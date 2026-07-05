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

# Hand-curated iconic 2020s terms the scored scrape misses: its coverage ends
# Nov 2023 (everything 2024+), standalone forms sometimes lost out to
# compounds (skibidi vs "skibidi rizz"), and the junk-def rule above ate a
# few whose strings had well-scored older meanings (mogging, gooner, unc).
# Curated 2026-07-05; every term verified to exist on Urban Dictionary via
# the public API, which no longer exposes vote counts — so score is written
# as 0 (the app never displays a score for NEW-only terms) and commonality
# is hand-assigned instead of pseudo_zipf: 3.5 = era-defining, 3.2 = major,
# ~2.9-3.0 = solid, <2.9 = niche-but-iconic. Year = when it went mainstream
# (not first-def date — many strings have ancient unrelated defs). Pron None
# = g2p like the auto set; overridden where g2p mangles (acronyms, digits,
# meme coinages).
MANUAL = [
    # (term, year, zipf, ARPABET override or None)
    # 2020
    ("vibe check", 2020, 3.2, None),
    ("glizzy", 2020, 3.2, None),
    ("hits different", 2020, 3.2, None),
    ("main character", 2020, 3.2, None),
    ("deadass", 2020, 3.5, "D EH1 D AE2 S"),
    ("baddie", 2020, 3.5, None),
    # 2021
    ("understood the assignment", 2021, 3.0, None),
    ("cheugy", 2021, 2.9, "CH UW1 G IY0"),
    ("caught in 4k", 2021, 3.2, "K AO1 T IH0 N F AO1 R K EY1"),
    ("rent free", 2021, 3.2, None),
    ("fr fr", 2021, 3.2, None),
    ("ratioed", 2021, 3.0, "R EY1 SH IY0 OW0 D"),
    # 2022
    ("quiet quitting", 2022, 3.0, None),
    ("situationship", 2022, 3.5, "S IH2 CH UW0 EY1 SH AH0 N SH IH2 P"),
    ("unalive", 2022, 3.2, "AH2 N AH0 L AY1 V"),
    ("it's giving", 2022, 3.2, None),
    ("goofy ahh", 2022, 3.2, "G UW1 F IY0 AA1"),
    ("soft launch", 2022, 3.0, None),
    ("hard launch", 2022, 2.9, None),
    # 2023
    ("skibidi", 2023, 3.5, "S K IH1 B IH0 D IY0"),
    ("gyat", 2023, 3.5, "G Y AA1 T"),
    ("gyatt", 2023, 3.5, "G Y AA1 T"),
    ("mewing", 2023, 3.2, "M Y UW1 IH0 NG"),
    ("looksmaxxing", 2023, 3.2, "L UH1 K S M AE2 K S IH0 NG"),
    ("mogging", 2023, 3.2, "M AA1 G IH0 NG"),
    ("rizzler", 2023, 3.2, "R IH1 Z L ER0"),
    ("girl dinner", 2023, 3.2, None),
    ("girl math", 2023, 2.9, None),
    ("boy math", 2023, 2.9, None),
    ("roman empire", 2023, 3.0, None),
    ("beige flag", 2023, 2.9, None),
    ("canon event", 2023, 3.2, None),
    ("bombastic side eye", 2023, 2.9, None),
    ("yapping", 2023, 3.2, None),
    ("gooning", 2023, 3.2, None),
    ("gooner", 2023, 3.2, None),
    ("let him cook", 2023, 3.2, None),
    ("hopecore", 2023, 2.7, "HH OW1 P K AO1 R"),
    ("core memory", 2023, 3.0, None),
    # 2024
    ("brat summer", 2024, 3.0, None),
    ("very demure", 2024, 3.0, None),
    ("hawk tuah", 2024, 3.2, "HH AO1 K T UW1 AH0"),
    ("aura points", 2024, 3.2, None),
    ("brainrot", 2024, 3.5, "B R EY1 N R AA1 T"),
    ("brain rot", 2024, 3.5, None),
    ("huzz", 2024, 3.2, "HH AH1 Z"),
    ("crash out", 2024, 3.2, None),
    ("crashout", 2024, 3.2, "K R AE1 SH AW1 T"),
    ("chat is this real", 2024, 3.0, None),
    ("pluh", 2024, 2.7, "P L AH1"),
    ("unc", 2024, 3.2, "AH1 NG K"),
    ("side quest", 2024, 3.0, None),
    # 2025
    ("six seven", 2025, 3.5, None),
    ("67", 2025, 3.5, "S IH1 K S S EH1 V AH0 N"),
    ("clanker", 2025, 3.2, None),
    ("aura farming", 2025, 3.2, None),
    ("tralalero tralala", 2025, 3.0, "T R AA0 L AA0 L EH1 R OW0 T R AA0 L AA0 L AA1"),
    ("ballerina cappuccina", 2025, 2.9, "B AE2 L ER0 IY1 N AH0 K AA2 P UW0 CH IY1 N AH0"),
    ("tung tung tung sahur", 2025, 2.9, "T UH1 NG T UH1 NG T UH1 NG S AA0 HH UW1 R"),
    ("italian brainrot", 2025, 3.0, "IH0 T AE1 L Y AH0 N B R EY1 N R AA1 T"),
    ("sybau", 2025, 3.0, "EH1 S W AY1 B IY1 EY1 Y UW1"),
    ("pmo", 2025, 3.2, "P IY1 EH1 M OW1"),
    ("ts pmo", 2025, 3.0, "T IY1 EH1 S P IY1 EH1 M OW1"),
    ("low taper fade", 2025, 3.0, None),
    ("ragebait", 2025, 3.2, "R EY1 JH B EY1 T"),
    ("bruzz", 2025, 2.9, "B R AH1 Z"),
    ("glorp", 2025, 2.7, "G L AO1 R P"),
]

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
emitted = set()
for i, t in enumerate(ranked):
    ph = arpabet(t)
    if not ph:
        continue  # g2p produced nothing usable; skip
    z = max(zipf_frequency(t, "en"), pseudo_zipf(post[t]))
    year = int(first20[t][:4])  # first sighting this decade
    lines.append("%s\t%s\t%.2f\t%d\t%d" % (t, ph, z, post[t], year))
    emitted.add(t)
    if (i + 1) % 500 == 0:
        print(f"  g2p {i + 1}/{len(ranked)}")

# ---- 5. manual additions (see MANUAL above) ----
added = 0
for t, year, z_hand, pron in MANUAL:
    if t in emitted:
        print(f"  manual SKIP (auto set already has it): {t!r}")
        continue
    if t in cmu_words:
        print(f"  manual SKIP (in CMUdict, already resolves): {t!r}")
        continue
    ph = pron or arpabet(t)
    if not ph:
        print(f"  manual SKIP (no pronunciation): {t!r}")
        continue
    z = max(zipf_frequency(t, "en"), z_hand)
    lines.append("%s\t%s\t%.2f\t%d\t%d" % (t, ph, z, 0, year))
    emitted.add(t)
    added += 1
print(f"manual terms added         : {added}/{len(MANUAL)}")

blob = "\n".join(lines)
assert "`" not in blob and "${" not in blob, "unexpected template-literal char"

with open(OUT, "w", encoding="utf-8") as f:
    f.write("// New words of the 2020s: top-rated Urban Dictionary terms first (meaningfully)\n")
    f.write("// defined 2020+ and absent from CMUdict.\n")
    f.write("// Source dataset: georgiyozhegov/urbandictionary-raw (coverage through Nov 2023),\n")
    f.write("// plus a hand-curated set of iconic terms through 2026 (score 0 = unscored;\n")
    f.write("// the UD API stopped exposing vote counts).\n")
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
