#!/usr/bin/env python3
"""Build ud-data.js: the top 10,000 highest-rated Urban Dictionary terms,
with ARPABET pronunciations (g2p) and a blended commonality score.

Source: georgiyozhegov/urbandictionary-raw (Hugging Face) -> ud-raw.parquet.
  columns: id, time, score (net up-minus-down votes), word, definition, example

Output line format (../ud-data.js, window.UD_DATA):
  term \t phonemes \t zipf \t score
- term      : lowercased headword/phrase (the lookup + display key)
- phonemes  : ARPABET; EMPTY when the term already exists in CMUdict
              (the app uses the CMU pronunciation in that case)
- zipf      : commonality on the Zipf scale = max(real wordfreq, pseudo-from-votes)
- score     : the Urban Dictionary net vote score (for display / attribution)

Attribution: every term here is surfaced in the UI as "from Urban Dictionary"
with a link to its definition page.
"""
import os
import re
import math
import pandas as pd
from wordfreq import zipf_frequency
from g2p_en import G2p

HERE = os.path.dirname(os.path.abspath(__file__))
PARQUET = os.path.join(HERE, "ud-raw.parquet")
CMUDICT = os.path.join(HERE, "cmudict.dict")
OUT = os.path.join(HERE, "..", "ud-data.js")

TOP_N = 10000

ok_re = re.compile(r"^[a-z0-9][a-z0-9 '.\-]*$")
has_letter = re.compile(r"[a-z]")
alt_re = re.compile(r"\(\d+\)$")


def clean_term(w):
    if not isinstance(w, str):
        return None
    t = w.strip().lower()
    t = re.sub(r"\s+", " ", t)
    if not (2 <= len(t) <= 30):
        return None
    if len(t.split(" ")) > 4:
        return None
    if not ok_re.match(t) or not has_letter.search(t):
        return None
    return t


def pseudo_zipf(score):
    """Map UD net votes into a modest Zipf band [1.0, 3.5] (log scale)."""
    s = score if score and score > 1 else 1
    return min(3.5, 1.0 + math.log10(s) * 0.6)


# ---- 1. load + rank UD terms (max score per distinct term) ----
df = pd.read_parquet(PARQUET, columns=["word", "score"])
best = {}
for w, s in zip(df["word"].tolist(), df["score"].tolist()):
    t = clean_term(w)
    if t is None:
        continue
    s = int(s) if s is not None else 0
    if t not in best or s > best[t]:
        best[t] = s

ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)[:TOP_N]
print(f"distinct cleaned terms : {len(best)}")
print(f"taking top             : {len(ranked)}")
print(f"score at rank 1        : {ranked[0][1]}  ({ranked[0][0]!r})")
print(f"score at rank {len(ranked)}    : {ranked[-1][1]}  ({ranked[-1][0]!r})")

# ---- 2. which terms already exist in CMUdict? ----
cmu_words = set()
with open(CMUDICT, "r", encoding="utf-8") as f:
    for line in f:
        tok = line.split(" ", 1)[0]
        if tok:
            cmu_words.add(alt_re.sub("", tok))

new_terms = [t for t, _ in ranked if t not in cmu_words]
print(f"already in CMUdict     : {len(ranked) - len(new_terms)}")
print(f"new (need g2p)         : {len(new_terms)}")

# ---- 3. g2p the new terms ----
g2p = G2p()


def arpabet(term):
    toks = [p for p in g2p(term) if p.strip() and p != " "]
    # keep only real ARPABET tokens (letters, optional trailing stress digit)
    toks = [p for p in toks if re.match(r"^[A-Z]+[0-2]?$", p)]
    return " ".join(toks)


prons = {}
for i, t in enumerate(new_terms):
    prons[t] = arpabet(t)
    if (i + 1) % 1000 == 0:
        print(f"  g2p {i + 1}/{len(new_terms)}")

# ---- 4. write ud-data.js ----
lines = []
for t, score in ranked:
    ph = "" if t in cmu_words else prons.get(t, "")
    if t not in cmu_words and not ph:
        continue  # g2p produced nothing usable; skip
    z = max(zipf_frequency(t, "en"), pseudo_zipf(score))
    lines.append("%s\t%s\t%.2f\t%d" % (t, ph, z, score))

blob = "\n".join(lines)
assert "`" not in blob and "${" not in blob, "unexpected template-literal char"

with open(OUT, "w", encoding="utf-8") as f:
    f.write("// Top-rated terms from Urban Dictionary (https://www.urbandictionary.com).\n")
    f.write("// Source dataset: georgiyozhegov/urbandictionary-raw. Pronunciations via g2p_en.\n")
    f.write("// Format per line: term\\tARPABET\\tzipf\\tUDscore  (ARPABET empty = use CMUdict pronunciation).\n")
    f.write("window.UD_DATA = `")
    f.write(blob)
    f.write("`;\n")

size_mb = os.path.getsize(OUT) / (1024 * 1024)
print(f"written terms          : {len(lines)}")
print(f"output file            : {os.path.normpath(OUT)}")
print(f"output size            : {size_mb:.2f} MB")
