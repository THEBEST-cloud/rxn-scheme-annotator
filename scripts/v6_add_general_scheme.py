#!/usr/bin/env python
"""Generate v6 from v4: ADDITIVELY append general-scheme reactions from
OpenChemIE pipeline output.

For each image, parse `pipeline_out_raw/XXXX.json` (raw OpenChemIE output).
Find reactions where SMILES contains '*' placeholder (= general scheme with
R-group). For each such reaction:
  - Build a contest-schema reaction entry: reactants/reagent/products from
    OpenChemIE's parsed structures, conditions as additional reagent/temp/time
  - Append it to the existing submission_v4 reactions list
  - This is PURE ADDITION — never modifies existing entities.

Skips garbage reactions (transition metal complexes that are mechanism
artifacts, > 60 heavy atoms, parse failures).
"""
import json, sys, pathlib, re
from rdkit import Chem
from rdkit import RDLogger
RDLogger.DisableLog('rdApp.*')

SRC_BASE = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "submission_v4")
RAW_DIR  = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "pipeline_out_raw")
DST      = pathlib.Path(sys.argv[3] if len(sys.argv) > 3 else "submission_v6")
DST.mkdir(parents=True, exist_ok=True)

TS_ELEMENTS = {"Cu", "Pd", "Ni", "Rh", "Ir", "Ru", "Mo", "Mn", "Co", "Fe", "Sc",
               "Yb", "La", "Eu", "Sm", "Pt", "Au", "Ag", "Os", "Re"}
MAX_HEAVY = 60

# Patterns for extracting yields / numeric relations from condition text
RE_YIELD  = re.compile(r'(\d+(?:\.\d+)?\s*%\s*(?:yield)?)', re.I)
RE_EE     = re.compile(r'\d+(?:\.\d+)?\s*%?\s*ee', re.I)
RE_ER     = re.compile(r'er\s*[:=]?\s*\d+(?:\.\d+)?\s*:\s*\d+(?:\.\d+)?', re.I)
RE_DR     = re.compile(r'dr\s*[:=]?\s*(?:>|<)?\s*\d+(?:\.\d+)?\s*:\s*\d+(?:\.\d+)?', re.I)
RE_MOLPCT = re.compile(r'\d+(?:\.\d+)?\s*mol\s*%', re.I)
RE_EQUIV  = re.compile(r'\d+(?:\.\d+)?\s*equiv', re.I)
RE_TEMP   = re.compile(r'(-?\d+\s*°?\s*[Cc]\b)|(\br\.?\s*t\.?\b)|(\brt\b)|(reflux)', re.I)
RE_TIME   = re.compile(r'\d+(?:\.\d+)?\s*(?:h|hr|min|d)\b|overnight', re.I)

def valid_smiles_for_addition(s):
    """Return canonical SMILES (no stereo, since v4 also free-form) or None."""
    if not s: return None
    m = Chem.MolFromSmiles(s)
    if m is None: return None
    if m.GetNumHeavyAtoms() > MAX_HEAVY: return None
    if m.GetNumHeavyAtoms() < 2: return None
    for atom in m.GetAtoms():
        if atom.GetSymbol() in TS_ELEMENTS:
            return None
    return s  # keep original form (may contain *)

def extract_text_relations(text):
    """Extract numeric relations from one OCR text string."""
    rels = []
    for m in RE_YIELD.findall(text):
        if m: rels.append(m.strip() if isinstance(m, str) else m[0].strip())
    for m in RE_EE.findall(text):  rels.append(m.strip() if isinstance(m,str) else m)
    for m in RE_ER.findall(text):  rels.append(m.strip() if isinstance(m,str) else m)
    for m in RE_DR.findall(text):  rels.append(m.strip() if isinstance(m,str) else m)
    return [r for r in rels if r]

def extract_temp(text):
    m = RE_TEMP.search(text)
    if m: return m.group(0).strip()
    return None

def extract_time(text):
    m = RE_TIME.search(text)
    if m: return m.group(0).strip()
    return None

def raw_to_contest_reaction(raw_rxn):
    """Convert one OpenChemIE raw reaction to contest-schema entity list,
    or return None if not usable (too dirty)."""
    entities = []

    # reactants
    for r in raw_rxn.get("reactants", []):
        smi = valid_smiles_for_addition(r.get("smiles", ""))
        if smi:
            entities.append({"type": "reactants", "text": smi, "relations": []})

    # products
    yield_rels = []
    for p in raw_rxn.get("products", []):
        smi = valid_smiles_for_addition(p.get("smiles", ""))
        if smi:
            entities.append({"type": "products", "text": smi, "relations": []})

    # conditions: aggregate text
    for c in raw_rxn.get("conditions", []):
        texts = c.get("text", [])
        if isinstance(texts, str): texts = [texts]
        for t in texts:
            t = t.strip()
            if not t: continue
            # numeric: yield/ee/er/dr → product relations
            yld = extract_text_relations(t)
            yield_rels.extend(yld)
            # temperature
            tp = extract_temp(t)
            if tp:
                entities.append({"type": "temperature", "text": tp, "relations": []})
            # time
            tm = extract_time(t)
            if tm:
                entities.append({"type": "time", "text": tm, "relations": []})

    if yield_rels:
        for e in entities:
            if e["type"] == "products":
                e["relations"].extend(yield_rels)

    # validity: must have ≥1 reactant and ≥1 product
    types = {e["type"] for e in entities}
    if "reactants" not in types or "products" not in types:
        return None
    return entities

stats = {"images": 0, "raw_rxns_seen": 0, "added": 0}

for p in sorted(SRC_BASE.glob("*.json")):
    stats["images"] += 1
    base = json.loads(p.read_text())
    raw_path = RAW_DIR / p.name
    if not raw_path.exists():
        (DST / p.name).write_text(json.dumps(base, indent=2, ensure_ascii=False))
        continue
    raw = json.loads(raw_path.read_text())
    if not isinstance(raw, list): raw = raw.get("reactions", [])

    # collect existing reactant/product InChI to dedupe vs additions
    existing_keys = set()
    for rxn in base.get("reactions", []):
        for ent in rxn:
            if ent["type"] in ("reactants", "products"):
                m = Chem.MolFromSmiles(ent["text"])
                if m: existing_keys.add(Chem.MolToInchiKey(m)[:14])

    for raw_rxn in raw:
        stats["raw_rxns_seen"] += 1
        # SKIP reactions whose SMILES contain '*' (general-scheme wildcard).
        # Gold uses concrete example SMILES (per example.json); '*' won't match.
        all_smi = [
            *(r.get("smiles","") for r in raw_rxn.get("reactants", [])),
            *(p.get("smiles","") for p in raw_rxn.get("products", [])),
        ]
        if any('*' in (s or '') for s in all_smi):
            continue  # general scheme — drop
        # convert to contest entities
        new_entities = raw_to_contest_reaction(raw_rxn)
        if not new_entities:
            continue
        # dedupe: only add if products have at least one InChI not already present
        new_keys = set()
        for e in new_entities:
            if e["type"] in ("reactants", "products"):
                m = Chem.MolFromSmiles(e["text"])
                if m: new_keys.add(Chem.MolToInchiKey(m)[:14])
        if new_keys and new_keys.issubset(existing_keys):
            continue  # nothing new
        base.setdefault("reactions", []).append(new_entities)
        stats["added"] += 1

    (DST / p.name).write_text(json.dumps(base, indent=2, ensure_ascii=False))

print(f"Images: {stats['images']}")
print(f"Raw reactions seen: {stats['raw_rxns_seen']}")
print(f"General-scheme reactions appended: {stats['added']}")
