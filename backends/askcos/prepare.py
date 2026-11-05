"""Retrieve fixed upstream ASKCOS CPU sources and checksum-verified QUARC assets."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import secrets
import shutil
import tarfile
import time

import requests

ROOT = Path(__file__).resolve().parent
DOCKERFILES = {"askcos2_core": ("gateway", "Dockerfile_app"),
               "forward_predictor/wldn5": ("forward", "Dockerfile_cpu"),
               "fast_filter": ("filter", "Dockerfile_ff_cpu"),
               "impurity_predictor": ("impurity", "Dockerfile_impurity_cpu"),
               "atom_map/indigo": ("indigo", "Dockerfile_indigo_cpu"),
               "context_quarc": ("context", "Dockerfile_cpu")}


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def download(url, target, expected=None, size=None):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if expected and digest(target) == expected and target.stat().st_size == size:
            return
        if not expected and tarfile.is_tarfile(target):
            return
        raise ValueError(f"Existing download is not valid; inspect before replacing: {target}")
    part = target.with_name(target.name + ".part")
    for attempt in range(5):
        offset = part.stat().st_size if part.exists() else 0
        try:
            with requests.get(url, stream=True, headers={"Range": f"bytes={offset}-"} if offset else {}, timeout=(30, 120)) as r:
                r.raise_for_status()
                if offset and r.status_code == 206 and not r.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                    raise ValueError("Invalid resumed response")
                mode = "ab" if offset and r.status_code == 206 else "wb"
                written = 0
                with part.open(mode) as handle:
                    for chunk in r.iter_content(1024 * 1024):
                        handle.write(chunk)
                        written += len(chunk)
                if r.headers.get("Content-Length") and written != int(r.headers["Content-Length"]):
                    raise requests.ConnectionError("Response truncated; resuming")
            if size is not None and part.stat().st_size < size:
                raise requests.ConnectionError("Download incomplete; resuming")
            if expected and (part.stat().st_size != size or digest(part) != expected):
                raise ValueError(f"Checksum mismatch: {part}")
            if not expected and not tarfile.is_tarfile(part):
                raise requests.ConnectionError("Source archive incomplete")
            if not expected:
                try:
                    with tarfile.open(part) as archive:
                        archive.getmembers()
                except (tarfile.TarError, EOFError) as exc:
                    raise requests.ConnectionError("Source archive incomplete") from exc
            part.replace(target)
            return
        except requests.RequestException:
            if attempt == 4:
                raise
            time.sleep(2)


def main():
    versions = json.loads((ROOT / "local_sources.json").read_text())
    for repo, commit in versions.items():
        destination = ROOT / "ASKCOSv2" / repo
        marker = destination / ".demo-source-commit"
        if not marker.exists() or marker.read_text().strip() != commit:
            if destination.exists():
                raise ValueError(f"Unrecognized source directory; refusing to overwrite: {destination}")
            slug = repo.rsplit("/", 1)[-1]
            url = f"https://gitlab.com/mlpds_mit/askcosv2/{repo}/-/archive/{commit}/{slug}-{commit}.tar.gz"
            archive = ROOT / "downloads" / f"{slug}-{commit}.tar.gz"
            print(f"Downloading ASKCOS source: {repo} @ {commit}", flush=True)
            download(url, archive)
            staging = ROOT / "downloads" / f"unpack-{slug}"
            if staging.exists():
                shutil.rmtree(staging)
            staging.mkdir()
            with tarfile.open(archive) as compressed:
                compressed.extractall(staging, filter="data")
            entries = list(staging.iterdir())
            if len(entries) != 1 or not entries[0].is_dir():
                raise ValueError("Unexpected upstream source archive layout")
            destination.parent.mkdir(parents=True, exist_ok=True)
            entries[0].replace(destination)
            marker.write_text(commit)
        name, original = DOCKERFILES[repo]
        (ROOT / "dockerfiles").mkdir(exist_ok=True)
        shutil.copyfile(destination / original, ROOT / "dockerfiles" / (name + ".Dockerfile"))
    assets = json.loads((ROOT / "quarc_assets.json").read_text())
    for item in assets["files"]:
        target = ROOT / Path(item["file"].replace("\\", "/"))
        print(f"Verifying QUARC asset: {target.name} ({item['bytes']:,} bytes)", flush=True)
        cache = ROOT / "downloads" / "models" / target.name
        download(item["url"], cache, item["sha256"], item["bytes"])
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or digest(target) != item["sha256"]:
            shutil.copyfile(cache, target)
    env = ROOT / ".env"
    if not env.exists():
        env.write_text(f"LOCAL_MONGO_PASSWORD={secrets.token_hex(24)}\nLOCAL_OAUTH_SECRET={secrets.token_hex(32)}\n")
    print("ASKCOS source, model assets and local credentials prepared.", flush=True)


if __name__ == "__main__":
    main()
