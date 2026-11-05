"""Download four public upstream AiZynthFinder assets into this standalone app.

No third-party sources or the existing synthesis-suite checkout are modified.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import time

import requests

MODELS = Path(__file__).resolve().parent / "models"
ASSETS = {
    "uspto_model.onnx": ("https://zenodo.org/records/7797465/files/uspto_model.onnx",
                         "bd0a3cb74cd7068de474c8fb789a00a66bc42c75636d66510ccac585ebe928f8"),
    "uspto_templates.csv.gz": ("https://zenodo.org/records/7341155/files/uspto_unique_templates.csv.gz",
                               "a4f1945e90cfa195538320833d68aed38f14e2fcc2f8afb5d958bc920edcafbe"),
    "uspto_filter_model.onnx": ("https://zenodo.org/records/7797465/files/uspto_filter_model.onnx",
                                "ad29aa32bdfcbe37065045546493806cf04899c55386c438905d83fb14bb6320"),
    "zinc_stock.hdf5": ("https://ndownloader.figshare.com/files/23086469",
                        "99d39a6f807c3e815487500bafc2b4a9dc66a31af189e3b1776874fb0d4a188d"),
}
SIZES = {"uspto_model.onnx": 91518243, "uspto_templates.csv.gz": 3313598,
         "uspto_filter_model.onnx": 16788859, "zinc_stock.hdf5": 663232280}


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download(name: str, url: str, expected: str, expected_size: int) -> None:
    destination = MODELS / name
    if destination.is_file() and digest(destination) == expected:
        print(f"OK (already verified): {name}", flush=True)
        return
    if destination.exists():
        raise ValueError(f"Existing asset does not match pinned SHA-256; inspect before replacing: {destination}")
    partial = MODELS / (name + ".part")
    for attempt in range(4):
        offset = partial.stat().st_size if partial.exists() else 0
        if offset > expected_size:
            raise RuntimeError(f"Partial download exceeds expected file size; inspect and remove: {partial}")
        try:
            with requests.get(url, stream=True, timeout=(30, 120),
                              headers={"Range": f"bytes={offset}-"} if offset else {},
                              allow_redirects=True) as response:
                response.raise_for_status()
                if offset and (response.status_code != 206 or
                               not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-")):
                    raise RuntimeError("Server did not honor resumed range; remove .part and retry")
                with partial.open("ab" if offset else "wb") as output:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            output.write(chunk)
            received = partial.stat().st_size
            if received < expected_size:
                raise requests.ConnectionError(f"Incomplete download: {received:,}/{expected_size:,} bytes; resuming")
            if received > expected_size:
                raise RuntimeError(f"Downloaded file exceeds pinned size; inspect and remove: {partial}")
            if digest(partial) != expected:
                raise RuntimeError(f"Complete file SHA-256 mismatch for {name}; inspect and remove: {partial}")
            partial.replace(destination)
            print(f"OK: {name} ({destination.stat().st_size:,} bytes)", flush=True)
            return
        except requests.RequestException as exc:
            if attempt == 3:
                raise RuntimeError(f"Download incomplete/failed for {name}: {exc}. "
                                   f"Rerun install.ps1 to resume {partial}, or use a trusted copy with the pinned SHA-256.") from exc
            print(f"Retrying {name} from {partial.stat().st_size if partial.exists() else 0} bytes: {exc}", flush=True)
            time.sleep(2 * (attempt + 1))


def main() -> None:
    MODELS.mkdir(exist_ok=True)
    for name, (url, checksum) in ASSETS.items():
        print(f"Checking {name} from {url}", flush=True)
        download(name, url, checksum, SIZES[name])
    print("Public model assets ready. Enamine stock/catalog are restored locally from the GitHub bundle by setup_catalog.py.")


if __name__ == "__main__":
    main()
