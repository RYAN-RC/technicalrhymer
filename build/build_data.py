#!/usr/bin/env python3
"""Turn cmudict.dict into a compact JS data file the static site can load.

Output: ../cmudict-data.js  ->  window.CMU_DATA = `word\tPH PH PH\n...`
One line per pronunciation. Alternate pronunciations keep the same base word
(the "(2)" markers are stripped). Trailing "# ..." comments are dropped.
"""
import re
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "cmudict.dict")
OUT = os.path.join(HERE, "..", "cmudict-data.js")

alt_re = re.compile(r"\(\d+\)$")

lines = []
n_words = 0
n_dropped = 0
with open(SRC, "r", encoding="utf-8") as f:
    for raw in f:
        raw = raw.rstrip("\n")
        if not raw.strip():
            continue
        # drop trailing pronunciation comments:  "word PH PH # note"
        if " #" in raw:
            raw = raw.split(" #", 1)[0].rstrip()
        parts = raw.split(" ")
        if len(parts) < 2:
            continue
        word = parts[0]
        phonemes = " ".join(parts[1:]).strip()
        if not phonemes:
            continue
        word = alt_re.sub("", word)  # drop (2),(3) alternate markers
        # drop dotted abbreviations ("a.", "u.s.", "e.g.") — they are phonetic
        # duplicates of real words and pollute the top of rhyme lists.
        if "." in word:
            n_dropped += 1
            continue
        lines.append(f"{word}\t{phonemes}")
        n_words += 1

blob = "\n".join(lines)

# template-literal safe: ARPABET + words contain no backticks or ${
assert "`" not in blob and "${" not in blob, "unexpected template-literal char"

with open(OUT, "w", encoding="utf-8") as f:
    f.write("// Generated from CMU Pronouncing Dictionary (cmudict). Public domain / BSD-style license.\n")
    f.write("window.CMU_DATA = `")
    f.write(blob)
    f.write("`;\n")

size_mb = os.path.getsize(OUT) / (1024 * 1024)
print(f"entries written : {n_words}")
print(f"abbrevs dropped : {n_dropped}")
print(f"output file     : {os.path.normpath(OUT)}")
print(f"output size     : {size_mb:.2f} MB")
