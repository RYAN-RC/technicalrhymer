#!/usr/bin/env python3
"""Build ud-data.js: the top 10,000 highest-rated Urban Dictionary terms,
plus a commonality rescue, with ARPABET pronunciations (g2p) and a blended
commonality score.

Source: georgiyozhegov/urbandictionary-raw (Hugging Face) -> ud-raw.parquet.
  columns: id, time, score (net up-minus-down votes), word, definition, example

COMMONALITY RESCUE: the dump's vote counts are lossy (UD's API stopped
exposing votes, and the scrape lost most historical tallies) — famous terms
sit at score 1-41 (lmao 1, wtf 3, idk 4, omg 33, yeet 41) while the top-10k
cut lands around 66. Votes can't see them, but real-world text frequency
can: any clean pure-alpha term that is NOT in CMUdict is included when it is
either genuinely common in text (zipf >= RESCUE_ZIPF) or moderately common
WITH real vote evidence (zipf >= RESCUE_ZIPF2 and score >= RESCUE_SCORE2 —
wordfreq's corpora end ~2021 and underweight speech, so yeet sits at zipf
2.51; its 41 surviving votes make up the difference). ~440 words, audited
2026-07-28. The score cutoff itself stays — the 62-65 band is first names
and one-definition junk, not lost celebrities.

Output line format (../ud-data.js, window.UD_DATA):
  term \t phonemes \t zipf \t score
- term      : lowercased headword/phrase (the lookup + display key)
- phonemes  : ARPABET; EMPTY when the term already exists in CMUdict
              (the app uses the CMU pronunciation in that case)
- zipf      : commonality on the Zipf scale = max(real wordfreq, pseudo-from-votes)
- score     : the Urban Dictionary net vote score (for display / attribution;
              can be 0 or negative for rescued terms — the app hides those)

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
RESCUE_ZIPF = 3.2    # common in text: in on frequency alone
RESCUE_ZIPF2 = 2.4   # moderately common ...
RESCUE_SCORE2 = 20   # ... but only with real surviving votes

ok_re = re.compile(r"^[a-z0-9][a-z0-9 '.\-]*$")
has_letter = re.compile(r"[a-z]")
alt_re = re.compile(r"\(\d+\)$")
pure_alpha = re.compile(r"^[a-z]+$")

# Rescued initialisms that CONTAIN vowels, so the vowel-less auto rule below
# can't catch them, but are spoken as letter names (hand-audited 2026-07-28).
# Two-letter rescues are letter-spelled unconditionally.
LETTER_SPOKEN = {
    "lmao", "lmfao", "idk", "omg", "wwe", "apr", "diy", "ufc", "ucla", "esp",
    "bmi", "irl", "lte", "ipo", "apa", "idf", "hdmi", "doj", "cpi", "faq",
    "gmo", "isp", "icu", "cpa", "att", "osu", "ipl", "edm", "gis",
    "edp", "aoa", "mdma", "riaa", "coa", "nda", "aos", "lma", "aew", "tmo",
    "bha", "nca", "bma", "pma",
}

# Degenerate rescues: roman numerals read as numbers, unpronounceable
# stretch-spellings.
RESCUE_DROP = {"ii", "iii", "xiii", "mmm"}

# Rescues whose spoken form is neither letters nor what g2p guesses.
RESCUE_PRON = {
    "pls": "P L IY1 Z",   # read as "please"
    "ew": "Y UW1",        # the interjection, not letter names
    "boi": "B OY1",
    "ahhh": "AA1",
    "opengl": "OW1 P AH0 N JH IY1 EH1 L",  # "open-G-L"
    "pubg": "P AH1 B JH IY1",              # "pub-G"
    "suge": "SH UH1 G",                    # Suge Knight, "shoog"
}


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

# ---- 2b. commonality rescue (see module docstring) ----
top_set = {t for t, _ in ranked}
def rescue_ok(t, s):
    if t in top_set or t in cmu_words or t in RESCUE_DROP or not pure_alpha.match(t):
        return False
    z = zipf_frequency(t, "en")
    return z >= RESCUE_ZIPF or (z >= RESCUE_ZIPF2 and s >= RESCUE_SCORE2)


rescued = sorted(
    (t for t, s in best.items() if rescue_ok(t, s)),
    key=lambda t: -zipf_frequency(t, "en"))
print(f"zipf-rescued >= {RESCUE_ZIPF}   : {len(rescued)}  (e.g. {', '.join(rescued[:6])})")
ranked += [(t, best[t]) for t in rescued]
new_terms += rescued

# ---- 3. g2p the new terms ----
g2p = G2p()

# Letter names for terms spoken as initialisms (mirrors build_new.py — the
# build scripts in this directory are standalone by convention).
LETTER = {
    "a": "EY1", "b": "B IY1", "c": "S IY1", "d": "D IY1", "e": "IY1",
    "f": "EH1 F", "g": "JH IY1", "h": "EY1 CH", "i": "AY1", "j": "JH EY1",
    "k": "K EY1", "l": "EH1 L", "m": "EH1 M", "n": "EH1 N", "o": "OW1",
    "p": "P IY1", "q": "K Y UW1", "r": "AA1 R", "s": "EH1 S", "t": "T IY1",
    "u": "Y UW1", "v": "V IY1", "w": "D AH1 B AH0 L Y UW0", "x": "EH1 K S",
    "y": "W AY1", "z": "Z IY1",
}
no_vowel = re.compile(r"^[b-df-hj-np-tv-xz]+$")  # letters only, no a/e/i/o/u/y


def letters(tok):
    return " ".join(LETTER[ch] for ch in tok)


def arpabet(term):
    toks = [p for p in g2p(term) if p.strip() and p != " "]
    # keep only real ARPABET tokens (letters, optional trailing stress digit)
    toks = [p for p in toks if re.match(r"^[A-Z]+[0-2]?$", p)]
    return " ".join(toks)


# Rescued terms only (all single-token pure-alpha): initialisms read as
# letter names — vowel-less ones (wtf, tbh), the hand-audited vowel-
# containing ones (lmao, omg), and every 2-letter rescue (hd, gf, af).
# The top-10k path above stays pure g2p so existing entries don't churn.
def rescue_pron(t):
    if t in RESCUE_PRON:
        return RESCUE_PRON[t]
    if no_vowel.match(t) or t in LETTER_SPOKEN or len(t) == 2:
        return letters(t)
    return arpabet(t)


rescued_set = set(rescued)
prons = {}
for i, t in enumerate(new_terms):
    prons[t] = rescue_pron(t) if t in rescued_set else arpabet(t)
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
    f.write("// Top-rated terms from Urban Dictionary (https://www.urbandictionary.com),\n")
    f.write("// plus a commonality rescue: common words (wordfreq zipf >= 3.2) whose vote\n")
    f.write("// counts the source dump lost (lmao, wtf, yeet...). Pronunciations via g2p_en;\n")
    f.write("// initialisms are letter-spelled. Source: georgiyozhegov/urbandictionary-raw.\n")
    f.write("// Format per line: term\\tARPABET\\tzipf\\tUDscore  (ARPABET empty = use CMUdict\n")
    f.write("// pronunciation; score <= 0 = rescued term whose real votes are unknown).\n")
    f.write("window.UD_DATA = `")
    f.write(blob)
    f.write("`;\n")

size_mb = os.path.getsize(OUT) / (1024 * 1024)
print(f"written terms          : {len(lines)}")
print(f"output file            : {os.path.normpath(OUT)}")
print(f"output size            : {size_mb:.2f} MB")
