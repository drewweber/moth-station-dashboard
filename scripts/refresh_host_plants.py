#!/usr/bin/env python3
"""Refresh mothdash/data/host_plants.json from the HOSTS database.

This is a MANUAL, occasional maintainer task -- it is never run by sync,
render, build, or CI. It queries two external services directly (not through
mothdash's normal synced-data path):

- The iNaturalist API, to list every Lepidoptera species (moths, i.e.
  excluding Papilionoidea/butterflies) ever reported in New York State
  (place_id=48), regardless of whether this project tracks it.
- The Natural History Museum's HOSTS database (CC0-licensed, archival,
  not updated since 2023), via its CKAN datastore_search API, queried by
  insect genus to keep the number of requests manageable.

Usage:
    python3 scripts/refresh_host_plants.py --step species   # refresh species list
    python3 scripts/refresh_host_plants.py --step hosts     # fetch host-plant records
    python3 scripts/refresh_host_plants.py --step build     # write host_plants.json

Each step is checkpointed to .cache/host_plants/ so a slow "hosts" run (there
are 1000+ genera; expect this to take a while and to need re-running to
resume) can be interrupted and continued without losing progress. Run "build"
last, once "hosts" has finished, to produce the final vendored file.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.parse
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / ".cache" / "host_plants"
OUTPUT_PATH = REPO_ROOT / "mothdash" / "data" / "host_plants.json"

NY_PLACE_ID = 48
MOTH_TAXON_ID = 47157
BUTTERFLY_TAXON_ID = 47224
HOSTS_RESOURCE_ID = "877f387a-36a3-486c-a0c1-b8d5fb69f85a"


def _curl_json(url: str, attempts: int = 3, timeout: int = 20) -> dict | None:
    for _ in range(attempts):
        out = subprocess.run(
            ["curl", "-s", "--max-time", str(timeout), url],
            capture_output=True,
            text=True,
        ).stdout
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            time.sleep(1)
    return None


def refresh_species(per_page: int = 200) -> None:
    """List every moth species reported in NY on iNaturalist."""
    cache_path = CACHE_DIR / "ny_species.json"
    try:
        species = json.loads(cache_path.read_text())
    except FileNotFoundError:
        species = {}

    page = 1
    while True:
        query = urllib.parse.urlencode(
            {
                "place_id": NY_PLACE_ID,
                "taxon_id": MOTH_TAXON_ID,
                "without_taxon_id": BUTTERFLY_TAXON_ID,
                "verifiable": "true",
                "per_page": per_page,
                "page": page,
                "order": "asc",
                "order_by": "id",
            }
        )
        url = f"https://api.inaturalist.org/v1/observations/species_counts?{query}"
        data = _curl_json(url)
        if not data:
            print(f"Failed to fetch page {page}, stopping.", file=sys.stderr)
            break
        rows = data.get("results", [])
        if not rows:
            break
        for row in rows:
            taxon = row.get("taxon") or {}
            name = taxon.get("name")
            if not name or len(name.split()) < 2:
                continue
            species[name] = {
                "taxon_id": taxon.get("id"),
                "common_name": taxon.get("preferred_common_name"),
            }
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(species))
        print(f"page {page}: {len(species)} unique species so far", file=sys.stderr)
        page += 1
        time.sleep(0.3)

    print(f"Done. {len(species)} species written to {cache_path}", file=sys.stderr)


def refresh_hosts(max_genera: int | None = None) -> None:
    """Fetch HOSTS records for every genus among the NY species list."""
    species_path = CACHE_DIR / "ny_species.json"
    if not species_path.exists():
        print("Run --step species first.", file=sys.stderr)
        sys.exit(1)
    species = json.loads(species_path.read_text())
    genera = sorted({name.split()[0] for name in species})

    hosts_path = CACHE_DIR / "hosts_by_genus.json"
    try:
        results = json.loads(hosts_path.read_text())
    except FileNotFoundError:
        results = {}

    processed = 0
    for genus in genera:
        if max_genera is not None and processed >= max_genera:
            break
        if genus in results:
            continue
        query = urllib.parse.urlencode(
            {
                "resource_id": HOSTS_RESOURCE_ID,
                "filters": json.dumps({"Insect Genus": genus}),
                "limit": 200,
            }
        )
        url = f"https://data.nhm.ac.uk/api/3/action/datastore_search?{query}"
        data = _curl_json(url, timeout=15)
        records = data["result"]["records"] if data and data.get("success") else []
        entries = []
        seen = set()
        for record in records:
            insect_species = (record.get("Insect Species") or "").strip()
            family = (record.get("Hostplant Family") or "").strip()
            hgenus = (record.get("Hostplant Genus") or "").strip()
            hspecies = (record.get("Hostplant Species") or "").strip()
            if not family and not hgenus:
                continue
            key = (insect_species, family, hgenus, hspecies)
            if key in seen:
                continue
            seen.add(key)
            entries.append(
                {"insect_species": insect_species, "family": family, "genus": hgenus, "species": hspecies}
            )
        results[genus] = entries
        processed += 1
        if processed % 10 == 0:
            hosts_path.write_text(json.dumps(results))
            print(f"progress: {len(results)}/{len(genera)} genera cached", file=sys.stderr)
        time.sleep(0.1)

    hosts_path.write_text(json.dumps(results))
    print(f"Done. {len(results)}/{len(genera)} genera cached in {hosts_path}", file=sys.stderr)
    if len(results) < len(genera):
        print("Not all genera fetched yet -- run --step hosts again to resume.", file=sys.stderr)


def _dedupe(records: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for record in records:
        family = record.get("family", "").strip()
        genus = record.get("genus", "").strip()
        species = record.get("species", "").strip()
        if not family and not genus:
            continue
        if family == "Polyphagous" and not genus:
            continue
        key = (family, genus, species)
        if key in seen:
            continue
        seen.add(key)
        out.append({"family": family, "genus": genus, "species": species})
    return out


def build() -> None:
    """Combine cached species + host records into mothdash/data/host_plants.json."""
    species_path = CACHE_DIR / "ny_species.json"
    hosts_path = CACHE_DIR / "hosts_by_genus.json"
    if not species_path.exists() or not hosts_path.exists():
        print("Run --step species and --step hosts first.", file=sys.stderr)
        sys.exit(1)

    ny_species = json.loads(species_path.read_text())
    by_genus = json.loads(hosts_path.read_text())

    species_hosts: dict[str, list[dict]] = {}
    match_level: dict[str, str] = {}
    for name in ny_species:
        parts = name.split()
        genus, epithet = parts[0], parts[1] if len(parts) > 1 else ""
        genus_records = by_genus.get(genus, [])
        exact = [r for r in genus_records if r.get("insect_species", "").strip().lower() == epithet.lower()]
        if exact:
            hosts = _dedupe(exact)[:20]
            level = "species"
        else:
            genus_only = [r for r in genus_records if not r.get("insect_species", "").strip()]
            hosts = _dedupe(genus_only)[:20]
            level = "genus" if hosts else None
        if hosts:
            species_hosts[name] = hosts
            match_level[name] = level

    taxa = {
        name: {"taxon_id": info["taxon_id"], "common_name": info.get("common_name")}
        for name, info in ny_species.items()
    }

    output = {
        "metadata": {
            "source": "HOSTS: a Database of the World's Lepidopteran Hostplants (Natural History Museum, London)",
            "source_url": "https://www.nhm.ac.uk/our-science/data/hostplants.html",
            "license": "CC0",
            "retrieved_at": date.today().isoformat(),
            "coverage": (
                "All Lepidoptera (moth) species reported in New York State on "
                "iNaturalist (place_id=48, excluding butterflies), not just species "
                "tracked by this project's stations."
            ),
            "species_covered": len(ny_species),
            "species_with_host_data": len(species_hosts),
            "notes": (
                "Archival dataset, not updated since 2023 -- host-plant records reflect "
                "historical literature, not necessarily current or local usage in New "
                "York, and may be incomplete or taxonomically outdated. Most entries are "
                "matched at the exact species level; a smaller number ('genus' in "
                "match_level) are only known at the genus level in HOSTS and are shown as "
                "a broader hint rather than a species-specific host record. A blank "
                "genus/species with a family listed means HOSTS only records the "
                "relationship at family level."
            ),
        },
        "species": species_hosts,
        "match_level": match_level,
        "taxa": taxa,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, separators=(",", ":")))
    print(
        f"Wrote {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size:,} bytes), "
        f"{len(species_hosts)}/{len(ny_species)} species with host data.",
        file=sys.stderr,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--step", choices=["species", "hosts", "build"], required=True)
    parser.add_argument(
        "--max-genera",
        type=int,
        default=None,
        help="For --step hosts: stop after fetching this many new genera (for resumable runs).",
    )
    args = parser.parse_args()

    if args.step == "species":
        refresh_species()
    elif args.step == "hosts":
        refresh_hosts(max_genera=args.max_genera)
    elif args.step == "build":
        build()


if __name__ == "__main__":
    main()
