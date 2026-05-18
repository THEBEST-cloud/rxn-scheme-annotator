#!/usr/bin/env python
"""Canonicalize all SMILES via RDKit and normalize text fields.
Creates submission_v3/ from submission_v2/.
"""
import json, sys, re, pathlib, shutil
from rdkit import Chem
from rdkit import RDLogger
RDLogger.DisableLog('rdApp.*')

SRC = pathlib.Path(sys.argv[1] if len(sys.argv)>1 else "submission_v2")
DST = pathlib.Path(sys.argv[2] if len(sys.argv)>2 else "submission_v3")
DST.mkdir(parents=True, exist_ok=True)

SMILES_TYPES = {"reactants", "reagent", "products"}
stats = {"canon": 0, "same": 0, "fail": 0, "norm_temp": 0, "norm_time": 0}

def normalize_temp(t):
    s = t.strip()
    # Normalize various rt forms
    if re.fullmatch(r'r\.?\s*t\.?', s, re.I): return "r.t."
    if re.fullmatch(r'room\s*temp(?:erature)?', s, re.I): return "r.t."
    # Normalize °C spacing
    m = re.fullmatch(r'(-?\d+(?:\.\d+)?)\s*°?\s*[Cc]', s)
    if m: return f"{m.group(1)} °C"
    # range like -25 to 25 °C
    m = re.fullmatch(r'(-?\d+(?:\.\d+)?)\s*(?:to|~|-)\s*(-?\d+(?:\.\d+)?)\s*°?\s*[Cc]', s)
    if m: return f"{m.group(1)} to {m.group(2)} °C"
    return s

def normalize_time(t):
    s = t.strip()
    m = re.fullmatch(r'(\d+(?:\.\d+)?)\s*h', s, re.I)
    if m: return f"{m.group(1)} h"
    m = re.fullmatch(r'(\d+(?:\.\d+)?)\s*min', s, re.I)
    if m: return f"{m.group(1)} min"
    m = re.fullmatch(r'overnight', s, re.I)
    if m: return "overnight"
    # range
    m = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(?:to|~|-)\s*(\d+(?:\.\d+)?)\s*h', s, re.I)
    if m: return f"{m.group(1)}-{m.group(2)} h"
    return s

for p in sorted(SRC.glob("*.json")):
    d = json.loads(p.read_text())
    for rxn in d.get("reactions", []):
        for ent in rxn:
            t = ent["type"]
            txt = ent.get("text", "")
            if t in SMILES_TYPES and txt:
                m = Chem.MolFromSmiles(txt)
                if m is None:
                    stats["fail"] += 1
                    continue
                canon = Chem.MolToSmiles(m)
                if canon != txt:
                    ent["text"] = canon
                    stats["canon"] += 1
                else:
                    stats["same"] += 1
            elif t == "temperature":
                new = normalize_temp(txt)
                if new != txt:
                    ent["text"] = new
                    stats["norm_temp"] += 1
            elif t == "time":
                new = normalize_time(txt)
                if new != txt:
                    ent["text"] = new
                    stats["norm_time"] += 1
    (DST / p.name).write_text(json.dumps(d, indent=2, ensure_ascii=False))

print(f"canonicalized: {stats['canon']}, already canonical: {stats['same']}, parse fail: {stats['fail']}")
print(f"normalized temperature: {stats['norm_temp']}, time: {stats['norm_time']}")
