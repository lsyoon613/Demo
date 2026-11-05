"""Publish-ready, split ZIP of the indexed catalog (no raw SDF required to run)."""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import zipfile

NAMES = ("catalog.sqlite", "enamine_inchikeys.txt", "enamine_quotes.csv")
CHUNK_SIZE = 32 * 1024 * 1024  # under GitHub's 100 MB regular-file limit


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def build(source: Path, destination: Path) -> dict:
    """Make a consistent read-only SQLite snapshot and an integrity-pinned bundle."""
    if any(not (source / name).is_file() for name in NAMES):
        raise FileNotFoundError("catalog.sqlite, enamine_inchikeys.txt and enamine_quotes.csv are required")
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise FileExistsError("Build in a new empty catalog_bundle directory to avoid overwriting existing data")
    with TemporaryDirectory() as folder:
        temp = Path(folder)
        snapshot = temp / "catalog.sqlite"
        with closing(sqlite3.connect(f"file:{(source / NAMES[0]).resolve().as_posix()}?mode=ro", uri=True)) as db, \
             closing(sqlite3.connect(snapshot)) as backup:
            db.backup(backup)
            stock_rows = backup.execute("SELECT COUNT(*) FROM stock").fetchone()[0]
            quote_rows = backup.execute("SELECT COUNT(*) FROM quotes").fetchone()[0]
            if backup.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("SQLite catalog failed integrity check")
        payload = {"catalog.sqlite": snapshot,
                   "enamine_inchikeys.txt": source / "enamine_inchikeys.txt",
                   "enamine_quotes.csv": source / "enamine_quotes.csv"}
        archive = temp / "catalog.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
            for name, path in payload.items():
                zipped.write(path, arcname=name)
        parts = []
        with archive.open("rb") as zipped:
            for index in range(1, (archive.stat().st_size + CHUNK_SIZE - 1) // CHUNK_SIZE + 1):
                path = destination / f"part-{index:03d}.bin"
                path.write_bytes(zipped.read(CHUNK_SIZE))
                parts.append({"name": path.name, "size": path.stat().st_size, "sha256": digest(path)})
        manifest = {"format": "enamine-catalog-zip-v1", "archive_sha256": digest(archive),
                    "stock_rows": stock_rows, "quote_rows": quote_rows,
                    "files": {name: {"size": path.stat().st_size, "sha256": digest(path)} for name, path in payload.items()},
                    "parts": parts, "note": "Exact-structure stock snapshot; quote coverage is partial and dated."}
        (destination / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True, help="Directory containing indexed DB, stock file, quote CSV")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "catalog_bundle")
    args = parser.parse_args()
    result = build(args.source, args.out)
    print(f"Bundled {result['stock_rows']:,} stock rows and {result['quote_rows']:,} dated quote rows in {len(result['parts'])} parts")
