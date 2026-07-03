# Technical Rhymer

**technicalrhymer.org** — search words by **sound, not spelling**. Look up a
word's pronunciation, take the part you want to match, and find every word whose
pronunciation matches it (rhymes, near-rhymes, assonance, etc.).

The full design rationale lives on the site's [About page](about.html)
(`about.html`).

## How it works

1. **Look up a pronunciation** — type a word, get its ARPABET phonemes
   (e.g. `orange` → `AO1 R AH0 N JH`). Digits on vowels mark stress
   (1 = primary, 2 = secondary, 0 = none).
2. **Find rhymes & matches** — paste a phoneme fragment (e.g. `AH N JH`) and
   search. You get every word whose pronunciation **ends with** that fragment,
   grouped by syllable count.

When you look it up (Enter or **Look up**), the pronunciation is dropped straight
into the search box below — if the word has only one. If it has **two or more**
pronunciations, none is auto-filled; click the one you want and it drops into the
box. (Live-typing in the lookup box only previews — it won't overwrite the box.)

Shortcuts: click anywhere on a pronunciation to put the whole thing in the search
box; click a single **phoneme** to search from that point on; hit **Rhyme** to
search the tail from the stressed vowel. **Copy** grabs the full pronunciation;
**Say** speaks the word via the browser's speech synthesis.

**Ignore stress** (on by default) is a single setting exposed in both boxes —
flipping either checkbox flips the other. When on, the lookup shows, copies,
clicks, and Rhymes the pronunciation *without* stress numbers (`AO R AH N JH`
instead of `AO1 R AH0 N JH`) **and** search matching ignores stress, so the two
stay consistent. Turn it off to see stress (with the primary-stress vowel
highlighted) and match stress exactly.

### Search operators

- **`*`** or **`%`** — the parts must appear **in that order**, with anything
  between them. `AO R * AH N JH` finds words that contain `AO R`, then later
  `AH N JH`. The match-mode buttons anchor the ends of an ordered query:
  *Ends with* pins the last part to the word's end, *Starts with* pins the first
  part to the start, *Exact* pins both.
- **`|`** — the parts must all appear, in **any order**. `AO R | JH` finds words
  containing both `AO R` and `JH` regardless of which comes first.

Use one operator type per search. A query with no operator is a single fragment
matched by the chosen match-mode (the original behavior).

A repeated `|` part requires that many occurrences: `AH | AH` matches only words
that contain `AH` **twice**, and `a | b | b` requires `b` twice.

### Word sense (semantic filter)

A collapsible **Word sense** panel filters the rhyme results by meaning. Enter a
word and pick a relation (**Related** / **Synonym / like** / **Opposite**). There
are two engines:

**AI mode (default, keyless).** The filter sends `{word, relation, top ~200
candidates}` to the Technical Rhymer **relay** (`/api/rhymer/sense` on
runcabin.com — `RhymerSenseController` in the Cabin repo), which asks **Claude**
using a server-held key. Fixed-function by design: the prompt is built
server-side from validated inputs, the model is pinned (Haiku-class), output is
schema-forced and intersected with the submitted candidates, and it's guarded by
per-IP rate limits + a global daily budget cap + a 6h response cache. Visitors
never see or supply a key. `EH ZH ER` + "pirates" → `treasure`. Results are also
cached client-side per (word, relation, engine, candidate set).

**Local dev:** optional **`key.local.js`** sets `window.RF_DEFAULT_KEY` (this
machine's copy uses the Anthropic key from Cabin's `scripts/start_cabin.ps1`) —
when present the browser calls `api.anthropic.com` directly (via
`anthropic-dangerous-direct-browser-access`), so AI mode works over `file://`
without the relay. It is **gitignored and must never be deployed**. Override the
relay URL with `window.RF_SENSE_PROXY` for testing against dev.

**Offline fallback.** If the relay is rate-limited, over budget, or unreachable,
the filter degrades to bundled data: GloVe word vectors for **Related**
(cosine ≥ 0.45 — `grass` keeps `meadow`/`lawn`/`pasture`, drops `car`) and
WordNet for **Synonym** / **Opposite**. This data (`vec-data.js`, `lex-data.js`)
is lazy-loaded the first time it's needed.

The chosen sense (word + relation) is remembered per pinned tab.

### Double rhymes

When a rhyme part lands **2+ times** in a word, that word is split out into a
**Double rhymes** section above the normal results, with a `×2` / `×3` badge.
Examples for `AE T`: `at-bat` (×2), `rat-a-tat` (×2). This catches strict repeats
(`EY T` appearing twice in the string) and repeated `|` parts (`AH | AH`). The
section only shows when there are doubles.

### Fuzzy (similar-sounding consonants)

Turn on **Fuzzy** to treat "like-sounding" consonants as interchangeable, for
slant rhymes / consonance. Consonants are grouped by manner *and* voicing, so
`t↔k`, `b↔d`, and `s↔sh` match, but cross-voicing pairs (`t↔d`) do not. Vowels
still must match. The groups:

| Group | Phonemes |
| --- | --- |
| voiceless stops | P T K |
| voiced stops | B D G |
| voiceless sibilants / affricate | S SH CH |
| voiced sibilants / affricate | Z ZH JH |
| voiceless non-sibilant fricatives | F TH |
| voiced non-sibilant fricatives | V DH |
| nasals | M N NG |
| liquids | L R |
| glides | W Y |
| (HH matches only itself) | HH |

Fuzzy works with every match-mode and with the `*` / `%` / `|` operators.

**The groups are user-configurable**: the gear button next to the Fuzzy toggle
opens an editor (native `<dialog>`) where sounds move between groups
tap-to-pick-up, tap-to-drop — including a "Loose sounds" bucket for consonants
that should only match themselves (HH lives there by default). Custom groups
persist in `localStorage` (`rf_fuzzy_v1`; cleared when they match the
defaults), a **Reset to defaults** button restores the manner+voicing table
above, and applying changes recomputes the precomputed fuzzed keys for all
~145k entries (~fraction of a second, only on Apply). Groups need at least two
sounds; leftovers fall loose. The shipped defaults live in
`DEFAULT_FUZZY_GROUPS` in `app.js`.

### Result tabs

Above the results is a tab bar: a **Live** tab (always your current search) plus
any pinned tabs. Hit **New tab** to freeze the current results into a pinned tab
so they stick around while you keep searching. Click a pinned tab to view its
frozen snapshot, click its **×** to close it. Each pinned tab remembers its full
query (text, match-mode, fuzzy, ignore-stress, sort), so it re-renders exactly,
and pinned tabs are saved to `localStorage` — they survive a page reload. The
search controls always drive the Live tab.

Results are ranked by **commonality** by default — the most common words sit on
top, rare/obscure ones at the bottom — with a thin bar on each result showing
its frequency. Sort modes: *Most common* (default) · *By syllables* · *A–Z*.

Match modes: *Ends with (rhyme)* · *Starts with* · *Anywhere* · *Exact*.
*Ignore stress marks* (on by default) makes `AH0 N JH` and `AH1 N JH` match.

### UX niceties

- **Phoneme keyboard** — a collapsible tap-to-build panel under the search box
  with all 39 ARPABET sounds (each with an example word), the `*` / `|`
  operators, undo-last-sound, and clear.
- **Match highlighting** — result chips highlight exactly which phonemes
  matched your fragment.
- **Example chips** — one-tap examples under the lookup box and in the blank
  results state.
- **Actionable empty states** — "no matches" offers one-tap fixes (switch to
  Anywhere, turn on Fuzzy, clear the sense filter…).
- **Shareable URLs** — searches sync to `?q=…` (plus mode/fuzzy/stress/sort and
  sense settings), and the tab title follows the query.
- **Copy list** — copies the visible result words, one per line.
- **Sticky preferences** — fuzzy, ignore-stress, sort, match mode, sense
  relation, and panel open/closed state persist in `localStorage`
  (`rf_prefs_v1`) and survive reloads. A shared `?q=` link overrides them for
  that load but never overwrites them.
- **Keyboard** — `/` focuses lookup from anywhere; `Esc` clears the focused
  box; `Enter` searches.
- Clear (×) buttons in both inputs, auto-growing search box, back-to-top
  button, screen-reader announcements for result counts, and reduced-motion
  support.

### Slang (Urban Dictionary)

Coverage includes the **top 10,000 highest-rated Urban Dictionary terms** (ranked
by net vote score), so slang words and phrases are searchable and turn up in
rhyme results. These are marked with a gold **UD** tag; the lookup card shows the
UD vote score and links to the definition on Urban Dictionary. Their
pronunciations are **auto-generated** (g2p) and approximate, not human-verified.
Urban Dictionary content is user-submitted and may be crude, offensive, or NSFW.

### New words of the 2020s

Coverage also includes the **2,000 top-rated new words of the decade** — terms
whose first *meaningful* Urban Dictionary definition is dated 2020+ and that are
absent from CMUdict. These get a teal **’2x** tag (the year they first appeared)
and a **New · 20xx** badge on the lookup card. "First meaningful" is
score-weighted: a term qualifies even with older definitions as long as those are
marginal — max pre-2020 score ≤ max(20, 10% of its 2020s peak). That admits
`rizz` (junk 2015 nickname def at −50 vs. the real 626-vote 2023 def) while
keeping out `karen` (a genuinely popular 392-vote def from 2010). Pronunciations
are g2p like the UD set, except vowel-less acronyms (`tds`, `smh`) which are
spelled out as letter names. The source dataset ends **Nov 2023**, so 2024+
coinages aren't included yet.

## Running it

It's a standalone static site — no build step, no server required.

- **Open directly:** double-click `index.html` (data is loaded via `<script>`,
  so it works over `file://`).
- **Or serve it:** `python -m http.server 8731 --directory .` then open
  <http://localhost:8731>.

## Files

| File              | What it is                                                        |
| ----------------- | ----------------------------------------------------------------- |
| `index.html`      | Markup + inline Lucide icon sprite                                |
| `about.html`      | Design notes: why/how the search, ranking, and datasets work      |
| `styles.css`      | Styling (dark theme, single accent hue)                           |
| `app.js`          | Lookup + phoneme-suffix search logic                              |
| `cmudict-data.js` | The baked dictionary (`window.CMU_DATA`, ~135k pronunciations)    |
| `freq-data.js`    | Per-word commonality scores (`window.CMU_FREQ`, ~100k Zipf values) |
| `ud-data.js`      | Top 10k Urban Dictionary terms (`window.UD_DATA`: term, ARPABET, zipf, score) |
| `new-data.js`     | Top 2k new words of the 2020s (`window.NEW_DATA`: term, ARPABET, zipf, score, year) |
| `vec-data.js`     | GloVe-50d int8 word vectors for the Word sense "related" filter (lazy) |
| `lex-data.js`     | WordNet synonyms + antonyms for the Word sense "synonym/opposite" filter (lazy) |
| `build/`          | Build scripts + sources (see below)                              |

## Data

Pronunciations come from the [CMU Pronouncing Dictionary](https://github.com/cmusphinx/cmudict)
(~135k standard English words, ARPABET, public-domain/BSD-style license).
Commonality scores come from [wordfreq](https://github.com/rspeer/wordfreq)
(Zipf scale, combining subtitles, Wikipedia, news, books, and web text).
Slang comes from the top-rated entries of [Urban Dictionary](https://www.urbandictionary.com)
(source dataset: `georgiyozhegov/urbandictionary-raw` on Hugging Face), with
ARPABET generated by [g2p_en](https://github.com/Kyubyong/g2p).

To rebuild the data files:

```sh
cd build
pip install wordfreq pyarrow pandas g2p_en gensim nltk   # one-time

python build_data.py     # cmudict.dict        -> cmudict-data.js (pronunciations)
python build_freq.py     # cmudict.dict        -> freq-data.js    (commonality / Zipf)
python build_ud.py       # ud-raw.parquet      -> ud-data.js      (top 10k UD terms)
python build_new.py      # ud-raw.parquet      -> new-data.js     (top 2k new words of the 2020s)
python build_vec.py      # GloVe (downloaded)  -> vec-data.js     (word vectors, Word sense)
python build_lex.py      # WordNet (nltk)      -> lex-data.js     (synonyms/antonyms)
```

`build_data.py` drops dotted abbreviations (`a.`, `u.s.`). `build_freq.py` falls
back to the base word for possessives (so `challenge's` isn't stranded at 0).
`build_ud.py` ranks UD terms by net vote score, dedupes, takes the top 10,000,
g2p's the ones not already in CMUdict, and blends commonality as
`max(wordfreq, pseudo-from-votes)`.

### How slang commonality is scored

Urban Dictionary terms rarely have a real wordfreq value, so each gets
`max(real wordfreq zipf, a pseudo-zipf derived from its UD vote score)` (the
pseudo value is capped in a modest band so slang slots in among less-common real
words rather than displacing everyday vocabulary). This keeps the single
commonality sort coherent across standard words and slang.
