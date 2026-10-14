"""Exercise image delivery with real image files and a fake HTTPS transport."""

from email.message import Message
from io import BytesIO
from http.client import IncompleteRead
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from urllib.response import addinfourl

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    from mothdash.photos import prepare_photos
except ModuleNotFoundError:
    prepare_photos = None


def photo(number=1, **overrides):
    return {
        "label": "Example moth",
        "photo_url": f"https://inaturalist-open-data.s3.amazonaws.com/photos/{number}/medium.jpg",
        "photo_attribution": "(c) A Naturalist, some rights reserved (CC BY-NC)",
        "photo_license": "cc-by-nc",
        "url": f"https://www.inaturalist.org/observations/{number + 100}",
        **overrides,
    }


def jpeg(size=(600, 400)):
    output = BytesIO()
    Image.new("RGB", size, "#526b49").save(output, "JPEG")
    return output.getvalue()


class PhotoTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(prepare_photos, "photo preparation utility is not implemented")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.public = self.root / "public"
        self.cache = self.root / "cache"
        self.requests = []

    def transport(self, data, *, status=200, headers=None, after_request=None):
        """Replace HTTPS I/O while retaining urllib's real redirect handling."""
        def respond(handler, request):
            self.requests.append((request.full_url, request.timeout))
            if after_request:
                after_request()
            if isinstance(data, Exception):
                raise data
            message = Message()
            message["Content-Type"] = "image/jpeg"
            for key, value in (headers or {}).items():
                message[key] = value
            response = addinfourl(BytesIO(data), message, request.full_url, status)
            response.msg = "OK" if status == 200 else "Redirect"
            return response
        return patch("urllib.request.HTTPSHandler.https_open", respond)

    def prepare(self, rows, **kwargs):
        return prepare_photos(rows, self.public, self.cache, **kwargs)

    def test_default_render_keeps_original_rows_without_network(self):
        rows = [photo()]
        with self.transport(AssertionError("render must not fetch")):
            result = self.prepare(rows)
        self.assertEqual(result, rows)
        self.assertEqual(self.requests, [])
        self.assertIsNot(result[0], rows[0])

    def test_rejects_unapproved_licenses_and_missing_attribution(self):
        rows = [photo(index + 1, photo_license=license) for index, license in enumerate(
            (None, "", "cc-by-nd", "cc-by-nc-nd", "all-rights-reserved", "bogus")
        )]
        rows += [photo(50, photo_attribution=""), photo(51, photo_attribution=" \n ")]
        with self.transport(AssertionError("unsupported photos must not fetch")):
            result = self.prepare(rows, allow_downloads=True)
        self.assertEqual(result, rows)
        self.assertEqual(self.requests, [])

    def test_rejects_hosts_credentials_ports_and_malformed_paths(self):
        urls = [
            "http://static.inaturalist.org/photos/1/medium.jpg",
            "https://example.test/photos/1/medium.jpg",
            "https://static.inaturalist.org.example.test/photos/1/medium.jpg",
            "https://x.static.inaturalist.org/photos/1/medium.jpg",
            "https://user:pass@static.inaturalist.org/photos/1/medium.jpg",
            "https://static.inaturalist.org:444/photos/1/medium.jpg",
            "https://static.inaturalist.org/photos/1/../../medium.jpg",
            "https://static.inaturalist.org/photos/1/%2e%2e/medium.jpg",
            "https://static.inaturalist.org/photos/1/medium.svg",
            "https://static.inaturalist.org/photos/1/medium.jpg/extra",
            "https://static.inaturalist.org/photos/1/medium.jpg#fragment",
            "https://static.inaturalist.org/photos/1/medium.jpg\n",
            "https://[broken/photos/1/medium.jpg",
            "//static.inaturalist.org/photos/1/medium.jpg",
        ]
        rows = [photo(photo_url=url) for url in urls]
        with self.transport(AssertionError("invalid URL must not fetch")):
            result = self.prepare(rows, allow_downloads=True)
        self.assertEqual(result, rows)
        self.assertEqual(self.requests, [])


@unittest.skipUnless(Image is not None, "Pillow is optional for network-free rendering")
class EncodedPhotoTests(PhotoTests):
    def test_portrait_variants_have_actual_widths_and_preserve_aspect(self):
        rows = [photo()]
        with self.transport(jpeg((600, 1200))):
            result = self.prepare(rows, allow_downloads=True)
        self.assertEqual(self.requests, [(rows[0]["photo_url"], 5)])
        self.assertEqual(rows, [photo()])
        self.assertEqual(result[0]["photo_url"], rows[0]["photo_url"])
        variants = result[0]["photo_variants"]
        self.assertEqual([(v["width"], v["height"]) for v in variants], [(240, 480), (500, 1000)])
        for variant in variants:
            self.assertRegex(variant["url"], r"^/assets/photos/[a-f0-9]{64}\.webp$")
            with Image.open(self.public / variant["url"].lstrip("/")) as image:
                self.assertEqual(image.format, "WEBP")
                self.assertEqual(image.size, (variant["width"], variant["height"]))

    def test_small_original_is_not_upscaled_or_duplicated(self):
        with self.transport(jpeg((80, 40))):
            result = self.prepare([photo()], allow_downloads=True)
        self.assertEqual([(v["width"], v["height"]) for v in result[0]["photo_variants"]], [(80, 40)])

    def test_credits_preserve_attribution_source_license_and_changes(self):
        row = photo(photo_attribution='(c) A & B <Naturalist> "Credit"', label="Moth <name>")
        with self.transport(jpeg()):
            result = self.prepare([row], allow_downloads=True)
        credit = result[0]["photo_credit"]
        self.assertEqual(credit["attribution"], row["photo_attribution"])
        self.assertEqual(credit["source_url"], "https://www.inaturalist.org/photos/1")
        self.assertEqual(credit["observation_url"], row["url"])
        self.assertEqual(credit["license_url"], "https://creativecommons.org/licenses/by-nc/4.0/")
        page = (self.public / "photo-credits.html").read_text()
        self.assertIn("(c) A &amp; B &lt;Naturalist&gt; &quot;Credit&quot;", page)
        self.assertIn(credit["source_url"], page)
        self.assertIn(credit["observation_url"], page)
        self.assertIn(credit["license_url"], page)
        self.assertIn("WebP", page)
        self.assertIn("resized", page)
        self.assertIn('id="photo-1"', page)

    def test_warm_cache_republishes_without_network_or_new_download_budget(self):
        with self.transport(jpeg()):
            initial = self.prepare([photo(), photo()], allow_downloads=True)
        self.assertEqual(len(self.requests), 1)
        self.public = self.root / "second-public"
        with self.transport(AssertionError("cache hit must not fetch")):
            result = self.prepare([photo()], max_downloads=0)
        self.assertEqual(result[0]["photo_variants"], initial[0]["photo_variants"])
        self.assertTrue((self.public / result[0]["photo_variants"][0]["url"].lstrip("/")).is_file())
        self.assertTrue((self.public / "photo-credits.html").is_file())
        self.assertEqual(len(self.requests), 1)

    def test_metadata_change_invalidates_old_cache(self):
        with self.transport(jpeg()):
            self.prepare([photo()], allow_downloads=True)
        with self.transport(AssertionError("cache-only render must not fetch")):
            changed = self.prepare([
                photo(photo_attribution="New photographer"),
                photo(photo_license="cc-by"),
                photo(photo_url="https://static.inaturalist.org/photos/1/medium.jpg"),
            ])
        self.assertTrue(all("photo_variants" not in row for row in changed))

    def test_failed_downloads_count_toward_budget_and_duplicates_do_not_retry(self):
        rows = [photo(1), photo(1), photo(2), photo(3)]
        with self.transport(TimeoutError("source unavailable")):
            result = self.prepare(rows, allow_downloads=True, max_downloads=2)
        self.assertEqual(result, rows)
        self.assertEqual([url for url, _ in self.requests], [rows[0]["photo_url"], rows[2]["photo_url"]])

    def test_hard_cap_covers_cache_hits_and_downloads(self):
        rows = [photo(index) for index in range(1, 26)]
        with self.transport(jpeg()):
            first = self.prepare(rows[:20], allow_downloads=True, max_downloads=999)
            first_cache = self.cache
            self.cache = self.root / "extra-cache"
            second = self.prepare(rows[20:], allow_downloads=True)
        for path in self.cache.iterdir():
            shutil.copyfile(path, first_cache / path.name)
        self.cache = first_cache
        self.assertTrue(all("photo_variants" in row for row in first + second))
        self.requests.clear()
        with self.transport(AssertionError("all sources cached")):
            combined = self.prepare(rows, allow_downloads=True, max_downloads=999)
        self.assertEqual(sum("photo_variants" in row for row in combined), 20)
        self.assertEqual(combined[20:], rows[20:])
        self.assertEqual(self.requests, [])
        self.cache = self.root / "empty-cache"
        with self.transport(jpeg()):
            cold = self.prepare(rows, allow_downloads=True, max_downloads=999)
        self.assertEqual(len(self.requests), 20)
        self.assertEqual(sum("photo_variants" in row for row in cold), 20)

    def test_redirect_is_not_followed_even_to_an_approved_host(self):
        row = photo()
        with self.transport(b"", status=302, headers={"Location": "https://static.inaturalist.org/photos/2/medium.jpg"}):
            result = self.prepare([row], allow_downloads=True)
        self.assertEqual(result, [row])
        self.assertEqual(len(self.requests), 1)

    def test_oversized_or_non_image_response_falls_back(self):
        for data, headers in [
            (b"not an image", {}),
            (b"x" * (5 * 1024 * 1024 + 1), {}),
            (jpeg(), {"Content-Length": str(5 * 1024 * 1024 + 1)}),
        ]:
            with self.subTest(headers=headers, size=len(data)), self.transport(data, headers=headers):
                result = self.prepare([photo()], allow_downloads=True)
            self.assertEqual(result, [photo()])
        self.assertFalse(list(self.public.glob("assets/photos/*.webp")))

    def test_corrupt_cache_and_unsafe_manifest_paths_fall_back(self):
        with self.transport(jpeg()):
            self.prepare([photo()], allow_downloads=True)
        manifest = next(self.cache.glob("*.json"))
        metadata = json.loads(manifest.read_text())
        metadata["variants"][0]["filename"] = "../../outside.webp"
        manifest.write_text(json.dumps(metadata))
        with self.transport(AssertionError("cache-only mode")):
            result = self.prepare([photo()])
        self.assertEqual(result, [photo()])
        manifest.write_text("not JSON")
        self.assertEqual(self.prepare([photo()]), [photo()])

    def test_credits_do_not_link_untrusted_observation_urls(self):
        with self.transport(jpeg()):
            result = self.prepare([photo(url="javascript:alert(1)")], allow_downloads=True)
        self.assertEqual(result[0]["photo_credit"]["observation_url"], "")
        self.assertNotIn("javascript:", (self.public / "photo-credits.html").read_text())

    def test_no_new_downloads_after_total_time_budget(self):
        clock = [0]
        rows = [photo(1), photo(2)]
        with patch("mothdash.photos.time.monotonic", lambda: clock[0]), self.transport(
            jpeg(), after_request=lambda: clock.__setitem__(0, 61)
        ):
            result = self.prepare(rows, allow_downloads=True)
        self.assertEqual(result, rows)
        self.assertEqual(len(self.requests), 1)

    def test_pillow_is_optional_and_warm_cache_remains_usable_without_it(self):
        with patch.dict("sys.modules", {"PIL": None}), self.transport(AssertionError("Pillow unavailable")):
            cold = self.prepare([photo()], allow_downloads=True)
        self.assertEqual(cold, [photo()])
        self.assertEqual(self.requests, [])
        with self.transport(jpeg()):
            initial = self.prepare([photo()], allow_downloads=True)
        with patch.dict("sys.modules", {"PIL": None}), self.transport(AssertionError("warm cache")):
            warm = self.prepare([photo()])
        self.assertEqual(warm[0]["photo_variants"], initial[0]["photo_variants"])

    def test_approved_license_codes_and_source_queries_are_retained(self):
        rows = [photo(index + 1, photo_license=license) for index, license in enumerate(
            ("cc0", "cc-by", "cc-by-sa", "cc-by-nc", "cc-by-nc-sa")
        )]
        rows[0]["photo_url"] = "https://static.inaturalist.org/photos/1/medium.jpeg?12345"
        with self.transport(jpeg()):
            result = self.prepare(rows, allow_downloads=True)
        self.assertTrue(all("photo_variants" in row for row in result))
        self.assertEqual(self.requests[0][0], rows[0]["photo_url"])
        self.assertEqual(result[0]["photo_credit"]["license_url"], "https://creativecommons.org/publicdomain/zero/1.0/")

    def test_incomplete_http_response_falls_back(self):
        with self.transport(IncompleteRead(b"partial")):
            result = self.prepare([photo()], allow_downloads=True)
        self.assertEqual(result, [photo()])

    def test_cache_retains_current_sources_and_leaves_unrelated_files_alone(self):
        with self.transport(jpeg((600, 400))):
            previous = self.prepare([photo(1)], allow_downloads=True)
        old_asset_names = {Path(v["url"]).name for v in previous[0]["photo_variants"]}
        unmanaged = self.cache / "notes.json"
        unmanaged.write_text("user notes")
        with self.transport(jpeg((400, 600))):
            current = self.prepare([photo(2)], allow_downloads=True)
        self.assertTrue(all(not (self.cache / name).exists() for name in old_asset_names))
        self.assertEqual(len(list(self.cache.glob("[0-9a-f]" * 64 + ".json"))), 1)
        self.assertTrue(all((self.cache / Path(v["url"]).name).is_file() for v in current[0]["photo_variants"]))
        self.assertEqual(unmanaged.read_text(), "user notes")
        with self.transport(AssertionError("retained current assets are warm")):
            reused = self.prepare([photo(2)])
        self.assertEqual(reused[0]["photo_variants"], current[0]["photo_variants"])

    def test_shared_asset_is_retained_when_one_source_leaves_the_preview(self):
        with self.transport(jpeg()):
            both = self.prepare([photo(1), photo(2)], allow_downloads=True)
        kept = self.prepare([photo(2)])
        self.assertEqual(kept[0]["photo_variants"], both[1]["photo_variants"])
        self.assertTrue(all((self.cache / Path(v["url"]).name).is_file() for v in kept[0]["photo_variants"]))


if __name__ == "__main__":
    unittest.main()
