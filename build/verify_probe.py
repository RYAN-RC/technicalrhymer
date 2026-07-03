#!/usr/bin/env python3
# Independently re-derive the probe's claimed evidence from the real data files,
# faithfully replicating app.js parse + search(mode="end") + dedupe + byCommon sort.
import re, sys

ROOT = r"C:\Users\ryanm\source\rhyme-finder"

def get_block(path, varname):
    with open(path, "r", encoding="utf-8") as f:
        s = f.read()
    # find the assignment, then the first backtick AFTER it (avoids backticks in comments)
    a = s.index(varname)
    i = s.index("`", a)
    j = s.index("`", i+1)
    return s[i+1:j]

freq_raw = get_block(ROOT + r"\freq-data.js", "window.CMU_FREQ")
data_raw = get_block(ROOT + r"\cmudict-data.js", "window.CMU_DATA")

# parseFreq: word\tzipf  (parseFloat)
freq = {}
for line in freq_raw.split("\n"):
    t = line.find("\t")
    if t < 0:
        continue
    try:
        freq[line[:t]] = float(line[t+1:])
    except ValueError:
        pass

def strip_stress(p):
    return re.sub(r"[0-2]", "", p)

# parseData: entries with key (with stress), keyNS (no stress), z
entries = []
for line in data_raw.split("\n"):
    t = line.find("\t")
    if t < 0:
        continue
    w = line[:t]
    p = line[t+1:]
    z = freq.get(w, 0)
    entries.append({"w": w, "p": p, "key": p, "keyNS": strip_stress(p), "z": z})

print("entries (pronunciations):", len(entries))
print("freq size:", len(freq))

# normalizeFragment: uppercase, split ws, optionally strip stress, join " "
def normalize(text, ignore_stress):
    toks = [t for t in text.upper().strip().split() if t]
    if ignore_stress:
        toks = [re.sub(r"[0-2]", "", t) for t in toks]
    return " ".join(toks)

# search mode "end": hay == frag OR hay.endswith(" "+frag); dedupe by word (first wins)
def search_end(frag, ignore_stress):
    seen = set()
    out = []
    for e in entries:
        hay = e["keyNS"] if ignore_stress else e["key"]
        if hay == frag or hay.endswith(" " + frag):
            if e["w"] not in seen:
                seen.add(e["w"])
                out.append(e)
    return out

def by_common_sorted(matches):
    # byCommon = (b.z - a.z) || alpha(a.w,b.w). Python: sort by (-z, w)
    return sorted(matches, key=lambda e: (-e["z"], e["w"]))

def analyze(label, frag_text, ignore_stress):
    frag = normalize(frag_text, ignore_stress)
    matches = search_end(frag, ignore_stress)
    sorted_m = by_common_sorted(matches)
    total = len(sorted_m)
    # first index where z == 0
    first_zero = next((i for i, e in enumerate(sorted_m) if e["z"] == 0), None)
    z_pos = sorted_m[:first_zero] if first_zero is not None else sorted_m
    n_zpos = len(z_pos)
    # count tied-with-a-neighbor among z>0 words (in final sorted order)
    tied = 0
    for i, e in enumerate(z_pos):
        prev_tie = i > 0 and z_pos[i-1]["z"] == e["z"]
        next_tie = i < n_zpos-1 and z_pos[i+1]["z"] == e["z"]
        if prev_tie or next_tie:
            tied += 1
    print(f"\n=== {label}  frag='{frag}' ignore_stress={ignore_stress} ===")
    print(f"  total matches (deduped by word): {total}")
    print(f"  first z==0 at position (0-based): {first_zero}  (1-based: {None if first_zero is None else first_zero+1})")
    print(f"  z>0 words: {n_zpos}")
    print(f"  of those, tied-with-neighbor (alpha-broken): {tied}")
    return {"total": total, "first_zero": first_zero, "n_zpos": n_zpos, "tied": tied,
            "sorted": sorted_m}

# Default UI: ignoreStress checkbox -- need to check index.html default. Probe phrases
# "IY(-ee)", "IH NG", "OW" are stress-stripped, so analyze with ignore_stress=True.
r_iy   = analyze("IY (-ee)", "IY", True)
r_ihng = analyze("IH NG",    "IH NG", True)
r_ow   = analyze("OW",       "OW", True)

# Also check whether the visible top (first RENDER_CAP=2500) is entirely z>0 for IY
RENDER_CAP = 2500
vis = r_iy["sorted"][:RENDER_CAP]
vis_zero = sum(1 for e in vis if e["z"] == 0)
print(f"\n[IY] of first {RENDER_CAP} shown, z==0 count: {vis_zero}  (0 => visible list entirely z>0)")
print(f"[IY] z at position {RENDER_CAP-1} (last visible): {vis[-1]['z']:.2f}  word={vis[-1]['w']}")

# Show the size of the largest tie band among z>0 for IY (illustrate 'very large tie bands')
from collections import Counter
band = Counter(e["z"] for e in r_iy["sorted"][:r_iy["first_zero"]])
top_bands = sorted(band.items(), key=lambda kv: -kv[1])[:5]
print(f"[IY] largest z-value tie bands among z>0 (zipf -> count): {top_bands}")

# ---- Alternative tie-count definitions to reconcile with probe's numbers ----
from collections import Counter
def tie_variants(label, r):
    zpos = r["sorted"][:r["first_zero"]]
    n = len(zpos)
    zs = [e["z"] for e in zpos]
    cnt = Counter(zs)
    # A: word is in a tie band of size>=2 (prev-or-next neighbor ties) -- already computed = r["tied"]
    a = r["tied"]
    # B: count of words that share z with >=1 other word, computed via band sizes (== A, sanity)
    b = sum(c for v, c in cnt.items() if c >= 2)
    # C: "redundant" ties = words minus number of distinct bands among the tied = sum(c-1) over bands size>=2
    c = sum(c - 1 for v, c in cnt.items() if c >= 2)
    # D: number of distinct z values that have >=2 words (number of tie bands)
    d = sum(1 for v, c in cnt.items() if c >= 2)
    # E: only "next neighbor ties" count
    e = sum(1 for i in range(n) if i < n-1 and zs[i] == zs[i+1])
    print(f"[{label}] z>0={n}  A(prev|next in band>=2)={a}  B(band-member)={b}  C(sum(c-1))={c}  D(#bands)={d}  E(next-ties)={e}")

tie_variants("IY", r_iy)
tie_variants("IH NG", r_ihng)
tie_variants("OW", r_ow)
