#!/usr/bin/env python
"""Merge gold-labeled JSONs (preferred) with pipeline output for the rest.

Usage: python scripts/merge.py <gold_dir> <pipeline_dir> <merged_dir>
"""
import sys, json, pathlib, shutil

def main():
    gold = pathlib.Path(sys.argv[1])
    pipe = pathlib.Path(sys.argv[2])
    out  = pathlib.Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    img = pathlib.Path("img")
    n_gold = n_pipe = n_stub = 0
    for p in sorted(img.glob("*.png")):
        stem = p.stem
        src_gold = gold / f"{stem}.json"
        src_pipe = pipe / f"{stem}.json"
        if src_gold.exists():
            shutil.copy(src_gold, out / f"{stem}.json")
            n_gold += 1
        elif src_pipe.exists():
            shutil.copy(src_pipe, out / f"{stem}.json")
            n_pipe += 1
        else:
            (out / f"{stem}.json").write_text(json.dumps({"reactions":[]}, indent=2, ensure_ascii=False))
            n_stub += 1
    print(f"gold:{n_gold}  pipeline:{n_pipe}  stub:{n_stub}")

if __name__ == "__main__":
    main()
