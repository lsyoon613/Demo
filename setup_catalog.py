"""Restore the published Enamine index locally; only verified bundle bytes are used."""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import zipfile

ROOT = Path(__file__).resolve().parent
NAMES = ("catalog.sqlite", "enamine_inchikeys.txt", "enamine_quotes.csv")


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def restore(root: Path = ROOT) -> dict:
    bundle = root / "data" / "catalog_bundle"
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != "enamine-catalog-zip-v1" or set(manifest.get("files", {})) != set(NAMES):
        raise ValueError("Enamine 자료 목록/형식 불일치")
    if not isinstance(manifest.get("parts"), list) or not manifest["parts"]:
        raise ValueError("Enamine 압축 분할 목록 누락")
    output = root / "price_db"
    output.mkdir(exist_ok=True)
    for name in NAMES:
        info = manifest["files"][name]
        destination = output / name
        if destination.exists() and (destination.stat().st_size != info["size"] or digest(destination) != info["sha256"]):
            raise ValueError(f"기존 로컬 자료와 배포 스냅샷이 다릅니다. 덮어쓰지 않음: {destination}")
    archive = output / "catalog_bundle.zip.tmp"
    try:
        hasher = hashlib.sha256()
        with archive.open("wb") as combined:
            for index, part in enumerate(manifest["parts"], 1):
                name = f"part-{index:03d}.bin"
                if part.get("name") != name:
                    raise ValueError("Enamine 분할 파일 순서 오류")
                source = bundle / name
                if source.stat().st_size != part["size"] or digest(source) != part["sha256"]:
                    raise ValueError(f"Enamine 분할 파일 누락/손상: {name}")
                with source.open("rb") as stream:
                    while chunk := stream.read(1024 * 1024):
                        combined.write(chunk)
                        hasher.update(chunk)
        if hasher.hexdigest() != manifest["archive_sha256"]:
            raise ValueError("Enamine 합본 체크섬 불일치")
        with zipfile.ZipFile(archive) as zipped:
            if set(zipped.namelist()) != set(NAMES):
                raise ValueError("Enamine 압축 파일 구성 불일치")
            for name in NAMES:
                destination = output / name
                if destination.is_file():
                    continue
                staged = output / (name + ".tmp")
                try:
                    with zipped.open(name) as source, staged.open("wb") as target:
                        shutil.copyfileobj(source, target, length=1024 * 1024)
                    info = manifest["files"][name]
                    if staged.stat().st_size != info["size"] or digest(staged) != info["sha256"]:
                        raise ValueError(f"Enamine 복원 내용 불일치: {name}")
                    staged.replace(destination)
                finally:
                    staged.unlink(missing_ok=True)
        with closing(sqlite3.connect(f"file:{(output / 'catalog.sqlite').resolve().as_posix()}?mode=ro", uri=True)) as db:
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("Enamine SQLite 무결성 검사 실패")
            count = db.execute("SELECT COUNT(*) FROM stock").fetchone()[0]
            if count != manifest["stock_rows"]:
                raise ValueError("Enamine 제품 건수 불일치")
        return {"stock_rows": count, "quote_rows": manifest["quote_rows"], "bundle": str(bundle)}
    finally:
        archive.unlink(missing_ok=True)


if __name__ == "__main__":
    print("Verified local Enamine catalog:", restore())
