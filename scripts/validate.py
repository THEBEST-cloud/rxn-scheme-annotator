#!/usr/bin/env python
"""Validate a submission JSON: SMILES parse, schema, basic sanity checks."""
import json, sys, pathlib
from rdkit import Chem
from rdkit import RDLogger
RDLogger.DisableLog('rdApp.*')

VALID_TYPES = {"reactants", "reagent", "products", "temperature", "time", "other conditions"}
SMILES_TYPES = {"reactants", "reagent", "products"}

def validate_file(path):
    p = pathlib.Path(path)
    with open(p) as f:
        data = json.load(f)
    errors, warnings, info = [], [], []
    assert "reactions" in data, "missing top-level 'reactions' key"
    rxns = data["reactions"]
    info.append(f"# of reactions: {len(rxns)}")
    for i, rxn in enumerate(rxns):
        if not isinstance(rxn, list):
            errors.append(f"reaction[{i}] is not a list")
            continue
        types_found = set()
        for j, ent in enumerate(rxn):
            tag = f"rxn[{i}].entity[{j}]"
            if "type" not in ent or "text" not in ent:
                errors.append(f"{tag} missing type or text")
                continue
            if "relations" not in ent:
                errors.append(f"{tag} missing relations")
                continue
            if not isinstance(ent["relations"], list):
                errors.append(f"{tag} relations is not a list")
            t = ent["type"]
            if t not in VALID_TYPES:
                errors.append(f"{tag} bad type: {t!r}")
            types_found.add(t)
            if t in SMILES_TYPES:
                m = Chem.MolFromSmiles(ent["text"])
                if m is None:
                    errors.append(f"{tag} ({t}) SMILES failed to parse: {ent['text']}")
                else:
                    canon = Chem.MolToSmiles(m)
                    if canon != ent["text"]:
                        info.append(f"{tag} ({t}) non-canonical (ok): {ent['text']}  ->  {canon}")
        if "reactants" not in types_found:
            warnings.append(f"reaction[{i}] missing 'reactants'")
        if "products" not in types_found:
            warnings.append(f"reaction[{i}] missing 'products'")
    return errors, warnings, info

if __name__ == "__main__":
    paths = sys.argv[1:] or [str(p) for p in pathlib.Path("submission").glob("*.json")]
    total_err = 0
    for p in paths:
        print(f"\n=== {p} ===")
        try:
            errs, warns, infos = validate_file(p)
        except Exception as e:
            print(f"  FATAL: {e}")
            total_err += 1
            continue
        for line in infos: print("  ", line)
        for line in warns: print("  WARN:", line)
        for line in errs:  print("  ERROR:", line)
        if not errs:
            print(f"  -> {len(warns)} warnings, 0 errors")
        else:
            total_err += len(errs)
    sys.exit(0 if total_err == 0 else 1)
