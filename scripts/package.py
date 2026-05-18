#!/usr/bin/env python
"""Package a submission: copy meta.md + all per-image JSONs into a zip.

For images missing from the prediction dir, emit a stub {"reactions": []}
(better than missing — missing = 0 anyway per rules).

Usage: python scripts/package.py <pred_dir> <output_zip>
"""
import sys, json, pathlib, zipfile, shutil

def main():
    pred_dir = pathlib.Path(sys.argv[1])
    out_zip  = pathlib.Path(sys.argv[2])
    img_dir  = pathlib.Path("img")
    meta_path = pathlib.Path("meta.md")

    img_stems = [p.stem for p in sorted(img_dir.glob("*.png"))]
    print(f"Found {len(img_stems)} image stems")

    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        # meta.md
        if meta_path.exists():
            z.write(meta_path, "meta.md")
            print(f"  + meta.md")

        present = 0
        stubbed = 0
        for stem in img_stems:
            src = pred_dir / f"{stem}.json"
            if src.exists():
                z.write(src, f"{stem}.json")
                present += 1
            else:
                # write stub
                stub = json.dumps({"reactions": []}, indent=2, ensure_ascii=False)
                z.writestr(f"{stem}.json", stub)
                stubbed += 1
        print(f"  Files: {present} present, {stubbed} stubbed")
    print(f"Wrote {out_zip}")

if __name__ == "__main__":
    main()
