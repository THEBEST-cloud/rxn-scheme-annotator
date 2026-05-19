#!/usr/bin/env python
"""Parse RxnIM text output → contest schema JSON.

RxnIM output format per image (concatenated):
  Reaction: 1
  Reactants: <SMILES>
  Conditions: <name>[reagent], <name>[solvent], <temp>[temperature], <yield>[yield]
  Products: <SMILES>
  Full Reaction: <SMILES> >> <SMILES> | <conditions>

  Reaction: 2
  ...

This script converts each Reaction block into our schema:
  [
    {"type":"reactants", "text":<smi>, "relations":[]},
    {"type":"reagent",   "text":<smi-or-name>, "relations":[]},
    {"type":"temperature","text":<temp>, "relations":[]},
    {"type":"products",  "text":<smi>, "relations":[<yield>]},
    ...
  ]

For 'name[role]' condition entries that aren't SMILES (e.g., 'Br2', 'Pyridine',
'THF/H2O'), we try (a) SMILES parse, (b) common-solvent dict, (c) keep as text.
"""
import re, sys, json, pathlib
from rdkit import Chem
from rdkit import RDLogger
RDLogger.DisableLog('rdApp.*')

SOLVENT_DICT = {
    'CH2Cl2':'ClCCl', 'DCM':'ClCCl', 'CH3CN':'CC#N', 'MeCN':'CC#N',
    'THF':'C1CCOC1', 'DMF':'CN(C)C=O', 'DMSO':'CS(C)=O',
    'EtOH':'CCO', 'MeOH':'CO', 'iPrOH':'CC(C)O', 'tBuOH':'CC(C)(C)O',
    't-BuOMe':'CC(C)(C)OC', 'MTBE':'CC(C)(C)OC', 'CPME':'COC1CCCC1',
    'Et2O':'CCOCC', 'dioxane':'C1COCCO1', '1,4-dioxane':'C1COCCO1',
    'toluene':'Cc1ccccc1', 'benzene':'c1ccccc1', 'AcOH':'CC(=O)O',
    'pentane':'CCCCC', 'hexane':'CCCCCC', 'H2O':'O', 'water':'O',
    'CHCl3':'ClC(Cl)Cl', 'EtOAc':'CCOC(=O)C', 'IPA':'CC(C)O',
    'DCE':'ClCCCl', 'NMP':'CN1CCCC1=O', 'DMA':'CN(C)C(C)=O',
    'Br2':'BrBr', 'Pyridine':'c1ccncc1',
}

RE_RXN_BLOCK = re.compile(r'Reaction:\s*\d+\s*\n', re.M)
RE_REACTANTS = re.compile(r'Reactants?:\s*(.+)', re.I)
RE_CONDITIONS = re.compile(r'Conditions?:\s*(.+)', re.I)
RE_PRODUCTS = re.compile(r'Products?:\s*(.+)', re.I)

# match "name[role]" — name can have parens, slashes, percent etc.
RE_COND_ENTRY = re.compile(r'([^,]+?)\[(\w+)\]', re.I)

def smiles_or_name_to_text(token):
    """Try to interpret token as SMILES; else look up in SOLVENT_DICT; else return text."""
    t = token.strip()
    m = Chem.MolFromSmiles(t)
    if m is not None and m.GetNumHeavyAtoms() > 0:
        return t  # valid SMILES
    # check solvent dict (case-sensitive then fuzzy)
    for k, smi in SOLVENT_DICT.items():
        if k.lower() == t.lower():
            return smi
    # try splitting "A/B" cosolvent
    if "/" in t:
        parts = [p.strip() for p in t.split("/")]
        smis = []
        for p in parts:
            m = Chem.MolFromSmiles(p)
            if m and m.GetNumHeavyAtoms() > 0:
                smis.append(p); continue
            for k, smi in SOLVENT_DICT.items():
                if k.lower() == p.lower():
                    smis.append(smi); break
        if smis:
            return ".".join(smis)
    # fallback: return as-is (will be rendered as text)
    return t

def parse_block(block):
    """Parse one Reaction block → list of contest entities."""
    entities = []
    yield_rels = []

    m = RE_REACTANTS.search(block)
    if m:
        for r_text in m.group(1).split('.'):  # RxnIM uses '.' to separate multiple reactants
            r = r_text.strip()
            if not r: continue
            mol = Chem.MolFromSmiles(r)
            if mol and mol.GetNumHeavyAtoms() > 0:
                entities.append({"type":"reactants", "text":r, "relations":[]})

    m = RE_PRODUCTS.search(block)
    if m:
        for p_text in m.group(1).split('.'):
            p = p_text.strip()
            if not p: continue
            mol = Chem.MolFromSmiles(p)
            if mol and mol.GetNumHeavyAtoms() > 0:
                entities.append({"type":"products", "text":p, "relations":[]})

    m = RE_CONDITIONS.search(block)
    if m:
        for token, role in RE_COND_ENTRY.findall(m.group(1)):
            token = token.strip()
            role = role.lower()
            if role == 'yield':
                # e.g., "68%[yield]"
                yield_rels.append(token if token.endswith("yield") else f"{token} yield" if "%" in token else token)
            elif role == 'temperature':
                entities.append({"type":"temperature", "text":token, "relations":[]})
            elif role == 'time':
                entities.append({"type":"time", "text":token, "relations":[]})
            elif role in ('reagent', 'catalyst', 'base', 'solvent', 'additive', 'oxidant', 'reductant'):
                txt = smiles_or_name_to_text(token)
                entities.append({"type":"reagent", "text":txt, "relations":[]})
            else:
                # unknown role: classify as other conditions
                entities.append({"type":"other conditions", "text":token, "relations":[]})

    if yield_rels:
        for e in entities:
            if e["type"] == "products":
                e["relations"].extend(yield_rels)

    # require ≥1 reactant + ≥1 product
    types = {e["type"] for e in entities}
    if "reactants" not in types or "products" not in types:
        return None
    return entities

def parse_image_output(text):
    """Parse full RxnIM output text → list of contest reactions."""
    blocks = re.split(r'(?=Reaction:\s*\d+)', text)
    reactions = []
    for b in blocks:
        b = b.strip()
        if not b or not b.startswith("Reaction"):
            continue
        ents = parse_block(b)
        if ents:
            reactions.append(ents)
    return reactions

if __name__ == "__main__":
    # demo
    import sys
    sample = """Reaction: 1
Reactants: CC(C)(C)OC(=O)N[C@H]1C=C[C@H](C(=O)O)C1
Conditions: Br2[reagent], Pyridine[reagent], DME/H2O[solvent], 0-5°C[temperature], 68%[yield]
Products: CC(C)(C)OC(=O)N[C@@H]1C[C@H]2C(=O)O[C@H]2[C@@H]1Br
Full Reaction: ..."""
    if len(sys.argv) > 1:
        text = pathlib.Path(sys.argv[1]).read_text()
    else:
        text = sample
    rxns = parse_image_output(text)
    print(json.dumps({"reactions": rxns}, indent=2, ensure_ascii=False))
