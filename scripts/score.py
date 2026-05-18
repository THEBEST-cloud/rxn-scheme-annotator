#!/usr/bin/env python
"""Score a predicted JSON against the golden-set JSON.

Match policy:
- An entity is "equal" if same type AND same SMILES skeleton (InChIKey first 14 chars)
  for SMILES types, or normalized string match for text types.
- Reactions are matched greedily by max-overlap of entities.
- Per-image score = (matched entities) / (max(pred entities, gold entities)) [Jaccard-ish]
- Print precision/recall/F1 across entity matches.
"""
import json, sys, pathlib, re
from rdkit import Chem
from rdkit import RDLogger
RDLogger.DisableLog('rdApp.*')

SMILES_TYPES = {"reactants", "reagent", "products"}

def inchi_skel(smi):
    if not smi: return None
    m = Chem.MolFromSmiles(smi)
    if m is None: return None
    try:
        return Chem.MolToInchiKey(m)[:14]
    except Exception:
        return None

def norm_text(s):
    return re.sub(r'\s+', '', s.lower())

def entity_key(ent):
    t = ent.get("type")
    text = ent.get("text", "")
    if t in SMILES_TYPES:
        return (t, inchi_skel(text))
    return (t, norm_text(text))

def reaction_entity_keys(rxn):
    return [entity_key(e) for e in rxn]

def best_match_score(pred_rxn, gold_rxn):
    pred_keys = reaction_entity_keys(pred_rxn)
    gold_keys = reaction_entity_keys(gold_rxn)
    pred_count = {}
    gold_count = {}
    for k in pred_keys: pred_count[k] = pred_count.get(k,0)+1
    for k in gold_keys: gold_count[k] = gold_count.get(k,0)+1
    matched = sum(min(pred_count.get(k,0), gold_count.get(k,0)) for k in gold_count)
    return matched, len(pred_keys), len(gold_keys)

def score_file(pred_path, gold_path):
    with open(pred_path) as f: pred = json.load(f)
    with open(gold_path) as f: gold = json.load(f)
    pred_rxns = pred.get("reactions", [])
    gold_rxns = gold.get("reactions", [])
    # Greedy match: for each gold reaction find best-match pred reaction
    used = set()
    total_match = total_pred = total_gold = 0
    for gr in gold_rxns:
        best = (-1, -1, 0, 0, 0)  # (matched, idx, pred_n, gold_n, _)
        for i, pr in enumerate(pred_rxns):
            if i in used: continue
            matched, pn, gn = best_match_score(pr, gr)
            if matched > best[0]:
                best = (matched, i, pn, gn, 0)
        if best[1] >= 0:
            used.add(best[1])
            total_match += best[0]
            total_pred += best[2]
            total_gold += best[3]
        else:
            total_gold += len(gr)
    # Unmatched pred reactions count as FP
    for i, pr in enumerate(pred_rxns):
        if i not in used:
            total_pred += len(pr)
    P = total_match / total_pred if total_pred else 0
    R = total_match / total_gold if total_gold else 0
    F = 2*P*R/(P+R) if (P+R) else 0
    return dict(matched=total_match, n_pred=total_pred, n_gold=total_gold,
                P=P, R=R, F=F,
                pred_rxns=len(pred_rxns), gold_rxns=len(gold_rxns))

if __name__ == "__main__":
    pred_dir = pathlib.Path(sys.argv[1] if len(sys.argv)>1 else "pipeline_out")
    gold_dir = pathlib.Path(sys.argv[2] if len(sys.argv)>2 else "submission")
    print(f"pred: {pred_dir}  gold: {gold_dir}")
    totals = {"matched":0, "n_pred":0, "n_gold":0}
    print(f"{'image':>10} {'pred_rxns':>10} {'gold_rxns':>10} {'matched':>8} {'P':>6} {'R':>6} {'F':>6}")
    for gp in sorted(gold_dir.glob("*.json")):
        pp = pred_dir / gp.name
        if not pp.exists():
            print(f"{gp.stem:>10}  MISSING in pred")
            continue
        s = score_file(pp, gp)
        for k in totals: totals[k] += s[k]
        print(f"{gp.stem:>10} {s['pred_rxns']:>10} {s['gold_rxns']:>10} {s['matched']:>8} {s['P']:>6.3f} {s['R']:>6.3f} {s['F']:>6.3f}")
    P = totals["matched"]/totals["n_pred"] if totals["n_pred"] else 0
    R = totals["matched"]/totals["n_gold"] if totals["n_gold"] else 0
    F = 2*P*R/(P+R) if (P+R) else 0
    print(f"{'TOTAL':>10} {'':>10} {'':>10} {totals['matched']:>8} {P:>6.3f} {R:>6.3f} {F:>6.3f}")
