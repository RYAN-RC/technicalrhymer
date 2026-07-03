#!/usr/bin/env python3
"""Build new-data.js: the top 2,000 highest-rated NEW words of the 2020s,
with approximate ARPABET pronunciations (g2p).

"New this decade" = the term is not in CMUdict (being in CMUdict proves it
predates 2020 — the dictionary was frozen well before), it has a definition
dated 2020-01-01 or later, and any PRE-2020 definitions are marginal:
max pre-2020 score <= max(20, 10% of its best 2020s score). A raw
earliest-definition rule is too brittle — "rizz" (Oxford 2023 WOTY) has a
junk 2015 nickname def scored -50 next to its 626-vote 2023 def, while
"karen" has a genuinely popular 392-vote def from 2010. The score-weighted
rule admits the former and excludes the latter. Still approximate: the
dataset is a scored sample (152k rows, 1999 -> Nov 2023).

Source: georgiyozhegov/urbandictionary-raw (Hugging Face) -> ud-raw.parquet.
  columns used: word, score (net votes), time (ISO 8601 string)

Output line format (../new-data.js, window.NEW_DATA):
  term \t phonemes \t zipf \t score \t year
- term      : lowercased headword/phrase
- phonemes  : ARPABET via g2p_en — ALWAYS auto-generated/approximate
- zipf      : commonality = max(real wordfreq, pseudo-from-votes)
- score     : Urban Dictionary net vote score
- year      : year of the earliest known definition (display: "since 2022")

Helpers (clean_term / pseudo_zipf / arpabet) mirror build_ud.py — the build
scripts in this directory are standalone by convention.
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
OUT = os.path.join(HERE, "..", "new-data.js")

TOP_N = 2000
DECADE_START = "2020-01-01"
PRE_MAX_ABS = 20    # pre-2020 defs scoring at or under this never disqualify
PRE_MAX_FRAC = 0.10 # ... nor does a pre-2020 peak under 10% of the 2020s peak

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


# ---- 1. per-term pre/post-2020 peak scores + earliest 2020s sighting ----
df = pd.read_parquet(PARQUET, columns=["word", "score", "time"])
pre = {}    # term -> max score among pre-2020 definitions
post = {}   # term -> max score among 2020+ definitions
first20 = {}  # term -> ISO time of earliest 2020+ definition
for w, s, tm in zip(df["word"].tolist(), df["score"].tolist(), df["time"].tolist()):
    t = clean_term(w)
    if t is None or not isinstance(tm, str) or not tm:
        continue
    s = int(s) if s is not None else 0
    if tm >= DECADE_START:  # ISO strings sort chronologically
        if t not in post or s > post[t]:
            post[t] = s
        if t not in first20 or tm < first20[t]:
            first20[t] = tm
    else:
        if t not in pre or s > pre[t]:
            pre[t] = s

print(f"distinct cleaned terms     : {len(set(pre) | set(post))}")
print(f"dataset time range         : {df['time'].min()} -> {df['time'].max()}")

# ---- 2. keep terms that belong to this decade: has a 2020s definition and
# any pre-2020 definitions are marginal (junk defs of the same string) ----
decade = {t for t, s in post.items()
          if t not in pre or pre[t] <= max(PRE_MAX_ABS, PRE_MAX_FRAC * s)}
print(f"defined 2020+, marginal pre: {len(decade)}")

# ---- 3. drop anything already in CMUdict (proves it predates 2020) ----
cmu_words = set()
with open(CMUDICT, "r", encoding="utf-8") as f:
    for line in f:
        tok = line.split(" ", 1)[0]
        if tok:
            cmu_words.add(alt_re.sub("", tok))

fresh = [t for t in decade if t not in cmu_words]
print(f"also not in CMUdict        : {len(fresh)}")

ranked = sorted(fresh, key=lambda t: post[t], reverse=True)[:TOP_N]
print(f"taking top                 : {len(ranked)}")
print(f"score at rank 1            : {post[ranked[0]]}  ({ranked[0]!r})")
print(f"score at rank {len(ranked)}        : {post[ranked[-1]]}  ({ranked[-1]!r})")

# ---- 4. approximate pronunciations: g2p, except vowel-less tokens (tds, smh)
# which g2p mangles — those are read as letter names ----
g2p = G2p()

LETTER = {
    "a": "EY1", "b": "B IY1", "c": "S IY1", "d": "D IY1", "e": "IY1",
    "f": "EH1 F", "g": "JH IY1", "h": "EY1 CH", "i": "AY1", "j": "JH EY1",
    "k": "K EY1", "l": "EH1 L", "m": "EH1 M", "n": "EH1 N", "o": "OW1",
    "p": "P IY1", "q": "K Y UW1", "r": "AA1 R", "s": "EH1 S", "t": "T IY1",
    "u": "Y UW1", "v": "V IY1", "w": "D AH1 B AH0 L Y UW0", "x": "EH1 K S",
    "y": "W AY1", "z": "Z IY1",
}
no_vowel = re.compile(r"^[b-df-hj-np-tv-xz]+$")  # letters only, no a/e/i/o/u/y


def arpabet(term):
    out = []
    for tok in term.split(" "):
        if no_vowel.match(tok):
            out.extend(LETTER[ch] for ch in tok)
            continue
        ph = [p for p in g2p(tok) if p.strip() and p != " "]
        out.extend(p for p in ph if re.match(r"^[A-Z]+[0-2]?$", p))
    return " ".join(out)


lines = []
for i, t in enumerate(ranked):
    ph = arpabet(t)
    if not ph:
        continue  # g2p produced nothing usable; skip
    z = max(zipf_frequency(t, "en"), pseudo_zipf(post[t]))
    year = int(first20[t][:4])  # first sighting this decade
    lines.append("%s\t%s\t%.2f\t%d\t%d" % (t, ph, z, post[t], year))
    if (i + 1) % 500 == 0:
        print(f"  g2p {i + 1}/{len(ranked)}")

blob = "\n".join(lines)
assert "`" not in blob and "${" not in blob, "unexpected template-literal char"

with open(OUT, "w", encoding="utf-8") as f:
    f.write("// New words of the 2020s: top-rated Urban Dictionary terms first (meaningfully)\n")
    f.write("// defined 2020+ and absent from CMUdict.\n")
    f.write("// Source dataset: georgiyozhegov/urbandictionary-raw (coverage through Nov 2023).\n")
    f.write("// Pronunciations via g2p_en — approximate. Format per line:\n")
    f.write("// term\\tARPABET\\tzipf\\tUDscore\\tfirstYear\n")
    f.write("window.NEW_DATA = `")
    f.write(blob)
    f.write("`;\n")

size_kb = os.path.getsize(OUT) / 1024
years = {}
for ln in lines:
    y = ln.rsplit("\t", 1)[1]
    years[y] = years.get(y, 0) + 1
print(f"written terms              : {len(lines)}")
print(f"by first-seen year         : {dict(sorted(years.items()))}")
print(f"output file                : {os.path.normpath(OUT)}")
print(f"output size                : {size_kb:.0f} KB")
