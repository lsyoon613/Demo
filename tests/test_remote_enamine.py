"""Exercise the private gateway over real loopback HTTP without requiring AiZynthFinder models."""
from http.server import ThreadingHTTPServer
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Lock, Thread
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import requests

import remote_enamine
import service


class GatewayTests(unittest.TestCase):
    def test_authenticated_search_and_catalog_preserve_local_comparison(self):
        target = "CC(=O)Oc1ccccc1C(=O)O"
        salicylic = service.canonical("O=C(O)c1ccccc1O")
        route = {"id": "aizynth-1", "target": target, "stock": "Enamine (2026-09)",
                 "steps": [{"reactants": [salicylic, "CC(=O)Cl"], "product": target}]}
        with TemporaryDirectory(dir=Path.home() / "AppData/Local/Temp/opencode") as folder:
            db_path = Path(folder) / "catalog.sqlite"
            with closing(sqlite3.connect(db_path)) as db:
                db.executescript("CREATE TABLE stock (catalog_id TEXT, inchikey TEXT, smiles TEXT, url TEXT);"
                                 "CREATE TABLE quotes (catalog_id TEXT, package_amount REAL, package_unit TEXT, "
                                 "currency TEXT, package_price REAL, availability TEXT, observed_at TEXT, source TEXT);")
                from rdkit import Chem
                key = Chem.MolToInchiKey(Chem.MolFromSmiles(salicylic))
                db.execute("INSERT INTO stock VALUES (?,?,?,?)", ("EN300-16723", key, salicylic,
                                                           "https://www.enaminestore.com/catalog/EN300-16723"))
                db.execute("INSERT INTO quotes VALUES (?,?,?,?,?,?,?,?)",
                           ("EN300-16723", .05, "g", "USD", 19, "In stock", "2026-11-05", "test snapshot"))
                db.commit()
            server = ThreadingHTTPServer(("127.0.0.1", 0), remote_enamine.handler("a-test-secret-token-for-tests", Lock()))
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            url = f"http://127.0.0.1:{server.server_port}"
            try:
                with patch.object(service, "DB", db_path), patch.object(service, "_search_local", return_value=[route]) as local_search:
                    with patch.dict(os.environ, {remote_enamine.URL_ENV: url,
                                                 remote_enamine.CLIENT_TOKEN_ENV: "a-test-secret-token-for-tests"}):
                        self.assertEqual(service.search(target, "Enamine (2026-09)"), [route])
                        local_search.assert_called_once()
                        result = service.compare(target, [route])
                        self.assertEqual(result["catalog_status"], "remote_catalog_available")
                        leaf = next(item for item in result["routes"][0]["leaves"] if item["smiles"] == salicylic)
                        self.assertEqual(leaf["matches"][0]["catalog_id"], "EN300-16723")
                        self.assertEqual(leaf["matches"][0]["quotes"][0]["price"], 19)
                        self.assertEqual(result["routes"][0]["origin_status"], "natural_occurrence_review")
                        self.assertEqual(requests.post(url + "/v1/catalog", json={"smiles": [salicylic]}, timeout=5).status_code, 401)
                        child = subprocess.run([sys.executable, "-c",
                            "from pathlib import Path; import service; "
                            "service.DB=Path('missing-private-catalog.sqlite'); "
                            f"r=service.search({target!r}, 'Enamine (2026-09)'); "
                            f"c=service.compare({target!r},r); "
                            "print(c['catalog_status'], c['routes'][0]['price_coverage'])"],
                            capture_output=True, text=True, timeout=20, check=True,
                            env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")})
                        self.assertIn("remote_catalog_available 1", child.stdout)
                    with patch.dict(os.environ, {remote_enamine.URL_ENV: url,
                                                 remote_enamine.CLIENT_TOKEN_ENV: "wrong"}):
                        with self.assertRaisesRegex(ValueError, "HTTP 401"):
                            service.compare(target, [route])
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=5)

    def test_remote_connection_failures_are_not_silent_missing_stock(self):
        with patch.dict(os.environ, {remote_enamine.URL_ENV: "http://example.com:9200",
                                     remote_enamine.CLIENT_TOKEN_ENV: "test"}):
            with self.assertRaisesRegex(ValueError, "HTTPS"):
                remote_enamine.catalog(["CCO"])


if __name__ == "__main__":
    unittest.main()
