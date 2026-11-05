# Synthesis Route Review · AiZynthFinder / ASKCOS / ADMET-AI

An independent **local Windows app** for route discovery, PubChem identity resolution, optional Enamine starting-material quotes, reaction/impurity predictions, natural-origin review, and exportable HTML/JSON reports. It does not modify AiZynthFinder, ASKCOS, or any other project. The UI is in Korean.

**Repository layout:** `src/` contains the app and service modules; `tests/` contains checks; `scripts/` contains optional live verification and catalog bundle generation; `docs/` contains the [GitHub update guide](docs/GITHUB_UPLOAD_안내.md). `data/catalog_bundle/` contains the split, SHA-256-pinned Enamine snapshot, `examples/` holds sample HTML, and `price_db/` contains optional DB-building tools. Install and launch from the repository root using `install.ps1` and `start.bat`.

## Minimum working install (Windows 10/11)

### Download, extract, double-click

1. Download [Demo-main.zip](https://github.com/lsyoon613/Demo/archive/refs/heads/main.zip) and **extract the whole ZIP** to a folder (do not run files inside the ZIP viewer).
2. Double-click **`start.bat`** in that folder.
3. A console opens. On first launch it installs dependencies, restores Enamine data, and downloads public models. If Python 3.11 is missing, it attempts installation using Windows Package Manager (`winget`). Keep the console open and allow several minutes with internet access.
4. Once ready, the local server starts and opens your browser at **http://127.0.0.1:8502**. Re-launching the same running app opens its existing browser address. If another program occupies that port, the launcher selects a free port between 8503 and 8522 and displays it. Later launches reuse the installation. Keep the console open while using the app; Ctrl+C stops the server. Startup failures remain visible in the console.

If Windows Package Manager is unavailable, install 64-bit Python 3.11 from python.org once and double-click `start.bat` again. ASKCOS and AMES remain optional separate installations described below.

**Impurity prediction is not included in first-run automatic setup.** If QUARC/WLDN5/Impurity Predictor show `127.0.0.1:9100` connection refused, the app is running but the separate ASKCOS server on that user's PC is not. See [ASKCOS connection/setup instructions](docs/ASKCOS_LOCAL.md). Failed source predictions are now labelled as propagation **not run**, rather than a completed zero-result analysis.

### Command-line installation (optional)

Install **64-bit Python 3.11**, have at least **3 GB free for model downloads** (more for Python dependencies), internet access for first install and PubChem lookups, then run in PowerShell. The installer detects standard `py -3.11`, uv-registered CPython 3.11, or `python` on PATH; alternatively set `SYNTHESIS_PYTHON311` to the full path of your Python 3.11 executable:

```powershell
git clone https://github.com/lsyoon613/Demo.git
cd Demo
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
.\start.bat
```

Open <http://localhost:8502>. `install.ps1` creates `.venv`, **restores Enamine stock, SQLite catalog and dated quote CSV locally from the bundled 3-part archive (~99 MB)** and checks hashes/SQLite integrity. It then installs pinned AiZynthFinder 4.4.1 and app dependencies, downloads the **public** USPTO expansion/filter/template files and ZINC stock into `models/`, and checks SHA-256. Public model downloads total roughly **775 MB**; `setup_models.py` resumes interrupted transfers. `start.bat` starts Streamlit on localhost. If cloned under a different repository name, use that directory in the `cd` command. ASKCOS installation is separate.

If a model download is interrupted, rerun `install.ps1`: the `.part` file resumes with HTTP Range requests and is never treated as a verified model until its pinned size and SHA-256 match. Repeated incomplete downloads indicate a network/CDN issue; `setup_models.py` lists the public source URLs and pinned checksums if you need to obtain verified assets over a different connection.

**Already cloned before the app folders were added?** In the existing `Demo` folder run `git pull`, then run `powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1` before `start.bat`. If you downloaded a ZIP instead of cloning, download the current ZIP again and extract it to a new folder. If Python 3.11 cannot be detected automatically, set `$env:SYNTHESIS_PYTHON311 = 'C:\full\path\to\python.exe'` in that PowerShell window before installing.

Start with a PubChem name such as `aspirin`, a CAS number `50-78-2`, or a SMILES. Select **Enamine (2026-09)** or **ZINC** then **새 경로 탐색**. The `doctor.py` check distinguishes missing optional services. If PubChem is offline, SMILES/InChI still work through RDKit; names/CAS/InChIKey require lookup. The **stored propranolol example** loads without a model search.

## Optional components for full functionality

Enamine route search and stock/price matching now run **locally**. The repository includes a consistent snapshot indexed from 1,173,509 structurally parsed products. The SQLite snapshot holds **3,908 observed package quote records** with timestamps/sources for a limited subset of products; the included supplementary CSV holds **3,042** of these collected quote records. Unquoted products have unknown prices, not $0. These are noncommercial academic research snapshots for the Department of AI-Based Drug Development, Duksung Women's University; reconfirm price and availability before ordering. Neither PubChem nor COCONUT requires a local bulk download.

| Feature | Separate preparation | When absent |
| --- | --- | --- |
| Local ASKCOS condition, forward and impurity prediction | WSL2 Ubuntu with Docker Engine and an [ASKCOSv2 local deployment](https://askcos-docs.mit.edu/guide/4-Deployment/4.1-Customizing-local-deployment.html). Enable gateway and **QUARC, WLDN5 forward, Impurity Predictor, Fast Filter** on `http://127.0.0.1:9100`. Check <http://127.0.0.1:9100/docs>. Upstream [standalone module guide](https://askcos-docs.mit.edu/guide/4-Deployment/4.2-Standalone-deployment-of-individual-modules.html). ASKCOS assets/containers are not bundled with this repo; the service API address is currently local and fixed. | Prediction calls report failure; route search and HTML export still work. |
| ADMET-AI AMES | `.\.venv\Scripts\python.exe -m venv .admet-venv` then `.\.admet-venv\Scripts\python.exe -m pip install -r requirements-admet.txt` (independent environment, model downloads may occur at first prediction). | AMES unavailable, no safety determination. |

The **raw 2.34 GB Enamine SDF is not needed to run this app** and is not included; only the indexed DB, stock file and observed quote CSV are bundled in compressed parts, restored during installation. The ZINC stock is a route-search stock, not a price database. To rebuild the DB from a newly acquired SDF or update quotes, use `price_db/build_catalog_db.py`, `price_db/export_aizynth_stock.py`, and `price_db/refresh_quotes.py`. To publish a refreshed snapshot use `scripts/build_catalog_bundle.py --source price_db --out <new-empty-directory>` and review the generated manifest before replacing the bundle. No Reaxys subscription/database is needed.

## Reproducible checks and reports

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.\.venv\Scripts\python.exe -X utf8 doctor.py
# With Enamine, ASKCOS and ADMET-AI installed, generate three live HTML/JSON examples:
.\.venv\Scripts\python.exe -X utf8 scripts\verify_targets.py
```

The last command runs live propranolol (Enamine), paclitaxel (Enamine) and valsartan (ZINC) predictions; it may take a long time. Generated reports are stored in `verified_reports/` and are ignored by Git. Users can also click **선택 경로 사람이 읽는 HTML 보고서** to download the selected route. JSON preserves requests/responses. Reports include names, input identifiers, CID/InChIKey, each step's structures/SMILES, origin evidence, predictions and unresolved values. User-entered step yields alone generate a relative yield scenario; actual final mass and total cost remain uncalculated without measured inputs.

Previously generated, downloadable **HTML examples** are in [`examples/`](examples/):

- [Propranolol · Enamine · 1 step](examples/Propranolol_CID4946_AQHHHDLHHXJYJD_aizynth-1.html) — all three ASKCOS modules and AMES succeeded. This route has no downstream intermediate to propagate.
- [Propranolol · ZINC · 3 steps](examples/Propranolol_CID4946_AQHHHDLHHXJYJD_aizynth-4_ZINC.html) — an additional multi-step check: all 9 stage/module requests, 4 bounded propagation scenarios and AMES completed. The first forward-model target was not returned; the following two were exact matches within model candidates, not experimental validation.
- [Paclitaxel · Enamine · 5 steps](examples/Paclitaxel_CID36314_RCINICONZNJXQF_aizynth-1.html) — all 15 stage/module requests and 8 bounded propagation scenarios completed; taxane-like precursor is **origin review required**, not proven natural extraction.
- [Valsartan · ZINC · 3 steps](examples/Valsartan_CID60846_ACWBQPMHZXGDFX_aizynth-1.html) — all 9 stage/module requests and 4 bounded propagation scenarios completed; **NDMA not established by this model run** (not a negative safety finding).
- [Metoprolol · Enamine · 1 step](examples/Metoprolol_CID4171_IUBSYMUCCVWXPE_aizynth-1.html) — additional live target: ASKCOS modules and AMES succeeded. Two **organic, non-route-material** ASKCOS byproduct candidates had AMES model scores of about **0.954 and 0.974** (review flags, not measured mutagenicity or observed impurities).
- [Aspirin · Enamine · origin review](examples/Aspirin_CID2244_BSYNRYMUTXBXSQ_aizynth-1_origin.html) — salicylic acid exact structure matched PubChem natural-occurrence evidence and COCONUT CNP0230203.0. Actual feedstock extraction/synthesis is unknown. This report tests identity/origin; ASKCOS and AMES were **not run** for this example.

These are dated model predictions, not validated manufacturing routes. See [`verification_summary.json`](examples/verification_summary.json) for the statuses. A clean clone can read these examples without installing ASKCOS or running a model search. Re-running the optional impurity/AMES stages requires the components above.

**Interpretation of the actual run:** In the paclitaxel and valsartan reports, ASKCOS returned successful API responses, but **none of their stage targets were an exact stereochemical match among forward-model results**. Some results matched only after ignoring stereochemistry (reported separately as *same connectivity, stereochemistry unconfirmed*); valsartan's final target was not found even at the connectivity-only level. This is not evidence that these proposed routes succeed experimentally.

Impurity propagation **substitutes selected model-predicted side products for a connected intermediate in downstream steps**. An automatically suggested computation cap depends on route connections and available predictions; it is not an optimal chemical setting, nor exhaustive. In particular, a missing NDMA prediction is **not** evidence of NDMA absence. AMES score **≥0.5** triggers a *review-needed* status; **<0.5** is still a model estimate and does not establish safety or an ICH M7 classification. Natural-origin provenance requires actual evidence; a structurally similar paclitaxel precursor is flagged for review, never automatically declared semisynthetic or totally synthetic.

For aspirin routes containing **salicylic acid**, [PubChem CID 338](https://pubchem.ncbi.nlm.nih.gov/compound/338) documents natural occurrence in willow/wintergreen, but the actual purchased/used salicylic acid may be synthetically produced. The app therefore says **chemical synthesis route with naturally occurring feedstock; actual supply origin unknown** rather than asserting total- or semisynthesis. The optional **selected-route COCONUT lookup** checks at most 12 unique starting structures by exact InChIKey and stereochemical structure, caches results for a day, and shows organism-linked records without downloading the whole database. [COCONUT 2.0](https://doi.org/10.1093/nar/gkae1063) aggregates NPAtlas too; NPAtlas primarily covers microbial natural products and is not needed as a separate service for willow-derived salicylic acid. Database presence never proves the actual supplier's extraction source; absence never proves synthetic origin.

The included Enamine snapshot matches salicylic acid to [EN300-16723](https://www.enaminestore.com/catalog/EN300-16723). Its product page does **not** disclose the manufacturing origin. A locally generated report displays the matched product and observed package quotes; the published example omits quote rows. The conditional classification remains *synthetic-salicylic-acid → total-synthesis candidate* versus *extracted-salicylic-acid → semisynthesis candidate*.

AMES tables label each scored structure as route reactant/intermediate, ASKCOS direct byproduct or propagated scenario. Standalone inorganic ions such as `[Br-]` and structures without carbon or with fewer than three heavy atoms are listed as **not assessed**, rather than presenting an out-of-domain AMES score as an organic byproduct alert.

## For an installation agent (Codex)

Paste the repository URL and request: “Read README.md, install the Windows Python 3.11 core with `install.ps1`, check that `setup_catalog.py` restored the Enamine catalog, run `doctor.py` and unit tests, start the app and verify both Enamine and ZINC aspirin search. Set up local ASKCOS and ADMET-AI separately if full impurity/AMES analysis is requested.”

**Repository note:** the three versioned `data/catalog_bundle/part-*.bin` files contain an extractable copy of the indexed Enamine catalog and dated quote data. `.venv`, public model binaries and raw SDF remain outside Git.
