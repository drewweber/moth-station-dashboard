"""Command line entry points."""

from __future__ import annotations

import argparse

from .config import load_config
from .db import init_db
from .render import render
from .sync import pending_station_updates, sync_all


def main() -> None:
    parser = argparse.ArgumentParser(prog="mothdash")
    parser.add_argument("--config", default="stations.toml")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init-db")

    sync_parser = subparsers.add_parser("sync")
    sync_parser.add_argument("--full", action="store_true")

    subparsers.add_parser("check")

    subparsers.add_parser("render")

    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--full", action="store_true")

    args = parser.parse_args()
    settings, stations = load_config(args.config)

    if args.command == "init-db":
        init_db(settings.database)
        print(f"Initialized {settings.database}")
    elif args.command == "sync":
        sync_all(settings, stations, full=args.full)
    elif args.command == "check":
        pending = pending_station_updates(settings, stations)
        print("pending_stations=" + ",".join(station.id for station in pending))
        print(f"updates={'true' if pending else 'false'}")
    elif args.command == "render":
        path = render(settings, stations)
        print(f"Wrote {path}")
    elif args.command == "build":
        sync_all(settings, stations, full=args.full)
        path = render(settings, stations)
        print(f"Wrote {path}")
    else:
        parser.print_help()
