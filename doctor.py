"""Fast dependency/asset status; does not initialize prediction models."""
import importlib.metadata
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))


def main():
    import remote_enamine
    for name in ("aizynthfinder", "streamlit", "rdkit", "admet-ai"):
        if name == "admet-ai":
            python = ROOT / ".admet-venv/Scripts/python.exe"
            if not python.is_file():
                print("ADMET-AI: separate environment missing")
                continue
            version = subprocess.run([str(python), "-c", "import importlib.metadata as m; print(m.version('admet-ai'))"],
                                     capture_output=True, text=True, timeout=10)
            print(f"ADMET-AI: {version.stdout.strip() if version.returncode == 0 else 'not installed'}")
            continue
        try:
            print(f"{name}: {importlib.metadata.version(name)}")
        except importlib.metadata.PackageNotFoundError:
            print(f"{name}: not installed")
    try:
        import pyarrow
        print(f"pyarrow: {pyarrow.__version__} (import OK)")
    except (ImportError, OSError) as exc:
        print(f"pyarrow: incompatible or missing ({exc})")
    for name, path in {"Enamine stock": ROOT / "price_db/enamine_inchikeys.txt",
                        "ZINC stock": ROOT / "models/zinc_stock.hdf5",
                        "catalog DB": ROOT / "price_db/catalog.sqlite",
                        "USPTO expansion model": ROOT / "models/uspto_model.onnx",
                        "USPTO templates": ROOT / "models/uspto_templates.csv.gz",
                        "USPTO filter model": ROOT / "models/uspto_filter_model.onnx"}.items():
        print(f"{name}: {'available' if path.is_file() else 'missing'} ({path})")
    if remote_enamine.configured():
        try:
            remote_enamine.catalog([])
            print("Remote Enamine gateway: authenticated catalog reachable")
        except ValueError as exc:
            print(f"Remote Enamine gateway: unavailable ({exc})")
    try:
        from urllib.request import urlopen
        with urlopen("http://127.0.0.1:9100/docs", timeout=3) as response:
            status = response.status
        print(f"ASKCOS local API: HTTP {status}")
    except OSError:
        print("ASKCOS local API: not running")
    print("App URL after start.bat: http://localhost:8502")


if __name__ == "__main__":
    main()
