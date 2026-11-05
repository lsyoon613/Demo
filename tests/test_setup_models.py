"""Check a prematurely closed public model download resumes safely."""
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import requests
import setup_models


class FakeResponse:
    def __init__(self, status, headers, body):
        self.status_code = status
        self.headers = headers
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def iter_content(self, chunk_size):
        yield self.body


class DownloadTests(unittest.TestCase):
    def test_truncated_200_response_resumes_with_range_and_hash_verification(self):
        content = b"verified-public-model"
        responses = [FakeResponse(200, {}, content[:7]),
                     FakeResponse(206, {"Content-Range": f"bytes 7-{len(content)-1}/{len(content)}"}, content[7:])]
        with TemporaryDirectory(dir=Path.home() / "AppData/Local/Temp/opencode") as folder:
            with patch.object(setup_models, "MODELS", Path(folder)), \
                 patch.object(setup_models.requests, "get", side_effect=responses) as get, \
                 patch.object(setup_models.time, "sleep"):
                setup_models.download("example.onnx", "https://example.org/example.onnx",
                                      hashlib.sha256(content).hexdigest(), len(content))
            self.assertEqual((Path(folder) / "example.onnx").read_bytes(), content)
            self.assertEqual(get.call_args_list[1].kwargs["headers"], {"Range": "bytes=7-"})


if __name__ == "__main__":
    unittest.main()
