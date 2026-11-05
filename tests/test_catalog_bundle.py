"""Verify a GitHub-sized catalog bundle restores locally and rejects corruption."""
from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

import setup_catalog
from scripts.build_catalog_bundle import build


class CatalogBundleTests(unittest.TestCase):
    def test_roundtrip_integrity_and_no_overwrite_of_existing_database(self):
        with TemporaryDirectory(dir=Path.home() / "AppData/Local/Temp/opencode") as folder:
            root = Path(folder)
            source = root / "source"
            source.mkdir()
            with closing(sqlite3.connect(source / "catalog.sqlite")) as db:
                db.execute("CREATE TABLE stock (catalog_id TEXT)")
                db.execute("CREATE TABLE quotes (catalog_id TEXT)")
                db.execute("INSERT INTO stock VALUES ('EN-test')")
                db.execute("INSERT INTO quotes VALUES ('EN-test')")
                db.commit()
            (source / "enamine_inchikeys.txt").write_text("EXAMPLE-KEY\n", encoding="utf8")
            (source / "enamine_quotes.csv").write_text("catalog_id\nEN-test\n", encoding="utf8")
            bundle = root / "data/catalog_bundle"
            manifest = build(source, bundle)
            self.assertEqual(manifest["stock_rows"], 1)
            result = setup_catalog.restore(root)
            self.assertEqual(result["quote_rows"], 1)
            self.assertEqual((root / "price_db/enamine_inchikeys.txt").read_text(), "EXAMPLE-KEY\n")
            self.assertEqual(setup_catalog.restore(root)["stock_rows"], 1)
            (root / "price_db/enamine_inchikeys.txt").write_text("unexpected local edit", encoding="utf8")
            with self.assertRaisesRegex(ValueError, "덮어쓰지 않음"):
                setup_catalog.restore(root)

    def test_corrupt_split_part_is_rejected_before_extraction(self):
        with TemporaryDirectory(dir=Path.home() / "AppData/Local/Temp/opencode") as folder:
            root = Path(folder)
            source = root / "source"
            source.mkdir()
            with closing(sqlite3.connect(source / "catalog.sqlite")) as db:
                db.execute("CREATE TABLE stock (catalog_id TEXT)")
                db.execute("CREATE TABLE quotes (catalog_id TEXT)")
                db.commit()
            (source / "enamine_inchikeys.txt").write_text("key", encoding="utf8")
            (source / "enamine_quotes.csv").write_text("catalog_id\n", encoding="utf8")
            bundle = root / "data/catalog_bundle"
            build(source, bundle)
            part = bundle / "part-001.bin"
            with part.open("ab") as handle:
                handle.write(b"corruption")
            with self.assertRaisesRegex(ValueError, "분할 파일"):
                setup_catalog.restore(root)
            self.assertFalse((root / "price_db/catalog.sqlite").exists())


if __name__ == "__main__":
    unittest.main()
