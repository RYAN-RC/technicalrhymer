#!/usr/bin/env python3
"""Compute a commonality score (Zipf frequency) for every CMUdict word and
bake it into ../freq-data.js as  window.CMU_FREQ = `word\tzipf\n...`.

Zipf scale (wordfreq): ~0 = not seen / extremely rare, ~8 = among the most
common words in English ("the" = 7.7). Combines subtitles, Wikipedia, news,
books, and web text. Words with zipf 0 are omitted (the app defaults missing
words to 0, i.e. least common -> bottom of the list).
"""
import re
import os
from wordfreq import zipf_frequency

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "cmudict.dict")
OUT = os.path.join(HERE, "..", "freq-data.js")

alt_re = re.compile(r"\(\d+\)$")

# unique base words, in first-seen order
words = []
seen = set()
with open(SRC, "r", encoding="utf-8") as f:
    for raw in f:
        tok = raw.split(" ", 1)[0]
        if not tok:
            continue
        w = alt_re.sub("", tok)
        if w and w not in seen:
            seen.add(w)
            words.append(w)

lines = []
nonzero = 0
rescued = 0
for w in words:
    z = zipf_frequency(w, "en")
    # Possessives ("challenge's", "above's") score 0 in wordfreq, which would
    # dump them to the bottom of every rhyme list. Fall back to the base word's
    # frequency (minus a small possessive penalty) so they rank sensibly.
    if z == 0 and w.endswith("'s"):
        base = zipf_frequency(w[:-2], "en")
        if base > 0:
            z = max(0.0, round(base - 0.3, 2))
            rescued += 1
    if z > 0:
        lines.append(w + "\t" + ("%.2f" % z))
        nonzero += 1

blob = "\n".join(lines)
assert "`" not in blob and "${" not in blob, "unexpected template-literal char"

with open(OUT, "w", encoding="utf-8") as f:
    f.write("// Word commonality (Zipf frequency) from the `wordfreq` library. https://github.com/rspeer/wordfreq\n")
    f.write("// Zipf ~0 = very rare, ~8 = most common. Words absent here default to 0 (least common).\n")
    f.write("window.CMU_FREQ = `")
    f.write(blob)
    f.write("`;\n")

size_mb = os.path.getsize(OUT) / (1024 * 1024)
print(f"unique words    : {len(words)}")
print(f"with zipf > 0   : {nonzero} ({100.0*nonzero/len(words):.1f}%)")
print(f"output file     : {os.path.normpath(OUT)}")
print(f"output size     : {size_mb:.2f} MB")
