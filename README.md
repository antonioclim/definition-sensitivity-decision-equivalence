# ODSA reproducibility materials · version 1.0.0

Research project: **Definition sensitivity and decision equivalence in science and technology indicators**. Author: Antonio Clim, Bucharest University of Economic Studies.

This distribution was prepared from the PC1 candidate derived from R19. Its Git tag is designated as `v1.0.0`. The Zenodo version DOI `10.5281/zenodo.24213372` was reserved in draft `24213372`. Consult the repository and DOI record for publication status and date.

- [GitHub repository](https://github.com/antonioclim/definition-sensitivity-decision-equivalence)
- [Zenodo version DOI](https://doi.org/10.5281/zenodo.24213372)

## Contents

| Directory | Contents |
|---|---|
| `simulation/` | Exact visible copies of the frozen simulation protocol, engine, tests and retained aggregate evidence |
| `oa/` | Captured R14.1 OpenAlex responses, frozen protocol, exact-arithmetic processing, outputs and independent checks |
| `scientific/ODSA_SCIENTIFIC_RECORDS_PC1.zip` | Complete retained metric-summary CSVs, historical verification, public FAT components and recovered independent FAT checks |
| `figures/` | Five current figures, editable ODG/FODG/SVG, export formats, source values and scientific caption registry |
| `evidence/` | Exact archive identity and historical source-to-candidate lineage |
| `third_party_notices/` | Applicable upstream notices with their original scope |
| `LICENSE.md`, `LICENSES/`, `RIGHTS_SCOPE.json`, `RIGHTS_INVENTORY.json` | Approved licence grants and upstream terms by component and file |

The manuscript, supplementary article documents and a historical manuscript-integration text are maintained separately. The distribution preserves the scientific archive, code, numerical inputs and results, frozen protocols, figures and audit records from PC1 byte for byte. In that earlier projection, three internal draft-portal references were removed from a historical technical README, and a factual World Bank source-route record took the place of the raw catalogue-page transcript. The source-route record preserves the catalogue identifier, DOI, access URLs, producer names, observed data-file dimensions and original capture hash.

The independent FAT verifier, its adjacent mathematical module, its public historical review and its synthetic-check source were recovered byte for byte from the supplied R17 historical capsule. The recovered public review matches the hash required by the existing FAT acceptance ledger. These files are in `scientific_records/independent/` after extraction. Recovery adds no new FAT calculation or new approval.

## Verify and extract

Use Python 3.12 or newer. Run these commands from the extracted archive root:

```console
python -B reproduce.py verify
python -B reproduce.py prepare-simulation --work-dir ../odsa_scientific_1_0_0
```

The commands use the standard library. Verification checks a closed file inventory, sizes and SHA-256 values, the OA component, the scientific archive and the visible scientific source projection. Extraction additionally verifies the inner closed manifest. Use a new or empty work directory outside the distribution. The wrapper writes the execution receipt and other generated files to that directory.

The extracted root is `../odsa_scientific_1_0_0/scientific_records/`. Its `frozen_simulation/09_R4_FULL_REPRODUCTION/outputs/` contains the complete retained **metric-summary tables** from the registered 1,080,000-replication execution. The original engine, protocol and explicit full-run gate are included for separate use.

Historical manifests, receipts and source registers identify their original scope. In the extracted archive, `scientific_records/SOURCE_PROJECTION_PC1.json` describes the earlier PC1 projection. The top-level `MANIFEST_SHA256.json` lists the version 1.0.0 payload. The historical R10 compatibility-view tool pins the original R5 manifests. For this distribution, use the commands on this page.

## Offline OpenAlex replay

Create a separate environment and install the exact dependencies in `requirements-oa.txt` if they are not already available:

```console
python -m venv ../odsa_env
```

On Windows PowerShell 5.1:

```powershell
& '..\odsa_env\Scripts\python.exe' -m pip install -r requirements-oa.txt
& '..\odsa_env\Scripts\python.exe' -B reproduce.py oa --work-dir '..\oa_replay_1_0_0'
if ($LASTEXITCODE -ne 0) { throw 'OA replay failed. Read the external work-directory logs.' }
```

On Linux or macOS:

```console
../odsa_env/bin/python -m pip install -r requirements-oa.txt
../odsa_env/bin/python -B reproduce.py oa --work-dir ../oa_replay_1_0_0
```

Dependency installation can contact the package index. The replay itself uses retained local inputs, makes no provider acquisition and compares six substantive outputs byte for byte. The execution receipt reports actual independent result and reporting comparisons. The zero-selection result for the strict below-25% threshold is retained.

The source is the R14.1 recovery acquisition. It does not recover the missing original R14 bytes. The cohort is 2024; responses were collected sequentially in November 2026 and country counts can overlap. The objective Q is stipulated. Neither semantic mismatch nor action disagreement is an established measure of welfare or policy effectiveness.

## Runtime dependencies and optional paths

| Path | Supplied dependency record | Scope |
|---|---|---|
| Integrity and extraction | Python standard library, Python >=3.12 for the outer wrapper | No numerical rerun |
| OA replay | `requirements-oa.txt` | `jsonschema==4.26.0` and its pinned dependencies |
| Frozen simulation | `simulation/03_EXECUTABLE/requirements.txt` | `numpy==2.3.5`, `PyYAML==6.0.3`, `pytest==9.0.2`; no automatic full run |
| Current figure generation | `figures/requirements_figures.txt` | lxml, PyMuPDF and Pillow; external `soffice`, `pdftops`, `inkscape` and `gs` for the documented export checks |
| Historical figure reproduction | Inner `frozen_simulation/05_FIGURE_REPRODUCTION/requirements_*.txt` | Matplotlib, pandas, Pillow, NumPy and optional python-pptx |
| FAT replay | Inner `fat/requirements_fat_r14_1.txt` and FAT README | Python, jsonschema and Node.js; separately authorised exact source input required |

Keep each component's pinned dependency files and original scientific entry points. Historical source availability and native-platform acceptance are separate claims. Linux verification does not establish Windows, PowerShell, Microsoft Word, browser or submission-portal acceptance.

## FAT access and evidence boundary

The private World Bank CSV and record-level working material are excluded. A new FAT replay requires the separately authorised exact canonical input identified in the FAT README. The producer never downloads that input. The required numbered recovery amendment is supplied in the outer `oa/05_AUDIT_AND_CONTINUITY/R14_1_AMENDMENT_01_RECOVERY.json`.

After extraction, the recovered independent verifier is `scientific_records/independent/verify_fat_r141.py`, with `r141_independent_math.py` beside it. Its retained public historical review is `R141_FAT_INDEPENDENT_REVIEW_PUBLIC.json`. The FAT README describes the producer and independent-review commands. Its `/component/independent/` placeholder maps to this recovered directory. Place any new protected run outside the distributed tree and never include it in an upload.

All four new FAT numerical blocks, the new eligible roster and the exact eligible count remain withheld. Recovery of public code and evidence does not release those results. The original World Bank download date and unresolved upstream state-eligibility limits remain open. The historical original full convergence-validator source remains unavailable; later bounded validators and reconciliation evidence are retained with their stated scope.

## Rights and attribution

Antonio Clim approved MIT for his original code and CC BY 4.0 for his software and protocol documentation, original figures and approved contributions to aggregate results. OpenAlex provider material and the seven World Bank Stata files retain their upstream terms. For the exact scopes, see [LICENCE scope](LICENSE.md) and the file-level inventory. `CITATION.cff` identifies this version for citation when it becomes available.

The source-to-candidate ledger records the provenance of the earlier PC1 preparation.
