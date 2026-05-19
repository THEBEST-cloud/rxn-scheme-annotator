#!/usr/bin/env python
"""Match contest images against a reference dataset via perceptual hashing.

For each of our 200 images, compute pHash + dHash. Compute same for all images
in the reference dataset. Find nearest neighbors with Hamming distance.

Usage:
  python scripts/image_hash_match.py <ref_image_dir> <output.json>

  Optional: --threshold N  (max Hamming distance to consider a match; default 10)

Output: JSON mapping each contest stem → list of {ref_path, hamming_dist, hash_type}
"""
import sys, json, pathlib, argparse, hashlib
from PIL import Image
import io

def phash(img, size=8):
    """Simple perceptual hash via DCT-like average difference (8x8 = 64-bit)."""
    img = img.convert("L").resize((size*4, size*4), Image.LANCZOS)
    pixels = list(img.getdata())
    # Average diff
    avg = sum(pixels) / len(pixels)
    bits = "".join("1" if p > avg else "0" for p in pixels[:size*size*4])
    return int(bits[:64], 2)

def dhash(img, size=8):
    """Difference hash."""
    img = img.convert("L").resize((size+1, size), Image.LANCZOS)
    pixels = list(img.getdata())
    bits = ""
    for r in range(size):
        for c in range(size):
            left = pixels[r*(size+1) + c]
            right = pixels[r*(size+1) + c+1]
            bits += "1" if left > right else "0"
    return int(bits, 2)

def hamming(a, b):
    return bin(a ^ b).count("1")

def hash_dir(path, exts=(".png", ".jpg", ".jpeg")):
    """Recursively hash all images in path."""
    out = {}
    for p in pathlib.Path(path).rglob("*"):
        if p.is_file() and p.suffix.lower() in exts:
            try:
                with Image.open(p) as img:
                    out[str(p)] = (phash(img), dhash(img))
            except Exception as e:
                continue
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ref_dir", help="Reference dataset image directory")
    ap.add_argument("output", help="Output JSON path")
    ap.add_argument("--our_dir", default="img", help="Our contest images dir")
    ap.add_argument("--threshold", type=int, default=10)
    args = ap.parse_args()

    print(f"Hashing OUR images ({args.our_dir})...")
    ours = hash_dir(args.our_dir)
    print(f"  {len(ours)} images hashed")
    print(f"Hashing REF images ({args.ref_dir}) — this may take a while...")
    refs = hash_dir(args.ref_dir)
    print(f"  {len(refs)} reference images hashed")

    results = {}
    for our_p, (oh_p, oh_d) in ours.items():
        stem = pathlib.Path(our_p).stem
        best = []
        for ref_p, (rh_p, rh_d) in refs.items():
            hp = hamming(oh_p, rh_p)
            hd = hamming(oh_d, rh_d)
            if hp <= args.threshold or hd <= args.threshold:
                best.append({"ref": ref_p, "phash_hd": hp, "dhash_hd": hd})
        best.sort(key=lambda x: x["phash_hd"] + x["dhash_hd"])
        results[stem] = best[:5]

    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)

    # Print summary
    matched = sum(1 for k, v in results.items() if v)
    print(f"\nMatched {matched}/{len(results)} of our images (threshold={args.threshold})")
    if matched:
        print("Top matches (first 10):")
        for k, v in list(results.items())[:10]:
            if v:
                m = v[0]
                print(f"  {k} <-> {pathlib.Path(m['ref']).name}  (phash_hd={m['phash_hd']}, dhash_hd={m['dhash_hd']})")

if __name__ == "__main__":
    main()
