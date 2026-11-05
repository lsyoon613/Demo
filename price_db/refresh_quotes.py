"""Upsert newly collected EnamineStore quotes without rebuilding the SDF index."""

import csv
from pathlib import Path
import sqlite3


HERE = Path(__file__).resolve().parent


def refresh():
    db_path = HERE / "catalog.sqlite"
    if not db_path.is_file():
        raise FileNotFoundError(f"Run build_catalog_db.py first: {db_path}")
    count = 0
    with sqlite3.connect(db_path) as db, (HERE / "enamine_quotes.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            db.execute("INSERT OR REPLACE INTO quotes VALUES (?,?,?,?,?,?,?,?,?,?)", (
                row["catalog_id"], "Enamine", float(row["package_amount"]), row["package_unit"],
                row["currency"], float(row["package_price"]), row["availability"], row["url"],
                row["retrieved_at_utc"], "EnamineStore live page"))
            count += 1
    print(f"Synchronized {count} observed package quotes to {db_path}")


if __name__ == "__main__":
    refresh()
