"""Bounded, optional WebP preparation for the homepage's photo previews.

Only explicitly licensed iNaturalist images with cached attribution qualify.
Rendering can reuse this cache without Pillow or network access; deployment
builds opt into downloads. Failure always leaves the original photo URL usable.
"""

from __future__ import annotations

import hashlib
from html import escape
from http.client import HTTPException
from io import BytesIO
import json
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


MAX_PHOTOS = 20
MAX_BYTES = 5 * 1024 * 1024
MAX_PREPARATION_SECONDS = 60
TRANSFORM_VERSION = "webp-width240-500-quality78-method4-v1"
PHOTO_HOSTS = {"inaturalist-open-data.s3.amazonaws.com", "static.inaturalist.org"}
PHOTO_PATH = re.compile(r"/photos/([1-9][0-9]*)/(?:square|thumb|small|medium|large|original)\.(?:jpg|jpeg|png|webp)")
ASSET_NAME = re.compile(r"[a-f0-9]{64}\.webp")
MANIFEST_NAME = re.compile(r"([a-f0-9]{64})\.json")
LICENSE_URLS = {
    "cc0": "https://creativecommons.org/publicdomain/zero/1.0/",
    **{
        f"cc-{code}": f"https://creativecommons.org/licenses/{code}/4.0/"
        for code in ("by", "by-sa", "by-nc", "by-nc-sa")
    },
}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Even an approved source cannot redirect this fetch to another URL.
        return None


def _photo_id(url: Any) -> str | None:
    if not isinstance(url, str) or not url or re.search(r"[\s\x00-\x1f\x7f]", url):
        return None
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme != "https" or parts.netloc not in PHOTO_HOSTS or parts.fragment:
        return None
    match = PHOTO_PATH.fullmatch(parts.path)
    return match[1] if match else None


def _credit(row: dict[str, Any]) -> dict[str, str] | None:
    photo_id = _photo_id(row.get("photo_url"))
    license_code = row.get("photo_license")
    attribution = row.get("photo_attribution")
    if (
        not photo_id
        or not isinstance(license_code, str)
        or license_code not in LICENSE_URLS
        or not isinstance(attribution, str)
        or not attribution.strip()
    ):
        return None
    observation_url = row.get("url") or ""
    if not isinstance(observation_url, str) or not re.fullmatch(
        r"https://(?:www\.)?inaturalist\.org/observations/[1-9][0-9]*", observation_url
    ):
        observation_url = ""
    return {
        "attribution": attribution,
        "license": license_code,
        "license_url": LICENSE_URLS[license_code],
        "source_url": f"https://www.inaturalist.org/photos/{photo_id}",
        "observation_url": observation_url,
        "credits_url": f"/photo-credits.html#photo-{photo_id}",
    }


def _source_key(row: dict[str, Any]) -> str:
    identity = [row["photo_url"], row["photo_license"], row["photo_attribution"], TRANSFORM_VERSION]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=True).encode()).hexdigest()


def _read_limited(path: Path, limit: int) -> bytes:
    with path.open("rb") as source:
        data = source.read(limit + 1)
    if len(data) > limit:
        raise ValueError("oversized cached photo data")
    return data


def _cached_variants(cache_dir: Path, key: str) -> list[dict[str, Any]] | None:
    try:
        manifest = json.loads(_read_limited(cache_dir / f"{key}.json", 16 * 1024))
        if not isinstance(manifest, dict) or manifest.get("key") != key:
            return None
        variants = manifest.get("variants")
        if not isinstance(variants, list) or not 1 <= len(variants) <= 2:
            return None
        for variant in variants:
            if not isinstance(variant, dict):
                return None
            filename = variant.get("filename")
            width, height = variant.get("width"), variant.get("height")
            if (
                not isinstance(filename, str) or not ASSET_NAME.fullmatch(filename)
                or type(width) is not int or not 1 <= width <= 500
                or type(height) is not int or not 1 <= height <= 4096
            ):
                return None
            data = _read_limited(cache_dir / filename, MAX_BYTES)
            if (
                data[:4] != b"RIFF" or data[8:12] != b"WEBP"
                or hashlib.sha256(data).hexdigest() + ".webp" != filename
            ):
                return None
        return variants
    except (OSError, ValueError, TypeError):
        return None


def _download(url: str, deadline: float) -> bytes:
    request = Request(url, headers={"User-Agent": "moth-station-dashboard/0.1", "Accept": "image/*"})
    with build_opener(_NoRedirect()).open(request, timeout=5) as response:
        if response.getcode() != 200:
            raise ValueError("photo source did not return an image")
        length = response.headers.get("Content-Length")
        if length and int(length) > MAX_BYTES:
            raise ValueError("photo source is too large")
        chunks = []
        total = 0
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError("photo preparation budget exhausted")
            # read1 returns after at most one underlying read, so a slow stream
            # cannot keep an accumulating read() alive past the total budget.
            chunk = response.read1(min(64 * 1024, MAX_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_BYTES:
                raise ValueError("photo source is too large")
    return b"".join(chunks)


def _prepare_variants(url: str, cache_dir: Path, key: str, deadline: float) -> list[dict[str, Any]]:
    # Optional dependency: ordinary rendering and warm-cache reuse need only
    # the standard library. Import before fetching so a missing encoder costs
    # no image requests.
    from PIL import Image, ImageOps

    data = _download(url, deadline)
    try:
        with Image.open(BytesIO(data)) as source:
            if (
                source.format not in {"JPEG", "PNG", "WEBP"}
                or getattr(source, "n_frames", 1) != 1
                or not 1 <= source.width <= 4096
                or not 1 <= source.height <= 4096
            ):
                raise ValueError("unsupported photo dimensions or format")
            image = ImageOps.exif_transpose(source).convert("RGB")
    except Image.DecompressionBombError as exc:
        raise ValueError("photo dimensions are too large") from exc

    encoded = []
    for width in sorted({min(240, image.width), min(500, image.width)}):
        if time.monotonic() >= deadline:
            raise TimeoutError("photo preparation budget exhausted")
        height = max(1, round(image.height * width / image.width))
        resized = image.resize((width, height), Image.Resampling.LANCZOS)
        output = BytesIO()
        resized.save(output, "WEBP", quality=78, method=4)
        webp = output.getvalue()
        if len(webp) > MAX_BYTES:
            raise ValueError("encoded photo is too large")
        filename = hashlib.sha256(webp).hexdigest() + ".webp"
        encoded.append(({"filename": filename, "width": width, "height": height}, webp))

    cache_dir.mkdir(parents=True, exist_ok=True)
    for variant, webp in encoded:
        (cache_dir / variant["filename"]).write_bytes(webp)
    variants = [variant for variant, _ in encoded]
    (cache_dir / f"{key}.json").write_text(json.dumps({"schema": 1, "key": key, "variants": variants}), encoding="utf-8")
    return variants


def _trim_cache(cache_dir: Path, current_keys: set[str]) -> None:
    """Discard only recognized generated cache entries no longer in use.

    These derived assets can be regenerated from their source photographs.
    Public assets are untouched, and unknown or malformed cache files are left
    alone. Read manifests first so shared content hashes are never discarded.
    """
    manifests = []
    retained_assets = set()
    try:
        candidates = list(cache_dir.iterdir())
    except OSError:
        return
    for path in candidates:
        match = MANIFEST_NAME.fullmatch(path.name)
        if not match or path.is_symlink():
            continue
        try:
            manifest = json.loads(_read_limited(path, 16 * 1024))
            if not isinstance(manifest, dict) or manifest.get("schema") != 1 or manifest.get("key") != match[1]:
                continue
            variants = manifest.get("variants")
            if not isinstance(variants, list) or not 1 <= len(variants) <= 2:
                continue
            names = {
                variant.get("filename") for variant in variants
                if isinstance(variant, dict) and isinstance(variant.get("filename"), str)
                and ASSET_NAME.fullmatch(variant["filename"])
            }
            if len(names) != len(variants):
                continue
            if match[1] in current_keys:
                retained_assets.update(names)
            else:
                manifests.append((path, names))
        except (OSError, ValueError, TypeError):
            continue
    for path, names in manifests:
        try:
            path.unlink()
        except OSError:
            continue
        for name in names - retained_assets:
            asset = cache_dir / name
            if not asset.is_symlink():
                try:
                    asset.unlink(missing_ok=True)
                except OSError:
                    pass


def _publish_variants(variants: list[dict[str, Any]], cache_dir: Path, public_dir: Path) -> list[dict[str, Any]]:
    assets_dir = public_dir / "assets" / "photos"
    assets_dir.mkdir(parents=True, exist_ok=True)
    published = []
    for variant in variants:
        filename = variant["filename"]
        data = _read_limited(cache_dir / filename, MAX_BYTES)
        (assets_dir / filename).write_bytes(data)
        published.append({
            "url": f"/assets/photos/{filename}",
            "width": variant["width"],
            "height": variant["height"],
        })
    return published


def _write_credits(rows: list[dict[str, Any]], public_dir: Path) -> None:
    entries = []
    seen = set()
    for row in rows:
        credit = row.get("photo_credit")
        if not credit or credit["credits_url"] in seen:
            continue
        seen.add(credit["credits_url"])
        observation = (
            f' · <a href="{escape(credit["observation_url"])}">Observation</a>'
            if credit["observation_url"] else ""
        )
        entries.append(
            f'<li id="{escape(credit["credits_url"].split("#")[1])}">'
            f'<h2>{escape(str(row.get("label") or "Moth observation"))}</h2>'
            f'<p>{escape(credit["attribution"])}</p>'
            f'<p><a href="{escape(credit["source_url"])}">Original photo on iNaturalist</a>{observation}'
            f' · <a href="{escape(credit["license_url"])}">{escape(credit["license"].upper())}</a></p></li>'
        )
    public_dir.mkdir(parents=True, exist_ok=True)
    (public_dir / "photo-credits.html").write_text(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>Photo credits · Moth stations</title>'
        '<link rel="stylesheet" href="/assets/dashboard.css"></head>'
        '<body><main class="site-shell"><p><a href="/index.html">Moth stations</a></p>'
        '<h1>Photo credits</h1><p>These homepage photographs have been resized '
        'without cropping and converted to WebP for faster loading. Photographers '
        'retain their rights; the linked license applies to each resized copy.</p>'
        f'<ul>{"".join(entries)}</ul></main></body></html>',
        encoding="utf-8",
    )


def prepare_photos(
    rows: list[dict[str, Any]],
    public_dir: Path,
    cache_dir: Path,
    *,
    max_downloads: int = 20,
    allow_downloads: bool = False,
) -> list[dict[str, Any]]:
    """Copy rows, adding responsive assets and credits for eligible successes.

    At most 20 distinct eligible sources are read from cache or prepared. New
    attempts (including failures) are additionally limited by max_downloads and
    a 60-second shared deadline, checked between streamed reads. Each pending
    network operation has a five-second timeout. Duplicate rows share work.
    Recognized derived cache entries outside these current sources are removed
    so routine cache snapshots stay bounded. Public and unrelated files are
    untouched. Unknown sources, licensing gaps, and failures retain their
    original URL and receive no generated variants.
    """
    result = [dict(row) for row in rows]
    prepared: dict[str, list[dict[str, Any]] | None] = {}
    attempts = 0
    download_limit = max(0, min(MAX_PHOTOS, max_downloads))
    deadline = time.monotonic() + MAX_PREPARATION_SECONDS
    for row in result:
        credit = _credit(row)
        if credit is None:
            continue
        key = _source_key(row)
        if key not in prepared:
            if len(prepared) >= MAX_PHOTOS:
                continue
            prepared[key] = None
            try:
                variants = _cached_variants(cache_dir, key)
                if variants is None and allow_downloads and attempts < download_limit and time.monotonic() < deadline:
                    attempts += 1
                    variants = _prepare_variants(row["photo_url"], cache_dir, key, deadline)
                if variants:
                    prepared[key] = _publish_variants(variants, cache_dir, public_dir)
            except (OSError, ValueError, ImportError, SyntaxError, EOFError, HTTPException):
                # Includes timeouts, HTTP errors, invalid images, unsupported
                # optional encoders, and unwritable/missing cache files.
                continue
        if prepared[key]:
            row["photo_variants"] = [dict(variant) for variant in prepared[key]]
            row["photo_credit"] = credit
    _trim_cache(cache_dir, set(prepared))
    if any(row.get("photo_credit") for row in result):
        try:
            _write_credits(result, public_dir)
        except OSError:
            # Do not publish locally rewritten photos without their credits.
            return [dict(row) for row in rows]
    return result
