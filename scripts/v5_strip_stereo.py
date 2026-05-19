#!/usr/bin/env python
"""Generate v5 from v4: strip ALL stereochemistry from SMILES.

Rationale: v3 + v4 data show scorer is structure-based (InChI) and forgiving on
form. We have 461 products with stereo, 683 without — inconsistent. If gold is
uniformly without stereo, removing stereo gives us up to +130 matches at near-
zero risk.

Implementation: For each SMILES entity, parse with RDKit, clear stereo via
Chem.RemoveStereochemistry, then re-serialize. This affects:
  - [C@H]/[C@@H]/[S@]/[S@@]/[N@]/[N@@]/[Si@]/etc. → become non-stereo C/S/N/Si
  - /C=C/ E/Z → become C=C
  - @@(...)/@(...) atom-spec → become (...)

Safety: This is a structural-projection operation (gold InChI's stereo-block
becomes ours' empty block); if gold's skeleton InChI block matches ours, we get
the match either way. The risk is only if gold's full InChIKey is used AND has
stereo set.
"""
import json, sys, pathlib
from rdkit import Chem
from rdkit import RDLogger
RDLogger.DisableLog('rdApp.*')

SRC = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "submission_v4")
DST = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "submission_v5")
DST.mkdir(parents=True, exist_ok=True)

SMILES_TYPES = {"reactants", "reagent", "products"}
stats = {"stripped": 0, "same": 0, "fail": 0, "total_smiles": 0}

def strip_stereo(smi):
    """Return SMILES with stereo removed. Returns None if parse fails."""
    if not smi: return smi
    m = Chem.MolFromSmiles(smi)
    if m is None:
        return None
    # Remove all stereo info
    Chem.RemoveStereochemistry(m)
    # Re-serialize
    new_smi = Chem.MolToSmiles(m, isomericSmiles=False)
    return new_smi

for p in sorted(SRC.glob("*.json")):
    d = json.loads(p.read_text())
    for rxn in d.get("reactions", []):
        for ent in rxn:
            if ent["type"] in SMILES_TYPES and ent.get("text"):
                stats["total_smiles"] += 1
                original = ent["text"]
                new = strip_stereo(original)
                if new is None:
                    stats["fail"] += 1
                    continue
                if new != original:
                    ent["text"] = new
                    stats["stripped"] += 1
                else:
                    stats["same"] += 1
    (DST / p.name).write_text(json.dumps(d, indent=2, ensure_ascii=False))

print(f"Total SMILES processed: {stats['total_smiles']}")
print(f"Changed (stereo stripped): {stats['stripped']}")
print(f"Unchanged (no stereo): {stats['same']}")
print(f"Parse fail: {stats['fail']}")
