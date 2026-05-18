# Chemistry Reaction Image Annotation Pipeline

> Track 2 of the Scientific Data Annotation Contest — converting 200 chemical reaction figures into structured JSON.

## Approach

Two-stage **semi-automated annotation with visual review**:

```
img/*.png ──┬──→ Stage 1: OpenChemIE inference (RxnScribe + MolScribe + OCR)
            │     → pipeline_out_raw/ (per-image raw output)
            │     → postprocess (drop TS / mechanism fragments)
            │     → convert (rough first-pass contest schema)
            │
            └──→ Stage 2: Claude visual labeling
                    ├── 10 hand-picked golden images (manual)
                    └── 190 remaining via 5 parallel Claude sub-agents
                          ↓
                  merge → RDKit/schema validate → score → package zip
```

OpenChemIE alone reaches only ~5% F1 on substrate-scope figures (it captures the
general scheme but does not enumerate the specific examples). The Claude visual
pass adds substrate-scope enumeration, fixes OCR errors, and excludes mechanism
/ derivatization blocks.

## Directory Layout

```
.
├── img/                  # 200 input PNGs (gitignored)
├── submission/           # 10 hand-labeled golden JSONs
├── submission_trial/     # 190 sub-agent labeled JSONs (gitignored)
├── submission_v2/        # final merged 200 JSONs (gitignored)
├── pipeline_out_raw/     # OpenChemIE raw output (gitignored)
├── pipeline_out/         # converted to contest schema (gitignored)
├── scripts/
│   ├── run_pipeline.py     # batch OpenChemIE on all images
│   ├── postprocess.py      # filter mechanism/TS reactions
│   ├── convert.py          # raw → contest schema
│   ├── validate.py         # schema + RDKit validation
│   ├── score.py            # InChIKey-based F1 vs gold
│   ├── merge.py            # gold + trial → final
│   └── package.py          # zip for submission
├── resume.sh             # auto-resume script (label remaining + finalize)
├── meta.md               # required submission metadata
├── LICENSE               # MIT
└── PIPELINE_README.md    # this file
```

## Setup

```bash
conda create -n chem-rxn python=3.10 -y
conda activate chem-rxn
conda install -c conda-forge rdkit poppler tesseract -y
pip install torch==2.2.2 torchvision==0.17.2 --index-url https://download.pytorch.org/whl/cu121
pip install 'openchemie @ git+https://github.com/CrystalEye42/OpenChemIE'
pip install "transformers<4.40"      # MolScribe / chemrxnextractor need this
pip install "numpy<2"                # torch 2.2.2 was compiled vs numpy 1.x
```

GPU library path workaround (matplotlib needs newer libstdc++):

```bash
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH
```

## End-to-end run

```bash
# 1. OpenChemIE inference on all 200 images (~8 min on 1×RTX 4090)
CUDA_VISIBLE_DEVICES=0 python scripts/run_pipeline.py img pipeline_out_raw

# 2. Heuristic post-processing (drop mechanism/TS fragments)
python scripts/postprocess.py pipeline_out_raw pipeline_out_clean

# 3. Convert to contest schema
python scripts/convert.py pipeline_out_clean pipeline_out

# 4. Hand-label 10 golden images → submission/

# 5. Sub-agent labeling of remaining 190 → submission_trial/
#    (Claude Code with parallel sub-agents; see prompts in resume.sh)

# 6. Merge + validate + package
python scripts/merge.py submission submission_trial submission_v2
python scripts/validate.py submission_v2/*.json
python scripts/score.py submission_v2 submission     # internal F1 vs gold
python scripts/package.py submission_v2 submission.zip
```

## Contest Schema (summary)

```json
{
  "reactions": [
    [
      {"type": "reactants",   "text": "<SMILES>", "relations": []},
      {"type": "reagent",     "text": "<SMILES>", "relations": ["5 mol%"]},
      {"type": "temperature", "text": "r.t.",      "relations": []},
      {"type": "time",        "text": "12 h",      "relations": []},
      {"type": "products",    "text": "<SMILES>", "relations": ["91% yield", "95% ee"]}
    ]
  ]
}
```

`type` enum: `reactants` | `reagent` | `products` | `temperature` | `time` | `other conditions`.
SMILES must parse with RDKit. `relations` is always a list (may be empty).

## Internal benchmark

Comparison done on the 10 golden images using InChIKey skeleton-block (first 14
chars) entity matching:

- Pipeline alone (OpenChemIE + post-process): **F1 ≈ 5.3%**
- Pipeline + Claude visual review: **F1 ≈ TBD after full run**

## Models Used

| Component | Source | License |
|---|---|---|
| Claude Opus 4.7 | Anthropic API | Commercial (used for labeling + orchestration) |
| OpenChemIE 0.1.0 | https://github.com/CrystalEye42/OpenChemIE | MIT |
| MolScribe 1.1.1 | https://github.com/thomas0809/MolScribe | MIT |
| RxnScribe 1.0 | https://github.com/thomas0809/RxnScribe | MIT |
| RDKit 2026.3.2 | https://github.com/rdkit/rdkit | BSD-3 |

## License

MIT — see [LICENSE](LICENSE).
