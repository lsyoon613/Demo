# Synthesis Route Review · AiZynthFinder / ASKCOS / ADMET-AI

An independent **local Windows app** for route discovery, PubChem identity resolution, optional Enamine starting-material quotes, reaction/impurity predictions, natural-origin review, and exportable HTML/JSON reports. It does not modify AiZynthFinder, ASKCOS, or any other project. The UI is in Korean.

**Repository layout:** `src/` contains the app and service modules; `tests/` contains checks; `scripts/` contains optional live verification; `docs/` contains the [GitHub upload guide](docs/GITHUB_UPLOAD_안내.md) and [remote Enamine server guide](docs/REMOTE_ENAMINE_설정.md). `data/` holds small public evidence/examples, `examples/` holds redacted sample HTML, and `price_db/` contains DB-building tools. Install and launch from the repository root using `install.ps1` and `start.bat`.

## Minimum working install (Windows 10/11)

Install **64-bit Python 3.11**, have at least **3 GB free for model downloads** (more for Python dependencies), internet access for first install and PubChem lookups, then run in PowerShell. The installer detects standard `py -3.11`, uv-registered CPython 3.11, or `python` on PATH; alternatively set `SYNTHESIS_PYTHON311` to the full path of your Python 3.11 executable:

```powershell
git clone https://github.com/lsyoon613/Demo.git
cd Demo
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
.\start.bat
```

Open <http://localhost:8502>. `install.ps1` creates `.venv`, installs pinned AiZynthFinder 4.4.1 and app dependencies, downloads the **public** USPTO expansion/filter/template files and ZINC stock into `models/`, and checks SHA-256. Downloads total roughly **775 MB**; `setup_models.py` resumes interrupted transfers. `start.bat` starts Streamlit on localhost. If cloned under a different repository name, use that directory in the `cd` command. An existing AiZynthFinder/ASKCOS installation is *not* required for basic ZINC search.

If a model download is interrupted, rerun `install.ps1`: the `.part` file resumes with HTTP Range requests and is never treated as a verified model until its pinned size and SHA-256 match. Repeated incomplete downloads indicate a network/CDN issue; `setup_models.py` lists the public source URLs and pinned checksums if you need to obtain verified assets over a different connection.

**Already cloned before the app folders were added?** In the existing `Demo` folder run `git pull`, then run `powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1` before `start.bat`. If you downloaded a ZIP instead of cloning, download the current ZIP again and extract it to a new folder. If Python 3.11 cannot be detected automatically, set `$env:SYNTHESIS_PYTHON311 = 'C:\full\path\to\python.exe'` in that PowerShell window before installing.

Start with a PubChem name such as `aspirin`, a CAS number `50-78-2`, or a SMILES. Select **ZINC** then **새 경로 탐색**. The `doctor.py` check distinguishes missing optional services. If PubChem is offline, SMILES/InChI still work through RDKit; names/CAS/InChIKey require lookup. The **stored propranolol example** loads without a model search, but Enamine prices/stock comparison need the separate catalog described below.

## Optional components for full functionality

**Shared Enamine server option:** If a permitted server already has the Enamine stock, indexed catalog and AiZynthFinder models, clones can use its authenticated API instead of obtaining the SDF or copying its database. The server performs Enamine route search as well as per-structure catalog/quote lookups; ZINC and other UI features retain their current behavior. See [REMOTE_ENAMINE_설정.md](docs/REMOTE_ENAMINE_설정.md) for server/client commands, HTTPS or SSH tunnel setup and the required environment variables. Neither the server URL nor a private access token is bundled with this repo. If the server is offline or access is denied, Enamine queries report an error instead of inventing a zero price or negative stock result.

| Feature | Separate preparation | When absent |
| --- | --- | --- |
| Local ASKCOS condition, forward and impurity prediction | WSL2 Ubuntu with Docker Engine and an [ASKCOSv2 local deployment](https://askcos-docs.mit.edu/guide/4-Deployment/4.1-Customizing-local-deployment.html). Enable gateway and **QUARC, WLDN5 forward, Impurity Predictor, Fast Filter** on `http://127.0.0.1:9100`. Check <http://127.0.0.1:9100/docs>. Upstream [standalone module guide](https://askcos-docs.mit.edu/guide/4-Deployment/4.2-Standalone-deployment-of-individual-modules.html). ASKCOS assets/containers are not bundled with this repo; the service API address is currently local and fixed. | Prediction calls report failure; route search and HTML export still work. |
| ADMET-AI AMES | `.\.venv\Scripts\python.exe -m venv .admet-venv` then `.\.admet-venv\Scripts\python.exe -m pip install -r requirements-admet.txt` (independent environment, model downloads may occur at first prediction). | AMES unavailable, no safety determination. |
| Full Enamine stock and price matching | Obtain the Enamine building-block SDF under its distributor terms. Run `.\.venv\Scripts\python.exe price_db\build_catalog_db.py --sdf "C:\path\to\Enamine.sdf"` then `.\.venv\Scripts\python.exe price_db\export_aizynth_stock.py`. This builds `price_db/catalog.sqlite` and `price_db/enamine_inchikeys.txt` **once**, not for every request; ~1.17 million structures may take time and disk space. Optional private `price_db/enamine_quotes.csv` follows columns `catalog_id,package_amount,package_unit,currency,package_price,availability,url,retrieved_at_utc`; rebuild or run `price_db/refresh_quotes.py` to import quotes. | ZINC search works; Enamine purchasing/price/stock status is **unverified**, not zero or unavailable. |

The Enamine SDF, indexed database and historical quote files are deliberately **not published** here. Enamine's price coverage in the developer's local database was a small sample; prices are never invented. The ZINC stock is a route-search stock, not a price database. If you use `price_db/refresh_quotes.py`, run it only after a catalog has been built and you have your own quotes CSV. No Reaxys subscription/database is needed.

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

These are dated model predictions, not validated manufacturing routes. See [`verification_summary.json`](examples/verification_summary.json) for the statuses. A clean clone can read these examples without installing ASKCOS or the Enamine catalog. Re-running requires the optional components above.

**Interpretation of the actual run:** In the paclitaxel and valsartan reports, ASKCOS returned successful API responses, but **none of their stage targets were an exact stereochemical match among forward-model results**. Some results matched only after ignoring stereochemistry (reported separately as *same connectivity, stereochemistry unconfirmed*); valsartan's final target was not found even at the connectivity-only level. This is not evidence that these proposed routes succeed experimentally.

Impurity propagation **substitutes selected model-predicted side products for a connected intermediate in downstream steps**. An automatically suggested computation cap depends on route connections and available predictions; it is not an optimal chemical setting, nor exhaustive. In particular, a missing NDMA prediction is **not** evidence of NDMA absence. AMES score **≥0.5** triggers a *review-needed* status; **<0.5** is still a model estimate and does not establish safety or an ICH M7 classification. Natural-origin provenance requires actual evidence; a structurally similar paclitaxel precursor is flagged for review, never automatically declared semisynthetic or totally synthetic.

For aspirin routes containing **salicylic acid**, [PubChem CID 338](https://pubchem.ncbi.nlm.nih.gov/compound/338) documents natural occurrence in willow/wintergreen, but the actual purchased/used salicylic acid may be synthetically produced. The app therefore says **chemical synthesis route with naturally occurring feedstock; actual supply origin unknown** rather than asserting total- or semisynthesis. The optional **selected-route COCONUT lookup** checks at most 12 unique starting structures by exact InChIKey and stereochemical structure, caches results for a day, and shows organism-linked records without downloading the whole database. [COCONUT 2.0](https://doi.org/10.1093/nar/gkae1063) aggregates NPAtlas too; NPAtlas primarily covers microbial natural products and is not needed as a separate service for willow-derived salicylic acid. Database presence never proves the actual supplier's extraction source; absence never proves synthetic origin.

The developer's local Enamine snapshot matched salicylic acid to [EN300-16723](https://www.enaminestore.com/catalog/EN300-16723). Its product page does **not** disclose the manufacturing origin. A locally generated report displays the matched product and observed package quotes; the published example omits quote rows. The conditional classification remains *synthetic-salicylic-acid → total-synthesis candidate* versus *extracted-salicylic-acid → semisynthesis candidate*. A clean clone needs the configured Enamine gateway or its own SDF and independently collected quotes for live price matching.

AMES tables label each scored structure as route reactant/intermediate, ASKCOS direct byproduct or propagated scenario. Standalone inorganic ions such as `[Br-]` and structures without carbon or with fewer than three heavy atoms are listed as **not assessed**, rather than presenting an out-of-domain AMES score as an organic byproduct alert.

## For an installation agent (Codex)

Paste the repository URL and request: “Read README.md, install the Windows Python 3.11 core with `install.ps1`, run `doctor.py`, run unit tests, start the app and verify ZINC aspirin search. Ask me for the separately obtained Enamine SDF only if I want Enamine catalog/quote features. Set up local ASKCOS and ADMET-AI separately if full impurity/AMES analysis is requested.”

**Repository note:** this repository does not include `.venv`, `models/`, `price_db/catalog.sqlite`, Enamine SDF, or raw user quotes.
