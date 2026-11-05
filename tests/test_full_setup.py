"""Full setup must check model identity/readiness, not just an open API port."""
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.check_backends import REQUIRED, askcos_ready
from backends.askcos.prepare import download


class Response:
    def __init__(self, body, status=200, headers=None):
        self.body, self.status_code, self.headers = body, status, headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, size):
        yield self.body


class FullSetupTests(unittest.TestCase):
    def test_all_five_named_models_must_be_ready(self):
        rows = [{"name": name, "ready": True, "to_start": True} for name in REQUIRED]
        self.assertTrue(askcos_ready({"modules": rows}))
        rows[0]["ready"] = False
        self.assertFalse(askcos_ready({"modules": rows}))
        rows[0] = {"name": "unrelated", "ready": True, "to_start": True}
        self.assertFalse(askcos_ready({"modules": rows}))

    def test_model_download_resumes_then_verifies_sha256(self):
        content = b"official checkpoint bytes"
        with TemporaryDirectory() as folder:
            target = Path(folder) / "model.ckpt"
            responses = [Response(content[:4]), Response(content[4:], 206, {"Content-Range": f"bytes 4-{len(content)-1}/{len(content)}"})]
            with patch("backends.askcos.prepare.requests.get", side_effect=responses) as get, \
                 patch("backends.askcos.prepare.time.sleep"):
                download("https://example.org/model", target, hashlib.sha256(content).hexdigest(), len(content))
                self.assertEqual(get.call_args.kwargs["headers"], {"Range": "bytes=4-"})
            self.assertEqual(target.read_bytes(), content)

    def test_wrong_complete_model_never_becomes_usable(self):
        with TemporaryDirectory() as folder:
            target = Path(folder) / "model.ckpt"
            with patch("backends.askcos.prepare.requests.get", return_value=Response(b"bad")):
                with self.assertRaisesRegex(ValueError, "Checksum mismatch"):
                    download("https://example.org/model", target, hashlib.sha256(b"yes").hexdigest(), 3)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
