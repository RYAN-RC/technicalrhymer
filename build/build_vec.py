#!/usr/bin/env python3
"""Bake word vectors (GloVe 50d) for the dictionary vocabulary into vec-data.js,
so the "Word sense -> related" filter can score semantic similarity offline.

Vectors are L2-normalized then quantized to int8 (x127). At runtime, the dot
product of two int8 rows / 127^2 ~= cosine similarity. Output (loaded lazily):
  window.RF_VEC_DIM   = 50
  window.RF_VEC_WORDS = `word\nword\n...`   (row order matches the matrix)
  window.RF_VEC_B64   = "<base64 of N*50 int8 bytes>"
"""
import os, re, base64
import numpy as np
import gensim.downloader as api

HERE = os.path.dirname(os.path.abspath(__file__))
CMUDICT = os.path.join(HERE, "cmudict.dict")
UD = os.path.join(HERE, "..", "ud-data.js")
OUT = os.path.join(HERE, "..", "vec-data.js")

alt_re = re.compile(r"\(\d+\)$")

vocab = set()
with open(CMUDICT, "r", encoding="utf-8") as f:
    for line in f:
        tok = line.split(" ", 1)[0]
        if tok:
            vocab.add(alt_re.sub("", tok))

# single-word UD terms too (phrases have no single GloVe vector)
if os.path.exists(UD):
    raw = open(UD, "r", encoding="utf-8").read()
    blob = raw.split("`", 1)[1].rsplit("`", 1)[0]
    for ln in blob.split("\n"):
        t = ln.split("\t")[0]
        if t and " " not in t:
            vocab.add(t)

print("loading glove-wiki-gigaword-50 ...")
kv = api.load("glove-wiki-gigaword-50")

words, rows = [], []
for w in vocab:
    if w in kv:
        v = kv[w].astype(np.float32)
        n = float(np.linalg.norm(v))
        if n == 0:
            continue
        q = np.clip(np.round(v / n * 127.0), -127, 127).astype(np.int8)
        words.append(w)
        rows.append(q)

mat = np.stack(rows)  # (N, 50) int8
b64 = base64.b64encode(mat.tobytes()).decode("ascii")
idx = "\n".join(words)
assert "`" not in idx and "${" not in idx

with open(OUT, "w", encoding="utf-8") as f:
    f.write("// Word vectors (GloVe wiki-gigaword 50d), L2-normalized and int8-quantized.\n")
    f.write("// Powers the Word sense -> 'related' semantic filter. https://nlp.stanford.edu/projects/glove/\n")
    f.write("window.RF_VEC_DIM = 50;\n")
    f.write("window.RF_VEC_WORDS = `" + idx + "`;\n")
    f.write('window.RF_VEC_B64 = "' + b64 + '";\n')

print("vectors written :", len(words))
print("grass present?  :", "grass" in words, "| meadow present?:", "meadow" in words)
print("output size     : %.2f MB" % (os.path.getsize(OUT) / 1048576))
