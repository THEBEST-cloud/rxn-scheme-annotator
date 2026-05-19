#!/usr/bin/env python
"""Fetch open-access source papers for contest images.

Pipeline:
  Image features (from Claude pre-described) → OpenAlex search →
  Crossref enrichment → Unpaywall OA lookup → Download PDF

For each image stem, we expect a `lit_queries/<stem>.json` file with:
  {"queries": ["search query 1", "..."], "must_contain": ["catalyst keywords"]}

Output:
  papers/<stem>/<doi_safe>.pdf — downloaded OA PDFs
  papers/<stem>/_candidates.json — all candidates with metadata
  papers/<stem>/_PAYWALLED.csv — paywalled candidates list

Usage:
  python scripts/lit_fetch.py <stem1> <stem2> ...
  python scripts/lit_fetch.py --all   # all stems in lit_queries/
"""
import sys, os, time, json, csv, re
import requests
from pathlib import Path
import argparse

ROOT = Path(__file__).parent.parent
PAPERS_ROOT = ROOT / "papers"
LIT_QUERIES = ROOT / "lit_queries"
UA = "rxn-anno/1.0 (research; FjgracieannnFU@columnist.com)"
HEADERS = {"User-Agent": UA}
EMAIL = "research@local"

def reconstruct_abstract(inv_idx):
    if not inv_idx: return ""
    pairs = [(pos, w) for w, positions in inv_idx.items() for pos in positions]
    pairs.sort()
    return " ".join(w for _, w in pairs)

def doi_to_filename(doi):
    return doi.replace("/", "_") + ".pdf"

def validate_pdf(path):
    try:
        from pypdf import PdfReader
        rdr = PdfReader(str(path))
        if len(rdr.pages) < 1:
            return False
        try:
            txt = rdr.pages[0].extract_text() or ""
        except Exception:
            txt = ""
        return len(txt.strip()) > 20 or len(rdr.pages) >= 2
    except Exception as e:
        print(f"     pdf invalid: {e}")
        return False

def try_download(url, dest):
    try:
        r = requests.get(url, headers=HEADERS, timeout=60, allow_redirects=True)
        if r.status_code != 200:
            print(f"     HTTP {r.status_code}"); return False
        ctype = r.headers.get("Content-Type", "").lower()
        content = r.content
        if len(content) < 5000:
            return False
        if b"%PDF" not in content[:2048] and "pdf" not in ctype:
            print(f"     not a pdf ({ctype})"); return False
        with open(dest, "wb") as f:
            f.write(content)
        if validate_pdf(dest):
            return True
        else:
            dest.unlink(missing_ok=True)
            return False
    except Exception as e:
        print(f"     err: {e}")
        try: dest.unlink(missing_ok=True)
        except Exception: pass
        return False

def fetch_for_stem(stem, cfg):
    out_dir = PAPERS_ROOT / stem
    out_dir.mkdir(parents=True, exist_ok=True)

    candidates = {}
    def add_cand(doi, title, year, abstract, pdf_url, is_oa, venue, source):
        if not doi: return
        doi = doi.lower().replace("https://doi.org/", "")
        if doi in candidates:
            if pdf_url and not candidates[doi].get("pdf_url"):
                candidates[doi]["pdf_url"] = pdf_url
                candidates[doi]["is_oa"] = is_oa
            return
        candidates[doi] = {
            "doi": doi, "title": title or "", "year": year, "abstract": abstract or "",
            "pdf_url": pdf_url, "is_oa": is_oa, "venue": venue or "", "source": source
        }

    # OpenAlex
    for q in cfg.get("queries", []):
        print(f"  [OA] {q[:80]}")
        try:
            r = requests.get("https://api.openalex.org/works",
                             params={"search": q, "per-page": 50, "sort": "cited_by_count:desc", "mailto": EMAIL},
                             headers=HEADERS, timeout=30)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"    err: {e}"); continue
        for w in data.get("results", []):
            doi = w.get("doi") or ""
            title = w.get("title") or ""
            year = w.get("publication_year")
            abs_txt = reconstruct_abstract(w.get("abstract_inverted_index"))
            best = w.get("best_oa_location") or {}
            pdf_url = best.get("pdf_url") if best else None
            is_oa = (w.get("open_access") or {}).get("is_oa", False)
            primary = w.get("primary_location") or {}
            venue = (primary.get("source") or {}) if primary else {}
            venue_name = venue.get("display_name") if venue else ""
            add_cand(doi, title, year, abs_txt, pdf_url, is_oa, venue_name, "openalex")
        time.sleep(0.3)

    print(f"  candidates from search: {len(candidates)}")

    # Filter by must_contain (in title or abstract)
    must = [k.lower() for k in cfg.get("must_contain", [])]
    def is_relevant(rec):
        if not must: return True
        t = (rec["title"] or "").lower()
        a = (rec["abstract"] or "").lower()
        return any(n in t or n in a for n in must)

    relevant = {d: r for d, r in candidates.items() if is_relevant(r)}
    print(f"  relevant by keyword: {len(relevant)}")

    # Prioritize: OA first, recent first
    items = list(relevant.items())
    items.sort(key=lambda kv: (0 if kv[1].get("pdf_url") else 1, -(kv[1].get("year") or 0)))
    items = items[:20]  # top 20

    cat_path = out_dir / "_candidates.json"
    with open(cat_path, "w") as f:
        json.dump({d: r for d, r in items}, f, indent=2, ensure_ascii=False)

    # Try Unpaywall + download
    downloaded = []
    paywalled = []
    for doi, rec in items:
        if len(downloaded) >= 10:
            paywalled.append(rec)
            continue
        fname = doi_to_filename(doi)
        dest = out_dir / fname
        if dest.exists():
            downloaded.append(rec); continue
        ok = False
        pdf_url = rec.get("pdf_url")
        if pdf_url:
            ok = try_download(pdf_url, dest)
        if not ok:
            # Unpaywall fallback
            try:
                ur = requests.get(f"https://api.unpaywall.org/v2/{doi}",
                                  params={"email": EMAIL}, headers=HEADERS, timeout=20)
                if ur.status_code == 200:
                    ud = ur.json()
                    loc = ud.get("best_oa_location") or {}
                    up_pdf = loc.get("url_for_pdf") or loc.get("url")
                    if up_pdf:
                        ok = try_download(up_pdf, dest)
            except Exception as e:
                pass
        if ok:
            downloaded.append(rec)
            print(f"    DL OK: {doi}")
        else:
            paywalled.append(rec)
        time.sleep(0.3)

    print(f"  → downloaded {len(downloaded)}, paywalled {len(paywalled)}")
    if paywalled:
        with open(out_dir / "_PAYWALLED.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["doi", "title", "year", "venue"])
            for rec in paywalled:
                w.writerow([rec["doi"], rec["title"], rec["year"], rec["venue"]])
    return len(downloaded), len(paywalled)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stems", nargs="*", help="image stems to fetch (e.g., 0001 0010 ...)")
    ap.add_argument("--all", action="store_true", help="process all stems in lit_queries/")
    args = ap.parse_args()

    LIT_QUERIES.mkdir(parents=True, exist_ok=True)
    PAPERS_ROOT.mkdir(parents=True, exist_ok=True)

    if args.all:
        stems = sorted(p.stem for p in LIT_QUERIES.glob("*.json"))
    else:
        stems = args.stems

    if not stems:
        print("No stems given. Run with --all or pass stems explicitly.")
        return

    summary = {}
    for stem in stems:
        qpath = LIT_QUERIES / f"{stem}.json"
        if not qpath.exists():
            print(f"[{stem}] no query file at {qpath}, skipping")
            continue
        cfg = json.loads(qpath.read_text())
        print(f"\n=== {stem} ===")
        dl, pw = fetch_for_stem(stem, cfg)
        summary[stem] = (dl, pw)

    print(f"\n=== SUMMARY ===")
    for k, (dl, pw) in summary.items():
        print(f"  {k}: dl={dl} paywall={pw}")
    if summary:
        dls = sum(dl for dl, _ in summary.values())
        pws = sum(pw for _, pw in summary.values())
        print(f"\nTotal: {dls} downloaded, {pws} paywalled, OA rate {100*dls/(dls+pws):.1f}%")

if __name__ == "__main__":
    main()
