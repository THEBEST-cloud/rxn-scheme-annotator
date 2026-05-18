#!/usr/bin/env bash
# Auto-resume script: labels remaining 16 images + merge + validate + package
# Designed to run unattended via systemd-run timer.

set -u
PROJ="/home/hoo/work/ljj-work/Match/化学反应结果标注大赛"
LOG="$PROJ/resume-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

echo "=== resume.sh started at $(date) ==="
cd "$PROJ"

# ---------- Step 1: label the 16 missing images via claude -p ----------
echo "=== Step 1: labeling 16 missing images via Claude CLI ==="

PROMPT='You label chemical reaction images for a competition. Produce one JSON file per image following an exact schema, validated with RDKit.

Working directory: /home/hoo/work/ljj-work/Match/化学反应结果标注大赛/

Your images (16 total): 0069, 0070, 0071, 0072, 0073, 0115, 0116, 0117, 0118, 0119, 0120, 0147, 0148, 0197, 0198, 0199

For each stem XXXX: read img/XXXX.png, write submission_trial/XXXX.json.

Read references once: README.md ; submission/0001.json ; submission/0050.json ; submission/0150.json ; submission_trial/0002.json.

Per-image: read image, optionally read pipeline_out/XXXX.json as hint, identify general scheme + selected examples (SKIP mechanism / transition state / Transformation of N / Proposed model blocks), emit one reaction per specific example in the selected-examples block (NOT the general scheme).

Schema: each entity {type, text, relations}. type ∈ {reactants, reagent, products, temperature, time, other conditions}. relations always a list (empty if no info). yield/ee/dr/er → products.relations. mol%/equiv → reagent.relations. SMILES MUST parse with RDKit.

SMILES tips: pinacol B = B1OC(C)(C)C(C)(C)O1 ; BF3K = [B-](F)(F)F.[K+] ; CH2Cl2=ClCCl, THF=C1CCOC1, DMSO=CS(C)=O, MeCN=CC#N, MeOH=CO, EtOH=CCO, AcOH=CC(=O)O, dioxane=C1COCCO1, toluene=Cc1ccccc1, DMF=CN(C)C=O. Boc carbamate = OC(=O)C(C)(C)C. Ts attached to X = XS(=O)(=O)c1ccc(C)cc1. Ring closure numbers MUST be unique across nesting (use c1ccc(-c2ccccc2)cc1 not c1ccc(c1cccc1)cc1). Stereo [C@H]/[C@@H] when wedge drawn.

After writing each XXXX.json: validate via /opt/anaconda3/bin/python scripts/validate.py submission_trial/XXXX.json. Fix any errors before moving to next image.

When all 16 are done, output a final report: total reactions, low-confidence list, time spent. Then exit.

Begin now. Do not ask clarifying questions; make reasonable calls.'

/usr/bin/claude -p "$PROMPT" \
  --add-dir "$PROJ" \
  --dangerously-skip-permissions \
  --model claude-opus-4-7 \
  --output-format text \
  > resume-claude.log 2>&1

echo "=== Claude session ended with exit code $? at $(date) ==="

# ---------- Step 2: verify all 200 images now covered ----------
echo "=== Step 2: checking coverage ==="
/opt/anaconda3/bin/python <<'EOF'
import pathlib
gold = set(p.stem for p in pathlib.Path("submission").glob("*.json"))
trial = set(p.stem for p in pathlib.Path("submission_trial").glob("*.json"))
have = gold | trial
needed = set(f"{i:04d}" for i in range(1, 201))
missing = sorted(needed - have)
print(f"gold: {len(gold)}, trial: {len(trial)}, combined: {len(have)}/200")
print(f"missing: {missing}")
EOF

# ---------- Step 3: merge gold + trial ----------
echo "=== Step 3: merging into submission_v2/ ==="
/opt/anaconda3/bin/python scripts/merge.py submission submission_trial submission_v2

# ---------- Step 4: validate all 200 ----------
echo "=== Step 4: RDKit + schema validation across all 200 ==="
/opt/anaconda3/bin/python scripts/validate.py submission_v2/*.json 2>&1 | tail -50
TOTAL_ERR=$(/opt/anaconda3/bin/python scripts/validate.py submission_v2/*.json 2>&1 | grep -c "ERROR")
echo "Total ERROR lines: $TOTAL_ERR"

# ---------- Step 5: score against the 10-image golden set ----------
echo "=== Step 5: scoring vs gold ==="
/opt/anaconda3/bin/python scripts/score.py submission_v2 submission

# ---------- Step 6: package submission.zip ----------
echo "=== Step 6: packaging final zip ==="
/opt/anaconda3/bin/python scripts/package.py submission_v2 submission_v2.zip
ls -la submission_v2.zip

echo "=== resume.sh complete at $(date) ==="
echo "Final artifacts:"
echo "  - $PROJ/submission_v2/      (200 JSONs)"
echo "  - $PROJ/submission_v2.zip   (final submission)"
echo "  - $PROJ/resume-claude.log   (Claude session log)"
echo "  - $LOG                      (master log)"
