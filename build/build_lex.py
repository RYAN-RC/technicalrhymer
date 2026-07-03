#!/usr/bin/env python3
"""Bake WordNet synonyms + antonyms for the dictionary vocabulary into lex-data.js,
for the "Word sense -> synonym / opposite" filters (offline, no embeddings).

Output (loaded lazily):  window.RF_LEX = `word\tsyn,syn,...\tant,ant,...\n...`
Only words that have at least one synonym or antonym are included.
"""
import os, re
import nltk
for pkg in ["wordnet", "omw-1.4"]:
    nltk.download(pkg, quiet=True)
from nltk.corpus import wordnet as wn

HERE = os.path.dirname(os.path.abspath(__file__))
CMUDICT = os.path.join(HERE, "cmudict.dict")
UD = os.path.join(HERE, "..", "ud-data.js")
OUT = os.path.join(HERE, "..", "lex-data.js")

alt_re = re.compile(r"\(\d+\)$")
ok = re.compile(r"^[a-z][a-z' .-]*$")

vocab = set()
with open(CMUDICT, "r", encoding="utf-8") as f:
    for line in f:
        tok = line.split(" ", 1)[0]
        if tok:
            vocab.add(alt_re.sub("", tok))
if os.path.exists(UD):
    raw = open(UD, "r", encoding="utf-8").read()
    blob = raw.split("`", 1)[1].rsplit("`", 1)[0]
    for ln in blob.split("\n"):
        t = ln.split("\t")[0]
        if t:
            vocab.add(t)

def norm(name):
    return name.replace("_", " ").lower()

lines = []
n_syn = n_ant = 0
for w in sorted(vocab):
    syns, ants = set(), set()
    for s in wn.synsets(w):
        for lem in s.lemmas():
            nm = norm(lem.name())
            if nm != w and ok.match(nm):
                syns.add(nm)
            for a in lem.antonyms():
                an = norm(a.name())
                if ok.match(an):
                    ants.add(an)
    if syns or ants:
        if syns:
            n_syn += 1
        if ants:
            n_ant += 1
        lines.append(w + "\t" + ",".join(sorted(syns)) + "\t" + ",".join(sorted(ants)))

blob = "\n".join(lines)
assert "`" not in blob and "${" not in blob

with open(OUT, "w", encoding="utf-8") as f:
    f.write("// WordNet synonyms + antonyms for the Word sense filter. https://wordnet.princeton.edu/\n")
    f.write("// Per line: word\\tsyn,syn,...\\tant,ant,...\n")
    f.write("window.RF_LEX = `" + blob + "`;\n")

print("entries written :", len(lines), "| with synonyms:", n_syn, "| with antonyms:", n_ant)
print("output size     : %.2f MB" % (os.path.getsize(OUT) / 1048576))
