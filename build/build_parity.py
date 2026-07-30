#!/usr/bin/env python3
"""Render the parity harness: the REAL site, running on a tiny fixture dictionary.

Why this exists
---------------
The site's matcher (app.js) and the API's matcher (RhymerDictionaryService.cs in
the Cabin repo) are two implementations of one algorithm. They have already
drifted twice. This harness lets the C# port be tested against ground truth the
SITE produced, rather than against hand-written expectations that can be wrong
in the same direction as the port.

It builds `parity-harness.html` — a byte-for-byte copy of index.html with the
six <script src="*-data.js"> tags replaced by inline bundles from the fixture —
so the engine under test is genuinely the shipped one, not a re-implementation.

Usage
-----
    python build_parity.py            # writes ../parity-harness.html
    # serve the repo (launch.json "rhyme-finder"), open /parity-harness.html,
    # then run collect_parity.js in the page console (or via a driver) and paste
    # the JSON into the fixture's "expected" block.

Fixture (input AND output):
    ../../repos/Cabin/Cabin.Tests/TestData/rhymer-parity.json
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "..")
FIXTURE = os.path.normpath(os.path.join(
    HERE, "..", "..", "repos", "Cabin", "Cabin.Tests", "TestData", "rhymer-parity.json"))
OUT = os.path.join(SITE, "parity-harness.html")

# The collector runs inside the harness page and drives the real UI: it sets the
# match mode, fuzzy and stress toggles exactly as a user would, presses Search,
# and reads the rendered chips. Nothing here reimplements the engine.
COLLECTOR = r"""
window.collectParity = function (cases) {
  const frag = document.getElementById('fragInput');
  const btn = document.getElementById('searchBtn');
  const stress = document.getElementById('ignoreStress');
  const fuzzy = document.getElementById('fuzzy');
  const out = {};
  const setToggle = (el, want) => { if (el && el.checked !== want) el.click(); };

  cases.forEach((c) => {
    const modeBtn = document.querySelector('[data-mode="' + c.mode + '"]');
    if (modeBtn) modeBtn.click();
    setToggle(stress, c.ignoreStress);
    setToggle(fuzzy, c.fuzzy);
    frag.value = c.q;
    btn.click();
    const chips = Array.from(document.querySelectorAll('#results .word-chip'));
    out[c.id] = {
      words: chips.map((ch) => ch.getAttribute('data-w')),
      repeats: chips.reduce((acc, ch) => {
        const t = ch.querySelector('.dbl-tag');
        if (t) acc[ch.getAttribute('data-w')] = parseInt(t.textContent.replace('×', ''), 10);
        return acc;
      }, {}),
    };
  });
  return out;
};
"""


def main():
    fx = json.load(open(FIXTURE, encoding="utf-8"))
    html = open(os.path.join(SITE, "index.html"), encoding="utf-8").read()

    # Swap each data bundle <script src> for the fixture's inline payload. The
    # window.* variable names must match what app.js reads.
    varname = {
        "cmudict-data.js": "CMU_DATA", "freq-data.js": "CMU_FREQ",
        "ud-data.js": "UD_DATA", "new-data.js": "NEW_DATA",
        "mod-data.js": "MOD_DATA", "co-data.js": "CO_DATA",
    }
    for file, payload in fx["bundles"].items():
        tag = '<script src="%s"></script>' % file
        if tag not in html:
            raise SystemExit(f"index.html no longer loads {file} — fixture is stale")
        assert "`" not in payload and "${" not in payload, f"bad payload in {file}"
        html = html.replace(
            tag, "<script>window.%s = `%s`;</script>" % (varname[file], payload))

    # Any bundle the fixture doesn't define must not load the real (15MB) file.
    for file, name in varname.items():
        html = html.replace('<script src="%s"></script>' % file,
                            "<script>window.%s = ``;</script>" % name)

    html = html.replace("</body>", "<script>%s</script>\n</body>" % COLLECTOR)
    html = html.replace("<title>", "<title>PARITY HARNESS — ")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"wrote {os.path.normpath(OUT)}")
    print(f"bundles inlined : {', '.join(fx['bundles'])}")
    print(f"cases to collect: {len(fx['cases'])}")
    print("next: serve the site, open /parity-harness.html, and call")
    print("      collectParity(<the fixture's cases array>)")


if __name__ == "__main__":
    main()
