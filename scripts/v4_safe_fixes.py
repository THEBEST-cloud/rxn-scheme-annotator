#!/usr/bin/env python
"""Generate v4 from v2: SAFE text-only fixes based on example.json style.

Changes:
  1. temperature 'r.t.' / 'r.t' / 'room temperature' → 'rt' (per example.json)
  2. Remove descriptive label relations: 'ligand', 'L', 'L1'..'Ln',
     'catalyst A/B/...', 'catalyst 1/2/...', 'method A/B', 'ligand 1/2',
     and any text that looks like a chemical name (PhMe/DCE/etc.) when
     present alongside numeric value relations on same entity.
  3. Strip empty relation strings.

NO SMILES modifications. NO entity removals/additions.
"""
import json, sys, re, pathlib

SRC = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "submission_v2")
DST = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "submission_v4")
DST.mkdir(parents=True, exist_ok=True)

# Patterns of descriptive (non-quantity) relation strings to drop.
# Match exact (case-insensitive). Numeric / R-list relations are kept.
DROP_EXACT = {
    "ligand", "ligand 1", "ligand 2", "ligand 3",
    "L", "L1", "L2", "L3", "L4", "L5",
    "catalyst", "catalyst A", "catalyst B", "catalyst C", "catalyst D",
    "catalyst 1", "catalyst 2", "catalyst 3", "catalyst 4",
    "method A", "method B", "method C",
    "Cat. A", "Cat. B", "Cat A", "Cat B",
    "Cat", "cat.",
    "additive",
}

# Things that look like compound labels in parentheses (e.g., "compound 1")
DROP_PATTERN = re.compile(
    r'^(compound|product|complex|cat\.?)\s*\d+[a-z]?$|'
    r'^\([RS]\)$|'             # (R) or (S) descriptors
    r'^[A-Z]\d?$',             # single letter labels like "A", "B1"
    re.I,
)

stats = {"temp_norm": 0, "rel_dropped": 0, "entities": 0}

def fix_temp(txt):
    s = txt.strip()
    if re.fullmatch(r'r\.?\s*t\.?', s, re.I): return "rt"
    if re.fullmatch(r'room\s*temp(?:erature)?', s, re.I): return "rt"
    return txt

def fix_relations(rels):
    out = []
    for r in rels:
        rs = r.strip()
        if not rs:
            continue  # drop empty
        if rs.lower() in (x.lower() for x in DROP_EXACT):
            stats["rel_dropped"] += 1
            continue
        if DROP_PATTERN.match(rs):
            stats["rel_dropped"] += 1
            continue
        out.append(rs)
    return out

for p in sorted(SRC.glob("*.json")):
    d = json.loads(p.read_text())
    for rxn in d.get("reactions", []):
        for ent in rxn:
            stats["entities"] += 1
            t = ent["type"]
            if t == "temperature":
                new_txt = fix_temp(ent.get("text", ""))
                if new_txt != ent["text"]:
                    ent["text"] = new_txt
                    stats["temp_norm"] += 1
            ent["relations"] = fix_relations(ent.get("relations", []))
    (DST / p.name).write_text(json.dumps(d, indent=2, ensure_ascii=False))

print(f"Processed: {stats['entities']} entities")
print(f"Temperature normalized (→ 'rt'): {stats['temp_norm']}")
print(f"Descriptive relations dropped:   {stats['rel_dropped']}")
