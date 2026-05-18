#!/usr/bin/env python
"""Convert OpenChemIE raw output → contest JSON schema.

Input shape (per reaction):
  {
    'reactants': [{'category','bbox','smiles','molfile'}, ...],
    'conditions': [{'category','bbox','text': [str, ...]}, ...],
    'products':  [{'category','bbox','smiles','molfile'}, ...]
  }

Output (contest schema, per image):
  {"reactions": [
     [{"type": "reactants"|"reagent"|"products"|"temperature"|"time"|"other conditions",
       "text": "<SMILES or text>",
       "relations": [...]
      }, ...],
    ...
  ]}
"""
import json, sys, re, pathlib
from rdkit import Chem
from rdkit import RDLogger
RDLogger.DisableLog('rdApp.*')

# --- text extraction patterns ---
RE_YIELD       = re.compile(r'(\d+(?:\.\d+)?\s*%\s*(?:yield|y\.?\s*)?)|(up\s+to\s+\d+\s*%)', re.I)
RE_EE          = re.compile(r'\d+(?:\.\d+)?\s*%\s*ee', re.I)
RE_ER          = re.compile(r'er\s*[:=]?\s*\d+(?:\.\d+)?\s*:\s*\d+(?:\.\d+)?', re.I)
RE_DR          = re.compile(r'dr\s*[:=]?\s*(?:>|<)?\s*\d+(?:\.\d+)?\s*:\s*\d+(?:\.\d+)?', re.I)
RE_MOLPCT      = re.compile(r'\d+(?:\.\d+)?\s*mol\s*%', re.I)
RE_EQUIV       = re.compile(r'\d+(?:\.\d+)?\s*equiv', re.I)
RE_TEMP        = re.compile(r'(-?\d+\s*°?\s*C)|(r\.?\s*t\.?)|(rt)|(room\s+temp)', re.I)
RE_TIME        = re.compile(r'\d+(?:\.\d+)?\s*(?:h|hr|hour|min|d|days?)|overnight', re.I)
RE_MICROWAVE   = re.compile(r'(microwave|mw|sonication|reflux|degassed|N2|Ar\b)', re.I)

# Common solvent names → SMILES
SOLVENT_DICT = {
    'CH2Cl2':'ClCCl', 'DCM':'ClCCl', 'CH3CN':'CC#N', 'MeCN':'CC#N',
    'THF':'C1CCOC1', 'DMF':'CN(C)C=O', 'DMSO':'CS(C)=O',
    'EtOH':'CCO', 'MeOH':'CO', 'iPrOH':'CC(C)O', 'tBuOH':'CC(C)(C)O',
    't-BuOMe':'CC(C)(C)OC', 'MTBE':'CC(C)(C)OC',
    'Et2O':'CCOCC', 'dioxane':'C1COCCO1', '1,4-dioxane':'C1COCCO1',
    'toluene':'Cc1ccccc1', 'benzene':'c1ccccc1', 'AcOH':'CC(=O)O',
    'CPME':'COC1CCCC1', 'cyclopentyl methyl ether':'COC1CCCC1',
    'pentane':'CCCCC', 'hexane':'CCCCCC', 'H2O':'O', 'water':'O',
    'CHCl3':'ClC(Cl)Cl', 'EtOAc':'CCOC(=O)C',
}

def valid_smiles(s):
    if not s: return None
    m = Chem.MolFromSmiles(s)
    if m is None: return None
    return s  # keep original (canonical not required by spec)

def extract_yield_ee(text):
    """Pull yield/ee/er/dr from text → returns list of relation strings."""
    rels = []
    for r in RE_YIELD.findall(text):
        for g in r:
            if g: rels.append(g.strip())
    for m in RE_EE.findall(text): rels.append(m.strip())
    for m in RE_ER.findall(text): rels.append(m.strip())
    for m in RE_DR.findall(text): rels.append(m.strip())
    return rels

def classify_condition_text(t):
    """Return list of (type, text, relations) entities from one condition string."""
    out = []
    t = t.strip()
    if not t: return out
    # Temperature
    tm = RE_TEMP.search(t)
    if tm:
        out.append(("temperature", tm.group(0).strip(), []))
    # Time
    tm = RE_TIME.search(t)
    if tm:
        out.append(("time", tm.group(0).strip(), []))
    # Solvent / reagent name → SMILES via dict
    for name, smi in SOLVENT_DICT.items():
        if re.search(rf'\b{re.escape(name)}\b', t, re.I):
            out.append(("reagent", smi, []))
            break
    # Catalyst loading (mol%)
    m = RE_MOLPCT.search(t)
    if m:
        # Attach to last reagent if any, else add as "other conditions"
        if out and out[-1][0] == "reagent":
            out[-1] = (out[-1][0], out[-1][1], out[-1][2] + [m.group(0).strip()])
        else:
            out.append(("other conditions", t, []))
    # Equiv
    m = RE_EQUIV.search(t)
    if m:
        if out and out[-1][0] == "reagent":
            out[-1] = (out[-1][0], out[-1][1], out[-1][2] + [m.group(0).strip()])
    return out

def convert_reaction(rxn):
    """Convert one OpenChemIE reaction dict → list of contest entities."""
    entities = []
    yield_relations = []  # accumulate for products

    # reactants
    for r in rxn.get('reactants', []):
        smi = valid_smiles(r.get('smiles'))
        if smi:
            entities.append({"type": "reactants", "text": smi, "relations": []})

    # products
    for p in rxn.get('products', []):
        smi = valid_smiles(p.get('smiles'))
        if smi:
            # collect yield/ee/er/dr from any condition text that mentions them
            # (we will attach below)
            entities.append({"type": "products", "text": smi, "relations": []})

    # conditions
    for cond in rxn.get('conditions', []):
        texts = cond.get('text', [])
        if isinstance(texts, str): texts = [texts]
        for t in texts:
            # try parse SMILES first (some conditions may be SMILES of reagents)
            smi = valid_smiles(t)
            if smi:
                entities.append({"type": "reagent", "text": smi, "relations": []})
                continue
            # extract yield/ee/er/dr → attach to products
            yld = extract_yield_ee(t)
            yield_relations.extend(yld)
            # classify remaining text
            sub_ents = classify_condition_text(t)
            for typ, txt, rels in sub_ents:
                entities.append({"type": typ, "text": txt, "relations": rels})

    # attach yield/ee/er/dr to ALL products
    if yield_relations:
        for e in entities:
            if e["type"] == "products":
                e["relations"].extend(yield_relations)

    return entities

def convert_image_output(rxn_list):
    """Top-level: list of reaction dicts → contest JSON."""
    contest = {"reactions": []}
    for r in rxn_list:
        ents = convert_reaction(r)
        # Require at least one reactant and one product
        types = {e["type"] for e in ents}
        if "reactants" in types and "products" in types:
            contest["reactions"].append(ents)
    return contest

if __name__ == "__main__":
    src = pathlib.Path(sys.argv[1])  # raw pipeline output dir (1 json/image)
    dst = pathlib.Path(sys.argv[2])  # output dir
    dst.mkdir(parents=True, exist_ok=True)
    for p in sorted(src.glob("*.json")):
        with open(p) as f:
            raw = json.load(f)
        out = convert_image_output(raw if isinstance(raw, list) else raw.get("reactions", []))
        with open(dst / p.name, "w") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
        print(f"{p.name}: {len(out['reactions'])} reactions")
