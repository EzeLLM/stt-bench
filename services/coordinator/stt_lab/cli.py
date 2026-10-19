import argparse
import json
import os
from pathlib import Path

from .db import Database
from .registry import register_manifest


def main():
    parser = argparse.ArgumentParser(
        description="Local checkpoint registration; metadata must be verified by the researcher"
    )
    parser.add_argument("--data", type=Path, default=Path(os.environ.get("STT_LAB_DATA", "data")))
    sub = parser.add_subparsers(dest="command", required=True)
    register = sub.add_parser("register-model")
    register.add_argument("manifest", type=Path)
    args = parser.parse_args()
    db = Database(args.data)
    if args.command == "register-model":
        model = register_manifest(db, json.loads(args.manifest.read_text()))
        print(json.dumps({"id": model["id"], "status": "hash-verified", "parity": model["parity"]}))


if __name__ == "__main__":
    main()
