"""Build an offline indexed catalog from the local Enamine SDF and price CSVs.

Run from any directory: python price_db/build_catalog_db.py --sdf PATH_TO_ENAMINE_SDF
The SQLite DB is regenerated atomically and contains no inferred prices.
"""

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from rdkit import Chem


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SDF = ROOT / "Enamine_Building_Blocks_Stock_1173520cmpd_20260916.sdf"
OLD = HERE.parent / "data" / "kb_price_comparison.csv"
NEW = HERE / "enamine_quotes.csv"
DEST = HERE / "catalog.sqlite"


def build(sdf=SDF, quotes=NEW, legacy_prices=OLD):
    sdf = Path(sdf)
    if not sdf.is_file():
        raise FileNotFoundError(f"Enamine SDF not found: {sdf}")
    temp = DEST.with_suffix(".building.sqlite")
    if temp.exists():
        temp.unlink()
    db = sqlite3.connect(temp)
    try:
        db.executescript("""
            CREATE TABLE stock (
                catalog_id TEXT PRIMARY KEY, inchikey TEXT NOT NULL, smiles TEXT NOT NULL,
                name TEXT, url TEXT, stock_weight_g REAL, snapshot TEXT NOT NULL
            );
            CREATE TABLE quotes (
                catalog_id TEXT NOT NULL, supplier TEXT NOT NULL, package_amount REAL NOT NULL,
                package_unit TEXT NOT NULL, currency TEXT NOT NULL, package_price REAL NOT NULL,
                availability TEXT, url TEXT, observed_at TEXT, source TEXT NOT NULL,
                PRIMARY KEY (catalog_id, supplier, package_amount, package_unit, currency, source)
            );
        """)
        rows = []
        count = skipped = 0
        with sdf.open("rb") as handle:
            for mol in Chem.ForwardSDMolSupplier(handle, sanitize=True, removeHs=True, strictParsing=False):
                try:
                    if mol is None:
                        raise ValueError("unparseable molecule")
                    key = Chem.MolToInchiKey(mol)
                    cid = mol.GetProp("Catalog_ID")
                    if not key or not cid:
                        raise ValueError("missing identity")
                    weight = mol.GetProp("Stock_weight_G") if mol.HasProp("Stock_weight_G") else None
                    rows.append((cid, key, Chem.MolToSmiles(mol, isomericSmiles=True),
                                 mol.GetProp("IUPAC Name") if mol.HasProp("IUPAC Name") else None,
                                 mol.GetProp("URL") if mol.HasProp("URL") else None,
                                 float(weight) if weight else None, "2026-09-16"))
                except (ValueError, KeyError, RuntimeError):
                    skipped += 1
                if len(rows) >= 2000:
                    db.executemany("INSERT OR REPLACE INTO stock VALUES (?,?,?,?,?,?,?)", rows)
                    count += len(rows)
                    rows.clear()
        db.executemany("INSERT OR REPLACE INTO stock VALUES (?,?,?,?,?,?,?)", rows)
        count += len(rows)
        db.execute("CREATE INDEX stock_inchikey ON stock(inchikey)")
        new_count = old_count = 0
        if quotes and Path(quotes).exists():
            with Path(quotes).open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    db.execute("INSERT OR REPLACE INTO quotes VALUES (?,?,?,?,?,?,?,?,?,?)", (
                        row["catalog_id"], "Enamine", float(row["package_amount"]), row["package_unit"],
                        row["currency"], float(row["package_price"]), row["availability"],
                        row["url"], row["retrieved_at_utc"], "EnamineStore live page"))
                    new_count += 1
        if legacy_prices and Path(legacy_prices).exists():
            with Path(legacy_prices).open(encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    if row["판매처"] != "Enamine" or not row["카탈로그번호"] or not row["원래 가격"] or not row["용량"]:
                        continue
                    parts = row["용량"].strip().split()
                    original = row["원래 가격"].strip().split()
                    if len(parts) != 2 or len(original) != 2 or parts[1].lower() not in ("mg", "g", "kg") or original[0] not in ("USD", "EUR"):
                        continue
                    try:
                        amount, price = float(parts[0]), float(original[1].replace(",", ""))
                    except ValueError:
                        continue
                    db.execute("INSERT OR REPLACE INTO quotes VALUES (?,?,?,?,?,?,?,?,?,?)", (
                        row["카탈로그번호"], "Enamine", amount, parts[1].lower(), original[0],
                        price, row["비고"], row["URL"], row["조회일"], "KB price comparison CSV"))
                    old_count += 1
        db.commit()
        total = db.execute("SELECT count(*) FROM stock").fetchone()[0]
        print(f"SDF parsed={count} skipped={skipped} indexed={total} new_quotes={new_count} old_quotes={old_count}")
        if total < 1_000_000:
            raise ValueError("Unexpectedly few catalog records; original DB retained")
    finally:
        db.close()
    temp.replace(DEST)
    print(f"Saved {DEST} at {datetime.now(timezone.utc).isoformat()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build local Enamine stock index; prices are optional, never inferred")
    parser.add_argument("--sdf", type=Path, default=SDF, help="Local Enamine SDF downloaded separately")
    parser.add_argument("--quotes", type=Path, default=NEW, help="Optional user-provided EnamineStore quote CSV")
    parser.add_argument("--legacy-prices", type=Path, default=OLD, help="Optional user-provided KB comparison CSV")
    args = parser.parse_args()
    build(args.sdf, args.quotes, args.legacy_prices)
