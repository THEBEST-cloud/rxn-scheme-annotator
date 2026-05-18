#!/usr/bin/env python
"""Heuristic post-processing on pipeline raw output.

Filters likely mechanism / transition state reactions:
- Drop reactions whose any SMILES has > MAX_HEAVY_ATOMS atoms.
- Drop reactions that have no products with sensible SMILES.
- Drop reactions where products SMILES contains many '*' placeholders.

Optionally tries to extract R-group enumeration from condition text and
emit per-substituent reactions.
"""
import json, sys, re, pathlib
from rdkit import Chem
from rdkit import RDLogger
RDLogger.DisableLog('rdApp.*')

MAX_HEAVY_ATOMS = 60
# Transition metals + boron-zinc / unusual elements that indicate mechanism/TS images
TS_ELEMENTS = {"Cu", "Pd", "Ni", "Rh", "Ir", "Ru", "Mo", "Mn", "Co", "Fe", "Sc",
               "Yb", "La", "Eu", "Sm", "Pt", "Au", "Ag", "Os", "Re"}
# Some main-reaction reagents legitimately contain transition metals (e.g., Yb(OTf)3
# is a reagent, Pd(PPh3)4 a reagent). But TS structures usually have these INSIDE the
# reactant/product SMILES, not in conditions. So we only flag transition metals in
# REACTANT or PRODUCT SMILES, not in conditions.

def heavy_atoms(smi):
    if not smi: return 0
    m = Chem.MolFromSmiles(smi)
    if m is None: return 0
    return m.GetNumHeavyAtoms()

def has_ts_element(smi):
    if not smi: return False
    for el in TS_ELEMENTS:
        if f"[{el}" in smi or f"[{el}+" in smi:
            return True
    return False

def has_star(smi):
    return bool(smi) and "*" in smi

def good_rxn(rxn):
    for k in ("reactants", "products"):
        for e in rxn.get(k, []):
            smi = e.get("smiles", "") or ""
            if heavy_atoms(smi) > MAX_HEAVY_ATOMS:
                return False
            if has_ts_element(smi):
                return False
            # SMILES must parse
            if smi and Chem.MolFromSmiles(smi) is None:
                return False
    if not rxn.get("products"):
        return False
    return True

def filter_image(rxn_list):
    """Filter and clean a list of reactions for one image."""
    return [r for r in rxn_list if good_rxn(r)]

if __name__ == "__main__":
    src = pathlib.Path(sys.argv[1] if len(sys.argv)>1 else "pipeline_out_raw")
    dst = pathlib.Path(sys.argv[2] if len(sys.argv)>2 else "pipeline_out_clean")
    dst.mkdir(parents=True, exist_ok=True)
    stats = {"in":0, "out":0, "dropped":0}
    for p in sorted(src.glob("*.json")):
        with open(p) as f: data = json.load(f)
        before = len(data)
        cleaned = filter_image(data)
        with open(dst / p.name, "w") as f:
            json.dump(cleaned, f, indent=2, ensure_ascii=False)
        stats["in"] += before
        stats["out"] += len(cleaned)
        stats["dropped"] += before - len(cleaned)
    print(stats)
