#!/usr/bin/env python
"""Run OpenChemIE on all 200 images. Save raw output as JSON per image.

Usage:
    python scripts/run_pipeline.py [img_dir] [out_dir]

Defaults: img_dir=img/  out_dir=pipeline_out_raw/
"""
import sys, os, json, pathlib, time, traceback

# Pin GPU 2 (empty per earlier check); leave 4090s 0/1/3/4/5/6/7 for vLLM.
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "2")

import cv2
import torch
from openchemie import OpenChemIE

def numpy_to_jsonable(obj):
    """Recursively convert numpy types and tuples to JSON-serializable forms."""
    if isinstance(obj, dict):
        return {k: numpy_to_jsonable(v) for k, v in obj.items() if k != "image" and k != "figure"}
    if isinstance(obj, (list, tuple)):
        return [numpy_to_jsonable(x) for x in obj]
    try:
        import numpy as np
        if isinstance(obj, np.generic):
            return obj.item()
        if isinstance(obj, np.ndarray):
            return obj.tolist()
    except Exception:
        pass
    return obj

def main():
    img_dir = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "img")
    out_dir = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "pipeline_out_raw")
    out_dir.mkdir(parents=True, exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Loading OpenChemIE on {device}...")
    model = OpenChemIE(device=device)
    print("Model loaded.")

    img_paths = sorted(img_dir.glob("*.png"))
    print(f"Processing {len(img_paths)} images...")

    t0 = time.time()
    for i, p in enumerate(img_paths):
        out_path = out_dir / f"{p.stem}.json"
        if out_path.exists():
            continue
        try:
            img = cv2.imread(str(p))
            results = model.extract_reactions_from_figures([img], batch_size=1, molscribe=True, ocr=True)
            # results = [{'figure':..., 'reactions':[...]}]
            rxns = results[0].get("reactions", []) if results else []
            with open(out_path, "w") as f:
                json.dump(numpy_to_jsonable(rxns), f, indent=2, ensure_ascii=False)
            print(f"[{i+1}/{len(img_paths)}] {p.name}: {len(rxns)} reactions  ({time.time()-t0:.1f}s elapsed)")
        except Exception as e:
            print(f"[{i+1}/{len(img_paths)}] {p.name}: FAILED — {e}")
            traceback.print_exc()
            # Continue with next image
            continue
    print(f"Done in {time.time()-t0:.1f}s")

if __name__ == "__main__":
    main()
