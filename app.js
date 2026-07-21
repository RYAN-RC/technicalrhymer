/* Technical Rhymer (technicalrhymer.org) — phoneme-suffix search over the
   CMU Pronouncing Dictionary. Workflow: look up a word's ARPABET pronunciation,
   take the tail you want, then search for every word whose pronunciation
   matches it. */

(function () {
  "use strict";

  // ---- data ----
  const entries = [];          // { w, p, key, keyNS, syl, z }
  const byWord = new Map();    // lowercased word -> [pron, pron, ...]
  const freq = new Map();      // lowercased word -> zipf commonality score
  const udInfo = new Map();    // urban-dictionary term -> net vote score
  const udGenerated = new Set(); // ud terms whose pronunciation we auto-generated
  const newInfo = new Map();   // new-this-decade term -> { year, score }
  const newGenerated = new Set(); // new terms this file added to the index (approx pron)

  const VOWEL_DIGIT = /[0-2]$/;
  const VOWEL_BASE = new Set(["AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY", "IH", "IY", "OW", "OY", "UH", "UW"]);
  const isVowelTok = (t) => VOWEL_DIGIT.test(t) || VOWEL_BASE.has(t);
  const stripStress = (p) => p.replace(/[0-2]/g, "");
  const sylCount = (p) => (p.match(/[0-2]/g) || []).length;

  // Fuzzy matching: "like-sounding" sound classes. Consonant DEFAULTS group by
  // manner + voicing; the user can regroup them (gear next to the Fuzzy
  // toggle) and custom groups persist in localStorage. Sounds in the same
  // group map to a shared representative. Vowel groups exist too but ship
  // UNSEEDED — the vowel is the rhyme, so by default every vowel matches only
  // itself; grouping vowels (say EH with IH) is a deliberate user choice.
  const ALL_CONSONANTS = ["B", "CH", "D", "DH", "F", "G", "HH", "JH", "K", "L", "M", "N", "NG", "P", "R", "S", "SH", "T", "TH", "V", "W", "Y", "Z", "ZH"];
  const ALL_VOWELS = ["AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY", "IH", "IY", "OW", "OY", "UH", "UW"];
  const DEFAULT_FUZZY_GROUPS = [
    ["P", "T", "K"],        // voiceless stops
    ["B", "D", "G"],        // voiced stops
    ["S", "SH", "CH"],      // voiceless sibilants / affricate
    ["Z", "ZH", "JH"],      // voiced sibilants / affricate
    ["F", "TH"],            // voiceless non-sibilant fricatives
    ["V", "DH"],            // voiced non-sibilant fricatives
    ["M", "N", "NG"],       // nasals
    ["L", "R"],             // liquids
    ["W", "Y"],             // glides
  ];
  const DEFAULT_VOWEL_GROUPS = [];   // intentionally unseeded — see above
  const FUZZY_KEY = "rf_fuzzy_v1";
  const VOWEL_FUZZY_KEY = "rf_fuzzyv_v1";

  // Keep only sounds from the given alphabet, no duplicates across groups,
  // groups of 2+. Any array input yields a config — INCLUDING the empty one,
  // which is the legitimate "nothing fuzzes, every sound matches only itself"
  // choice. Only a non-array (absent / corrupt storage) returns null → defaults.
  function sanitizeFuzzyGroups(raw, alphabet) {
    if (!Array.isArray(raw)) return null;
    const seen = new Set();
    const out = [];
    raw.forEach((g) => {
      if (!Array.isArray(g)) return;
      const grp = [];
      g.forEach((c) => {
        c = String(c).toUpperCase();
        if (alphabet.indexOf(c) < 0 || seen.has(c)) return;
        seen.add(c);
        grp.push(c);
      });
      if (grp.length >= 2) out.push(grp); // a group of one is just a loose sound
    });
    return out;
  }

  function loadGroups(storageKey, alphabet) {
    try {
      return sanitizeFuzzyGroups(JSON.parse(localStorage.getItem(storageKey) || "null"), alphabet);
    } catch (e) { return null; }
  }

  function buildRepMap(groups) {
    const m = {};
    groups.forEach((g) => g.forEach((c) => { m[c] = g[0]; }));
    return m;
  }

  // order-insensitive comparison (group order and in-group order don't matter)
  function groupsEqual(a, b) {
    const norm = (gs) => gs.map((g) => g.slice().sort().join(",")).sort().join("|");
    return norm(a) === norm(b);
  }
  const fuzzyIsDefault = (groups) => groupsEqual(groups, DEFAULT_FUZZY_GROUPS);
  const vowelsIsDefault = (groups) => groupsEqual(groups, DEFAULT_VOWEL_GROUPS);

  let fuzzyGroups = loadGroups(FUZZY_KEY, ALL_CONSONANTS) || DEFAULT_FUZZY_GROUPS.map((g) => g.slice());
  let vowelGroups = loadGroups(VOWEL_FUZZY_KEY, ALL_VOWELS) || DEFAULT_VOWEL_GROUPS.map((g) => g.slice());
  let CONS_MAP = buildRepMap(fuzzyGroups);
  let VOW_MAP = buildRepMap(vowelGroups);
  // Vowel tokens may carry a stress digit (AO1) — fuzz the base, keep the
  // digit, so stressed/unstressed keys stay aligned and syllables count true.
  const fuzzToken = (t) => {
    if (isVowelTok(t)) {
      const hasDigit = VOWEL_DIGIT.test(t);
      const base = hasDigit ? t.slice(0, -1) : t;
      const rep = VOW_MAP[base];
      return rep ? (hasDigit ? rep + t.slice(-1) : rep) : t;
    }
    return CONS_MAP[t] || t;
  };
  const fuzzStr = (s) => s.split(" ").map(fuzzToken).join(" ");

  // Recompute every entry's precomputed fuzzed keys after the groups change.
  // ~145k entries x 2 strings; only runs on Apply, never on boot (boot parses
  // with the loaded groups already in place).
  function rebuildFuzzKeys() {
    for (let i = 0; i < entries.length; i++) {
      const e = entries[i];
      e.keyF = fuzzStr(e.p);
      e.keyNSF = fuzzStr(e.keyNS);
    }
  }

  function parseFreq() {
    const raw = window.CMU_FREQ || "";
    if (!raw) return;
    const lines = raw.split("\n");
    for (let i = 0; i < lines.length; i++) {
      const t = lines[i].indexOf("\t");
      if (t < 0) continue;
      freq.set(lines[i].slice(0, t), parseFloat(lines[i].slice(t + 1)));
    }
  }

  function parseData() {
    parseFreq();
    const raw = window.CMU_DATA || "";
    const lines = raw.split("\n");
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const t = line.indexOf("\t");
      if (t < 0) continue;
      const w = line.slice(0, t);
      const p = line.slice(t + 1);
      const z = freq.get(w) || 0;
      const keyNS = stripStress(p);
      entries.push({ w: w, p: p, key: p, keyNS: keyNS, keyF: fuzzStr(p), keyNSF: fuzzStr(keyNS), syl: sylCount(p), z: z });
      let arr = byWord.get(w);
      if (!arr) { arr = []; byWord.set(w, arr); }
      arr.push(p);
    }
    parseUD();
    parseNew();
  }

  // Top-rated Urban Dictionary terms. Line: term \t ARPABET \t zipf \t udScore.
  // Empty ARPABET = term already in CMUdict (use that pronunciation); we only
  // record the UD score so it gets the "from Urban Dictionary" badge + link.
  function parseUD() {
    const raw = window.UD_DATA || "";
    if (!raw) return;
    const lines = raw.split("\n");
    for (let i = 0; i < lines.length; i++) {
      const parts = lines[i].split("\t");
      if (parts.length < 4) continue;
      const term = parts[0];
      const p = parts[1];
      const z = parseFloat(parts[2]) || 0;
      const score = parseInt(parts[3], 10) || 0;
      udInfo.set(term, score);
      if (p) {
        // new slang term not in CMUdict -> add it to the searchable index
        const keyNS = stripStress(p);
        entries.push({ w: term, p: p, key: p, keyNS: keyNS, keyF: fuzzStr(p), keyNSF: fuzzStr(keyNS), syl: sylCount(p), z: z });
        let arr = byWord.get(term);
        if (!arr) { arr = []; byWord.set(term, arr); }
        arr.push(p);
        udGenerated.add(term);
      }
    }
  }

  // New words of the 2020s (also UD-sourced). Line: term \t ARPABET \t zipf \t
  // score \t firstYear. None are in CMUdict, but some overlap the UD top-10k
  // set above — those are already indexed, so we only record the badge info.
  function parseNew() {
    const raw = window.NEW_DATA || "";
    if (!raw) return;
    const lines = raw.split("\n");
    for (let i = 0; i < lines.length; i++) {
      const parts = lines[i].split("\t");
      if (parts.length < 5) continue;
      const term = parts[0];
      const p = parts[1];
      const z = parseFloat(parts[2]) || 0;
      const score = parseInt(parts[3], 10) || 0;
      const year = parseInt(parts[4], 10) || 0;
      newInfo.set(term, { year: year, score: score });
      if (!byWord.has(term) && p) {
        const keyNS = stripStress(p);
        entries.push({ w: term, p: p, key: p, keyNS: keyNS, keyF: fuzzStr(p), keyNSF: fuzzStr(keyNS), syl: sylCount(p), z: z });
        byWord.set(term, [p]);
        newGenerated.add(term);
      }
    }
  }

  function udLink(term) {
    return "https://www.urbandictionary.com/define.php?term=" + encodeURIComponent(term);
  }

  // ---- helpers ----
  // Perfect-rhyme tail: from the last primary-stressed vowel to the end
  // (falls back to last secondary, then last unstressed vowel).
  function rhymeTail(p) {
    const toks = p.split(" ");
    const findLast = (re) => {
      let x = -1;
      for (let i = 0; i < toks.length; i++) if (re.test(toks[i])) x = i;
      return x;
    };
    let idx = findLast(/1$/);
    if (idx < 0) idx = findLast(/2$/);
    if (idx < 0) idx = findLast(/0$/);
    if (idx < 0) return p;
    return toks.slice(idx).join(" ");
  }

  // Parse the search box into a structured query:
  //  - contains "|"        -> unordered: every part must appear, in any order
  //  - contains "*" or "%" -> ordered: parts must appear in this order, gaps allowed
  //  - otherwise           -> plain single fragment (uses the match-mode buttons)
  function parseQuery(text, ignoreStress) {
    const t = text.toUpperCase();
    let type, raw;
    if (t.indexOf("|") >= 0) { type = "unordered"; raw = t.split("|"); }
    else if (/[*%]/.test(t)) { type = "ordered"; raw = t.split(/[*%]/); }
    else { type = "plain"; raw = [t]; }
    const segs = raw.map((s) => {
      let toks = s.trim().split(/\s+/).filter(Boolean);
      if (ignoreStress) toks = toks.map((x) => x.replace(/[0-2]/g, ""));
      return toks;
    }).filter((seg) => seg.length > 0);
    if (segs.length === 0) return null;
    if (segs.length === 1) type = "plain"; // a lone operand behaves as a plain fragment
    return { type: type, segs: segs };
  }

  function queryDisplay(q) {
    const parts = q.segs.map((s) => s.join(" "));
    if (q.type === "ordered") return parts.join(" * ");
    if (q.type === "unordered") return parts.join(" | ");
    return parts[0];
  }

  // first index >= from where seg appears as a contiguous run in tokens, else -1
  function indexOfSub(tokens, seg, from) {
    const n = tokens.length, m = seg.length;
    outer: for (let i = from; i + m <= n; i++) {
      for (let j = 0; j < m; j++) if (tokens[i + j] !== seg[j]) continue outer;
      return i;
    }
    return -1;
  }

  // count of non-overlapping occurrences of seg in tokens
  function countOcc(tokens, seg) {
    let c = 0, i = 0;
    while (i + seg.length <= tokens.length) {
      const k = indexOfSub(tokens, seg, i);
      if (k < 0) break;
      c += 1; i = k + seg.length;
    }
    return c;
  }

  // how many times the rhyme repeats in a word = the max occurrences of any one
  // distinct query segment. >= 2 means it's a "double rhyme".
  function rhymeMultiplicity(tokens, segs) {
    let max = 0;
    const seen = {};
    for (let s = 0; s < segs.length; s++) {
      const key = segs[s].join(" ");
      if (seen[key]) continue;
      seen[key] = 1;
      const c = countOcc(tokens, segs[s]);
      if (c > max) max = c;
    }
    return max;
  }

  // ordered: segments appear in order with arbitrary gaps. The match-mode anchors
  // the ends -> start/exact: first segment at the very start; end/exact: last at the end.
  function matchOrdered(tokens, segs, mode) {
    const k = segs.length;
    const startAnchor = (mode === "start" || mode === "exact");
    const endAnchor = (mode === "end" || mode === "exact");
    let pos = 0, first = 0;
    if (startAnchor) {
      if (indexOfSub(tokens, segs[0], 0) !== 0) return false;
      pos = segs[0].length; first = 1;
    }
    const last = endAnchor ? k - 1 : k;
    for (let s = first; s < last; s++) {
      const i = indexOfSub(tokens, segs[s], pos);
      if (i < 0) return false;
      pos = i + segs[s].length;
    }
    if (endAnchor) {
      const seg = segs[k - 1];
      const start = tokens.length - seg.length;
      if (start < pos) return false;
      for (let j = 0; j < seg.length; j++) if (tokens[start + j] !== seg[j]) return false;
    }
    return true;
  }

  // unordered: every segment must appear somewhere (order irrelevant). A segment
  // listed N times (e.g. "a | b | b") must occur at least N times in the word.
  function matchUnordered(tokens, segs) {
    const need = {};
    for (let s = 0; s < segs.length; s++) {
      const key = segs[s].join(" ");
      need[key] = (need[key] || 0) + 1;
    }
    for (let s = 0; s < segs.length; s++) {
      const key = segs[s].join(" ");
      if (need[key] < 0) continue; // already checked
      if (countOcc(tokens, segs[s]) < need[key]) return false;
      need[key] = -1;
    }
    return true;
  }

  // ---- "Sounds like": phonetically weighted edit distance ----
  // A Levenshtein over ARPABET tokens where the substitution cost knows
  // phonetics: vowels are scored by articulatory distance (a diphthong is a
  // start→glide trajectory, so AY sits between AA and IY), consonants by
  // place + manner + voicing (agreeing with the default fuzzy groups), and a
  // vowel never trades cheaply for a consonant. A word is a match when its
  // distance to the query pronunciation is within max(2, shorterLen / 3).
  const PH_LIST = ALL_VOWELS.concat(ALL_CONSONANTS); // ids: 0-14 vowels, 15-38 consonants
  const PH_ID = {};
  PH_LIST.forEach((p, i) => { PH_ID[p] = i; });
  const PH_UNK = PH_LIST.length; // reserved id for unrecognized query tokens
  const PH_N = PH_UNK + 1;

  // vowel articulation: [startHeight, startFront, endHeight, endFront, round, rhotic]
  // height 0 high → 2 low, frontness 0 front → 2 back; diphthongs get distinct
  // start/end points so their cost to a monophthong is the trajectory gap.
  const VOWEL_FEAT = {
    AA: [2, 2, 2, 2, 0, 0],
    AE: [2, 0.2, 2, 0.2, 0, 0],
    AH: [1, 1, 1, 1, 0, 0],
    AO: [1.6, 2, 1.6, 2, 1, 0],
    AW: [2, 1, 0.35, 2, 0.5, 0],
    AY: [2, 1, 0.35, 0.2, 0, 0],
    EH: [1, 0.2, 1, 0.2, 0, 0],
    ER: [1, 1, 1, 1, 0, 1],
    EY: [1, 0.2, 0.35, 0.2, 0, 0],
    IH: [0.35, 0.2, 0.35, 0.2, 0, 0],
    IY: [0, 0, 0, 0, 0, 0],
    OW: [1, 2, 0.35, 2, 1, 0],
    OY: [1.6, 2, 0.35, 0.2, 0.5, 0],
    UH: [0.35, 2, 0.35, 2, 1, 0],
    UW: [0, 2, 0, 2, 1, 0],
  };
  // consonant articulation: [place 0 lips → 7 glottis, manner, voiced, sibilant]
  const CONS_FEAT = {
    P: [0, 0, 0, 0], B: [0, 0, 1, 0], T: [3, 0, 0, 0], D: [3, 0, 1, 0], K: [6, 0, 0, 0], G: [6, 0, 1, 0],
    CH: [4, 1, 0, 1], JH: [4, 1, 1, 1],
    F: [1, 2, 0, 0], V: [1, 2, 1, 0], TH: [2, 2, 0, 0], DH: [2, 2, 1, 0],
    S: [3, 2, 0, 1], Z: [3, 2, 1, 1], SH: [4, 2, 0, 1], ZH: [4, 2, 1, 1], HH: [7, 2, 0, 0],
    M: [0, 3, 1, 0], N: [3, 3, 1, 0], NG: [6, 3, 1, 0],
    L: [3, 4, 1, 0], R: [4, 4, 1, 0],
    W: [6, 5, 1, 0], Y: [5, 5, 1, 0],
  };
  const MANNER_DIST = [ // stop, affricate, fricative, nasal, liquid, glide
    [0, 0.3, 0.6, 0.55, 0.8, 0.9],
    [0.3, 0, 0.3, 0.7, 0.85, 0.9],
    [0.6, 0.3, 0, 0.7, 0.8, 0.85],
    [0.55, 0.7, 0.7, 0, 0.7, 0.8],
    [0.8, 0.85, 0.8, 0.7, 0, 0.45],
    [0.9, 0.9, 0.85, 0.8, 0.45, 0],
  ];

  const SND_SUB = new Float64Array(PH_N * PH_N); // substitution cost, flat [a*PH_N+b]
  const SND_DEL = new Float64Array(PH_N);        // insert/delete cost per phoneme
  (function buildSoundCosts() {
    const vcost = (a, b) => {
      const start = Math.hypot(a[0] - b[0], (a[1] - b[1]) * 0.9);
      const end = Math.hypot(a[2] - b[2], (a[3] - b[3]) * 0.9);
      return Math.min(0.95, 0.2 + 0.26 * (start + end) / 2 +
        0.18 * Math.abs(a[4] - b[4]) + 0.3 * Math.abs(a[5] - b[5]));
    };
    const ccost = (a, b) => Math.min(1,
      0.14 + 0.32 * (Math.abs(a[0] - b[0]) / 7) + 0.42 * MANNER_DIST[a[1]][b[1]] +
      0.28 * Math.abs(a[2] - b[2]) + 0.12 * Math.abs(a[3] - b[3]));
    for (let i = 0; i < PH_N; i++) {
      for (let j = 0; j < PH_N; j++) {
        let c;
        if (i === j) c = 0;
        else if (i === PH_UNK || j === PH_UNK) c = 1;
        else {
          const va = VOWEL_FEAT[PH_LIST[i]], vb = VOWEL_FEAT[PH_LIST[j]];
          if (va && vb) c = vcost(va, vb);
          else if (!va && !vb) c = ccost(CONS_FEAT[PH_LIST[i]], CONS_FEAT[PH_LIST[j]]);
          else c = 1; // vowel <-> consonant
        }
        SND_SUB[i * PH_N + j] = c;
      }
    }
    // phonology the feature math can't see
    const pair = (a, b, c) => {
      SND_SUB[PH_ID[a] * PH_N + PH_ID[b]] = c;
      SND_SUB[PH_ID[b] * PH_N + PH_ID[a]] = c;
    };
    pair("L", "R", 0.32);  // lateral vs rhotic is audible — dearer than bare features say
    pair("R", "ER", 0.35); // the r-colored vowel ~ the consonant
    pair("Y", "IY", 0.45); pair("Y", "IH", 0.55); // glides ~ their syllabic twins
    pair("W", "UW", 0.45); pair("W", "UH", 0.55);
    for (let i = 0; i < PH_N; i++) SND_DEL[i] = i < ALL_VOWELS.length ? 0.95 : 0.85;
    SND_DEL[PH_ID.AH] = 0.6; // schwa comes and goes cheaply
    SND_DEL[PH_ID.HH] = 0.7;
    SND_DEL[PH_UNK] = 1;
  })();
  const SND_MIN_DEL = 0.6; // cheapest insert/delete — length-gap lower bound

  // token-id index over all entries, built once on first sounds-like search
  // (keyNS never changes after boot). Flat typed arrays, ~1MB for 146k prons.
  let SND_IDX = null;
  function buildSoundIndex() {
    const off = new Int32Array(entries.length);
    const len = new Uint8Array(entries.length);
    const lists = new Array(entries.length);
    let total = 0;
    for (let i = 0; i < entries.length; i++) {
      const toks = entries[i].keyNS.split(" ");
      lists[i] = toks;
      off[i] = total;
      len[i] = Math.min(toks.length, 255);
      total += len[i];
    }
    const flat = new Uint8Array(total);
    for (let i = 0; i < entries.length; i++) {
      const toks = lists[i], base = off[i], n = len[i];
      for (let j = 0; j < n; j++) {
        const id = PH_ID[toks[j]];
        flat[base + j] = id === undefined ? PH_UNK : id;
      }
    }
    SND_IDX = { flat: flat, off: off, len: len };
  }

  // one pass over the whole dictionary → [{ e, d }] in dictionary order.
  // Cheap length prefilter, then a two-row DP that abandons an entry as soon
  // as a whole row exceeds its threshold.
  function soundsLikePass(qToks) {
    if (!SND_IDX) buildSoundIndex();
    const m = Math.min(qToks.length, 64);
    const qIds = new Uint8Array(m);
    for (let j = 0; j < m; j++) {
      const id = PH_ID[qToks[j]];
      qIds[j] = id === undefined ? PH_UNK : id;
    }
    let prev = new Float64Array(m + 1);
    let curr = new Float64Array(m + 1);
    const flat = SND_IDX.flat, offs = SND_IDX.off, lens = SND_IDX.len;
    const out = [];
    for (let idx = 0; idx < entries.length; idx++) {
      const n = lens[idx];
      const minLen = n < m ? n : m;
      const thr = minLen / 3 > 2 ? minLen / 3 : 2;
      const gap = n > m ? n - m : m - n;
      if (gap * SND_MIN_DEL > thr) continue;
      prev[0] = 0;
      for (let j = 1; j <= m; j++) prev[j] = prev[j - 1] + SND_DEL[qIds[j - 1]];
      const base = offs[idx];
      let alive = true;
      for (let i = 1; i <= n; i++) {
        const ai = flat[base + i - 1];
        const delA = SND_DEL[ai];
        const srow = ai * PH_N;
        curr[0] = prev[0] + delA;
        let rowMin = curr[0];
        for (let j = 1; j <= m; j++) {
          const qj = qIds[j - 1];
          let v = prev[j - 1] + SND_SUB[srow + qj];
          const up = prev[j] + delA;
          if (up < v) v = up;
          const left = curr[j - 1] + SND_DEL[qj];
          if (left < v) v = left;
          curr[j] = v;
          if (v < rowMin) rowMin = v;
        }
        if (rowMin > thr) { alive = false; break; }
        const t = prev; prev = curr; curr = t;
      }
      if (alive && prev[m] <= thr + 1e-9) out.push({ e: entries[idx], d: prev[m] });
    }
    return out;
  }

  function search(rawFrag, opts) {
    const ignoreStress = opts.ignoreStress;
    const fuzzy = opts.fuzzy;
    const mode = opts.mode;
    const q = parseQuery(rawFrag, ignoreStress);
    if (!q) return { results: [], q: null };
    // fuzz the query for matching, but keep q.segs (originals) for display
    const segs = fuzzy ? q.segs.map((s) => s.map(fuzzToken)) : q.segs;
    const pick = fuzzy
      ? (e) => (ignoreStress ? e.keyNSF : e.keyF)
      : (e) => (ignoreStress ? e.keyNS : e.key);
    const out = [];
    const seen = new Set();
    const doubles = new Map(); // word -> times the rhyme repeats (>= 2)

    if (mode === "near") {
      // whole box = one pronunciation; operators are ignored, stress is
      // always stripped, and the fuzzy toggle is moot — closeness IS the
      // cost model here.
      const qToks = [];
      q.segs.forEach((s) => s.forEach((t) => qToks.push(t.replace(/[0-2]$/, ""))));
      const dists = new Map(); // word -> weighted sound distance
      const hits = soundsLikePass(qToks);
      for (let i = 0; i < hits.length; i++) {
        const e = hits[i].e, d = hits[i].d;
        if (seen.has(e.w)) {
          if (d < dists.get(e.w)) dists.set(e.w, d); // closer alternate pron
          continue;
        }
        seen.add(e.w); out.push(e); dists.set(e.w, d);
      }
      return { results: out, q: q, doubles: doubles, dists: dists };
    }

    if (q.type === "plain") {
      const frag = segs[0].join(" ");
      const seg0 = segs[0];
      for (let i = 0; i < entries.length; i++) {
        const e = entries[i];
        const hay = pick(e);
        let hit = false;
        if (mode === "end") hit = hay === frag || hay.endsWith(" " + frag);
        else if (mode === "start") hit = hay === frag || hay.startsWith(frag + " ");
        else if (mode === "any") hit = (" " + hay + " ").indexOf(" " + frag + " ") >= 0;
        else hit = hay === frag; // exact
        if (hit && !seen.has(e.w)) {
          seen.add(e.w); out.push(e);
          const n = countOcc(hay.split(" "), seg0);
          if (n >= 2) doubles.set(e.w, n);
        }
      }
    } else {
      for (let i = 0; i < entries.length; i++) {
        const e = entries[i];
        const tokens = pick(e).split(" ");
        const hit = q.type === "ordered"
          ? matchOrdered(tokens, segs, mode)
          : matchUnordered(tokens, segs);
        if (hit && !seen.has(e.w)) {
          seen.add(e.w); out.push(e);
          const n = rhymeMultiplicity(tokens, segs);
          if (n >= 2) doubles.set(e.w, n);
        }
      }
    }
    return { results: out, q: q, doubles: doubles };
  }

  // sort comparators by mode
  const byAlpha = (a, b) => (a.w < b.w ? -1 : a.w > b.w ? 1 : 0);
  const byCommon = (a, b) => (b.z - a.z) || byAlpha(a, b);            // most common first
  const bySyllable = (a, b) => (a.syl - b.syl) || byCommon(a, b);    // fewest syllables, then common

  // ---- DOM ----
  const $ = (id) => document.getElementById(id);
  const SMOOTH = (window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches) ? "auto" : "smooth";
  const wordInput = $("wordInput");
  const lookupBtn = $("lookupBtn");
  const wordClear = $("wordClear");
  const fragClear = $("fragClear");
  const phonePanel = $("phonePanel");
  const toTopBtn = $("toTop");
  const announceEl = $("announce");
  const lookupExamples = $("lookupExamples");
  const pronResult = $("pronResult");
  const notFound = $("notFound");
  const fragInput = $("fragInput");
  const searchBtn = $("searchBtn");
  const resultsEl = $("results");
  const ignoreStressEl = $("ignoreStress");
  const stripStress1El = $("stripStress1");
  const fuzzyEl = $("fuzzy");
  const tabBarEl = $("tabBar");
  const sensePanelEl = $("sensePanel");
  const senseWordEl = $("senseWord");
  const senseClearEl = $("senseClear");
  const senseStatusEl = $("senseStatus");
  const senseRelBtns = Array.from(document.querySelectorAll("#senseRel button"));
  const matchBtns = Array.from(document.querySelectorAll("#matchSeg button"));
  const sortBtns = Array.from(document.querySelectorAll("#sortSeg button"));
  const statusEl = $("status");

  let mode = "end";
  let sortMode = "common";
  let senseRel = "related";
  const senseModel = "claude-opus-4-8"; // local-dev direct calls only; the relay pins its own model
  const aiCache = new Map(); // cacheKey -> Set of matching words
  const AI_CANDIDATE_CAP = 200;

  // ---- result tabs: a live tab + pinned (frozen) snapshots ----
  const TABS_KEY = "rf_tabs_v1";
  let tabSeq = 0;
  let activeTabId = "live";
  const tabs = [{ id: "live", live: true, raw: "", mode: "end", fuzzy: false, ignoreStress: true, sort: "common", sense: { word: "", rel: "related" } }];

  function icon(id) {
    return '<svg aria-hidden="true"><use href="#' + id + '"></use></svg>';
  }

  function setSeg(btns, attr, val) {
    btns.forEach((b) => b.classList.toggle("on", b.getAttribute(attr) === val));
  }

  // ---- sticky preferences (fuzzy, stress, sort, match, sense relation, panels) ----
  const PREFS_KEY = "rf_prefs_v1";

  function savePrefs() {
    try {
      localStorage.setItem(PREFS_KEY, JSON.stringify({
        mode: mode,
        sort: sortMode,
        fuzzy: fuzzyEl.checked,
        ignoreStress: ignoreStressEl.checked,
        senseRel: senseRel,
        phoneOpen: !!(phonePanel && phonePanel.open),
        senseOpen: !!sensePanelEl.open,
      }));
    } catch (e) { /* localStorage unavailable */ }
  }

  // Applied at boot, BEFORE the URL restore — a shared ?q= link still wins,
  // and merely opening one never overwrites the saved preferences.
  function loadPrefs() {
    let p = null;
    try { p = JSON.parse(localStorage.getItem(PREFS_KEY) || "null"); } catch (e) { /* */ }
    if (!p) return;
    if (["end", "start", "any", "exact", "near"].indexOf(p.mode) >= 0) { mode = p.mode; setSeg(matchBtns, "data-mode", mode); }
    if (["common", "syllable", "alpha"].indexOf(p.sort) >= 0) { sortMode = p.sort; setSeg(sortBtns, "data-sort", sortMode); }
    fuzzyEl.checked = !!p.fuzzy;
    const on = p.ignoreStress !== false;
    stripStress1El.checked = on;
    ignoreStressEl.checked = on;
    if (["related", "synonym", "opposite"].indexOf(p.senseRel) >= 0) { senseRel = p.senseRel; setSeg(senseRelBtns, "data-rel", senseRel); }
    if (phonePanel) phonePanel.open = !!p.phoneOpen;
    if (p.senseOpen) sensePanelEl.open = true;
  }

  // ---- step 1: lookup ----
  function displayPron(p) {
    return stripStress1El.checked ? stripStress(p) : p;
  }

  // fill the search box with a pronunciation (no search) — the "drop it below" action
  function fillSearchBox(v) {
    fragInput.value = v;
    autoGrow();
    syncClearBtns();
    fragInput.focus();
    try { fragInput.setSelectionRange(v.length, v.length); } catch (e) { /* */ }
  }

  function doLookup(fill) {
    const q = wordInput.value.trim().toLowerCase();
    pronResult.classList.remove("show");
    notFound.classList.remove("show");
    pronResult.innerHTML = "";
    if (!q) return;

    let prons = byWord.get(q);
    if (!prons) {
      // tolerate trailing punctuation, e.g. "orange." or "wow!"
      const cleaned = q.replace(/[^a-z'.-]/g, "");
      prons = byWord.get(cleaned) || byWord.get(cleaned.replace(/[.\-]+$/, ""));
    }

    if (!prons || !prons.length) {
      notFound.innerHTML =
        "<b>“" + escapeHtml(q) + "”</b> isn’t in the dictionary. " +
        "This build covers the CMU Pronouncing Dictionary (standard English), the " +
        "top 10,000 Urban Dictionary terms, and 2,000+ new words of the 2020s. Try another spelling.";
      notFound.classList.add("show");
      return;
    }

    const displayWord = q;
    let html = "";
    if (prons.length > 1) {
      html += '<div class="pron-multi-hint">' + icon("ic-arrow-down") +
        prons.length + " pronunciations — click the one you want to drop it in the search box.</div>";
    }
    prons.forEach((p, i) => {
      html += renderPronCard(displayWord, p, prons.length > 1 ? i + 1 : 0);
    });
    pronResult.innerHTML = html;
    pronResult.classList.add("show");
    wireePronCards(displayWord);

    // explicit lookup of a single-pronunciation word -> auto-drop it into the search box
    if (fill && prons.length === 1) fillSearchBox(displayPron(prons[0]));
  }

  function renderPronCard(word, p, altNum) {
    // step-1 "ignore stress" toggle: show & copy the pronunciation without stress digits
    const strip = stripStress1El.checked;
    const display = strip ? stripStress(p) : p;
    const tailFull = rhymeTail(p); // compute tail from the stressed form, then strip if needed
    const tail = strip ? stripStress(tailFull) : tailFull;
    const toks = display.split(" ");
    let phHtml = "";
    toks.forEach((tk, i) => {
      const isVowel = isVowelTok(tk);
      const isPrimary = !strip && /1$/.test(tk);
      let cls = "ph";
      if (isVowel) cls += " vowel";
      if (isPrimary) cls += " stress1";
      phHtml += '<button type="button" tabindex="-1" class="' + cls + '" data-i="' + i + '">' + tk + "</button>";
    });
    const altBadge = altNum ? ' <span class="syl-badge">alt ' + altNum + "</span>" : "";
    const isUd = udInfo.has(word);
    const udBadge = isUd
      ? ' <a class="ud-badge" href="' + udLink(word) + '" target="_blank" rel="noopener" title="View on Urban Dictionary (score ' +
        udInfo.get(word).toLocaleString() + ')">' + icon("ic-thumbs-up") + udInfo.get(word).toLocaleString() + icon("ic-external") + "</a>"
      : "";
    const nu = newInfo.get(word);
    const newBadge = nu
      ? ' <a class="new-badge" href="' + udLink(word) + '" target="_blank" rel="noopener" title="New this decade — mainstream since ' +
        nu.year + '">' + icon("ic-sparkles") + "New · " + nu.year + "</a>"
      : "";
    const udNote = (udGenerated.has(word) || newGenerated.has(word))
      ? '<div class="pron-tip ud-note">' + icon("ic-thumbs-up") +
        "From <b style=\"color:var(--muted)\">Urban Dictionary</b> — pronunciation is auto-generated and approximate.</div>"
      : "";
    return (
      '<div class="pron-card" data-pron="' + escapeAttr(display) + '" data-tail="' + escapeAttr(tail) + '">' +
        '<div class="pron-top">' +
          '<span class="pron-word">' + escapeHtml(word) + altBadge + udBadge + newBadge + "</span>" +
          '<span class="syl-badge">' + sylCount(p) + " syllable" + (sylCount(p) === 1 ? "" : "s") + "</span>" +
          '<span class="pron-actions">' +
            '<button class="icon-btn js-speak" title="Hear it">' + icon("ic-volume") + "Say</button>" +
            '<button class="icon-btn js-copy" title="Copy full pronunciation">' + icon("ic-copy") + "Copy</button>" +
            '<button class="icon-btn js-rhyme" title="Search rhymes (from the stressed vowel)">' + icon("ic-scissors") + "Rhyme</button>" +
          "</span>" +
        "</div>" +
        '<div class="phonemes">' + phHtml + "</div>" +
        udNote +
        '<div class="pron-tip">' + icon("ic-sparkles") +
          "Click this pronunciation to drop it in the search box, a single <b style=\"color:var(--muted)\">phoneme</b> to search from there, or <b style=\"color:var(--muted)\">Rhyme</b> for the tail.</div>" +
      "</div>"
    );
  }

  function wireePronCards(word) {
    Array.from(pronResult.querySelectorAll(".pron-card")).forEach((card) => {
      const pron = card.getAttribute("data-pron");
      const tail = card.getAttribute("data-tail");
      const phSpans = Array.from(card.querySelectorAll(".ph"));

      // click the card (anywhere not a phoneme/button) -> drop the full pronunciation in the box
      card.addEventListener("click", () => fillSearchBox(pron));

      // hover: highlight the suffix that would be searched
      phSpans.forEach((sp, i) => {
        sp.addEventListener("mouseenter", () => {
          phSpans.forEach((o, j) => o.classList.toggle("tail", j >= i));
        });
        sp.addEventListener("mouseleave", () => {
          phSpans.forEach((o) => o.classList.remove("tail"));
        });
        sp.addEventListener("click", (e) => {
          e.stopPropagation();
          const toks = pron.split(" ");
          sendToSearch(toks.slice(i).join(" "));
        });
      });

      card.querySelector(".js-copy").addEventListener("click", (e) => {
        e.stopPropagation();
        copyText(pron, e.currentTarget);
      });
      card.querySelector(".js-rhyme").addEventListener("click", (e) => {
        e.stopPropagation();
        sendToSearch(tail);
      });
      card.querySelector(".js-speak").addEventListener("click", (e) => {
        e.stopPropagation();
        speak(word);
      });
      // the UD / New badge links inside the card shouldn't trigger a fill
      Array.from(card.querySelectorAll(".ud-badge, .new-badge")).forEach((a) =>
        a.addEventListener("click", (e) => e.stopPropagation()));
    });
  }

  // ---- step 2: search ----
  function sendToSearch(fragmentRaw) {
    fragInput.value = fragmentRaw;
    autoGrow();
    syncClearBtns();
    doSearch();
    fragInput.scrollIntoView({ behavior: SMOOTH, block: "center" });
  }

  // running a search (or changing any control) drives the LIVE tab and shows it
  function doSearch() {
    const live = tabs[0];
    live.raw = fragInput.value;
    live.mode = mode;
    live.fuzzy = fuzzyEl.checked;
    live.ignoreStress = ignoreStressEl.checked;
    live.sort = sortMode;
    live.sense = { word: senseWordEl.value.trim().toLowerCase(), rel: senseRel };
    activeTabId = "live";
    renderTabBar();
    renderTabContent(live);
    syncUrl(live);
  }

  // keep the address bar + tab title shareable: ?q=AH+N+JH&m=any&f=1&s=0&sort=alpha
  const BASE_TITLE = document.title;
  function syncUrl(live) {
    const raw = live.raw.trim();
    document.title = raw ? raw.replace(/\s+/g, " ").toUpperCase() + " · Technical Rhymer" : BASE_TITLE;
    if (!window.history || !history.replaceState) return;
    const p = new URLSearchParams();
    if (raw) {
      p.set("q", raw.replace(/\s+/g, " "));
      if (live.mode !== "end") p.set("m", live.mode);
      if (live.fuzzy) p.set("f", "1");
      if (!live.ignoreStress) p.set("s", "0");
      if (live.sort !== "common") p.set("sort", live.sort);
      if (live.sense && live.sense.word) {
        p.set("w", live.sense.word);
        if (live.sense.rel !== "related") p.set("r", live.sense.rel);
      }
    }
    const qs = p.toString();
    try {
      history.replaceState(null, "", qs ? "?" + qs : location.pathname);
    } catch (e) { /* file:// or sandbox — fine without shareable URLs */ }
  }

  // restore a shared/bookmarked search from the URL (called once, after data load)
  function restoreFromUrl() {
    let p;
    try { p = new URLSearchParams(location.search); } catch (e) { return false; }
    const q = (p.get("q") || "").trim();
    if (!q) return false;
    const m = p.get("m");
    if (m && ["end", "start", "any", "exact", "near"].indexOf(m) >= 0) { mode = m; setSeg(matchBtns, "data-mode", m); }
    fuzzyEl.checked = p.get("f") === "1";
    const stressOn = p.get("s") !== "0";
    stripStress1El.checked = stressOn;
    ignoreStressEl.checked = stressOn;
    const so = p.get("sort");
    if (so && ["common", "syllable", "alpha"].indexOf(so) >= 0) { sortMode = so; setSeg(sortBtns, "data-sort", so); }
    const w = (p.get("w") || "").trim().toLowerCase();
    if (w) {
      senseWordEl.value = w;
      const r = p.get("r");
      if (r && ["related", "synonym", "opposite"].indexOf(r) >= 0) { senseRel = r; setSeg(senseRelBtns, "data-rel", r); }
      sensePanelEl.open = true;
    }
    fragInput.value = q;
    autoGrow();
    syncClearBtns();
    doSearch();
    return true;
  }

  function tabById(id) { return tabs.find((t) => t.id === id); }

  // ---- word sense (semantic filter): lazy-loaded GloVe vectors + WordNet ----
  const SENSE_THRESHOLD = 0.45;       // cosine cutoff for "related"
  const VEC_SCALE = 127 * 127;
  let vecMat = null, vecDim = 50;
  const vecIdx = new Map();           // word -> row index
  const lexMap = new Map();           // word -> { syn:Set, ant:Set }
  let senseLoaded = false, senseLoading = false;
  let senseCbs = [];

  function parseVec() {
    if (!window.RF_VEC_B64 || !window.RF_VEC_WORDS) return;
    const words = window.RF_VEC_WORDS.split("\n");
    const bin = atob(window.RF_VEC_B64);
    const arr = new Int8Array(bin.length);
    for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
    vecMat = arr; vecDim = window.RF_VEC_DIM || 50;
    for (let i = 0; i < words.length; i++) vecIdx.set(words[i], i);
  }
  function parseLex() {
    if (!window.RF_LEX) return;
    const lines = window.RF_LEX.split("\n");
    for (let i = 0; i < lines.length; i++) {
      const p = lines[i].split("\t");
      if (p.length < 3) continue;
      lexMap.set(p[0], {
        syn: new Set(p[1] ? p[1].split(",") : []),
        ant: new Set(p[2] ? p[2].split(",") : []),
      });
    }
  }
  function loadSenseData(cb) {
    if (senseLoaded) { if (cb) cb(); return; }
    if (cb) senseCbs.push(cb);
    if (senseLoading) return;
    senseLoading = true;
    let need = 2;
    const one = () => {
      need -= 1;
      if (need === 0) {
        parseVec(); parseLex();
        senseLoaded = true; senseLoading = false;
        const cbs = senseCbs; senseCbs = []; cbs.forEach((f) => f());
      }
    };
    const inject = (src) => {
      const s = document.createElement("script");
      s.src = src; s.onload = one; s.onerror = one;
      document.head.appendChild(s);
    };
    inject("vec-data.js");
    inject("lex-data.js");
  }

  function cosRows(i, j) {
    let dot = 0; const a = i * vecDim, b = j * vecDim;
    for (let k = 0; k < vecDim; k++) dot += vecMat[a + k] * vecMat[b + k];
    return dot / VEC_SCALE;
  }

  function senseContext(sense) {
    const w = (sense.word || "").trim().toLowerCase();
    if (!w) return null;
    const rel = sense.rel || "related";
    if (rel === "related") {
      const row = vecIdx.has(w) ? vecIdx.get(w) : -1;
      return { rel: rel, w: w, row: row, ok: row >= 0, reason: row >= 0 ? "" : "no word-vector for “" + w + "”" };
    }
    const e = lexMap.get(w) || { syn: new Set(), ant: new Set() };
    if (rel === "synonym") return { rel: rel, w: w, syn: e.syn, ok: true, reason: "" };
    return { rel: rel, w: w, ant: e.ant, ok: e.ant.size > 0, reason: e.ant.size ? "" : "no antonyms known for “" + w + "”" };
  }

  function sensePass(word, ctx) {
    if (ctx.rel === "related") {
      if (ctx.row < 0) return false;
      const r = vecIdx.get(word);
      if (r === undefined) return false;
      return cosRows(ctx.row, r) >= SENSE_THRESHOLD;
    }
    if (ctx.rel === "synonym") {
      if (word === ctx.w || ctx.syn.has(word)) return true;
      return word.indexOf(ctx.w) >= 0 || ctx.w.indexOf(word) >= 0;
    }
    return ctx.ant.has(word); // opposite
  }

  function setSenseStatus(text, warn) {
    if (!senseStatusEl) return;
    senseStatusEl.textContent = text || "";
    senseStatusEl.classList.toggle("warn", !!warn);
  }

  // ---- AI word-sense ----
  // Production: the site is static and keyless — AI calls go through the
  // Technical Rhymer relay on runcabin.com, which holds the key server-side,
  // pins a cheap model, rate-limits, and enforces a daily budget.
  // Local dev: key.local.js (gitignored) sets RF_DEFAULT_KEY and we call
  // Anthropic browser-direct instead.
  function senseProxyUrl() {
    return window.RF_SENSE_PROXY || "https://runcabin.com/api/rhymer/sense";
  }
  function getApiKey() {
    return (window.RF_DEFAULT_KEY || "").trim(); // local-only (key.local.js)
  }

  async function proxySenseMatches(word, rel, candidates) {
    const res = await fetch(senseProxyUrl(), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ word: word, rel: rel, candidates: candidates }),
    });
    if (!res.ok) {
      let detail = "";
      try { const j = await res.json(); detail = j.error || ""; } catch (e) { /* */ }
      throw new Error("HTTP " + res.status + (detail ? " — " + detail : ""));
    }
    const data = await res.json();
    const out = new Set();
    (data.matches || []).forEach((w) => out.add(String(w).toLowerCase()));
    return out;
  }

  const REL_PHRASE = {
    related: "semantically related to or strongly associated with",
    synonym: "synonyms or near-synonyms of (similar in meaning to)",
    opposite: "antonyms or opposites of",
  };

  async function aiSenseMatches(word, rel, candidates, key, model) {
    const prompt =
      "From the candidate word list below, return ONLY the words that are " +
      (REL_PHRASE[rel] || REL_PHRASE.related) + " the target word \"" + word + "\". " +
      "Use real-world knowledge and common-sense association (for example, \"pirates\" is related to \"treasure\", and \"grass\" is related to \"meadow\"). " +
      "Return the exact candidate strings that qualify; if none qualify, return an empty list.\n\nCandidates:\n" +
      candidates.join(", ");
    const body = {
      model: model,
      max_tokens: 4096,
      messages: [{ role: "user", content: prompt }],
      output_config: {
        format: {
          type: "json_schema",
          schema: {
            type: "object", additionalProperties: false, required: ["matches"],
            properties: { matches: { type: "array", items: { type: "string" } } },
          },
        },
      },
    };
    const res = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "anthropic-dangerous-direct-browser-access": "true",
      },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      let detail = "";
      try { const j = await res.json(); detail = (j.error && j.error.message) || ""; } catch (e) { /* */ }
      throw new Error("HTTP " + res.status + (detail ? " — " + detail : ""));
    }
    const data = await res.json();
    const block = (data.content || []).find((b) => b.type === "text");
    if (!block) throw new Error("no text in response");
    const parsed = JSON.parse(block.text);
    const out = new Set();
    (parsed.matches || []).forEach((w) => out.add(String(w).toLowerCase()));
    return out;
  }

  // ctx fields shared by every render call for a tab
  function tabCtx(tab) {
    return { sort: tab.sort, fuzzy: tab.fuzzy, ignoreStress: tab.ignoreStress, mode: tab.mode, live: !!tab.live };
  }

  function applySenseFilter(tab, found, keptSet, label) {
    const kept = found.results.filter((e) => keptSet.has(e.w));
    const keptWords = new Set(kept.map((e) => e.w));
    const dbl = new Map();
    found.doubles.forEach((v, k) => { if (keptWords.has(k)) dbl.set(k, v); });
    setSenseStatus(label);
    const ctx = tabCtx(tab);
    ctx.doubles = dbl;
    ctx.dists = found.dists;
    ctx.sense = { rel: tab.sense.rel, w: tab.sense.word };
    renderResults(kept, found.q, ctx);
  }

  function aiFilterAndRender(tab, found) {
    const sense = tab.sense;
    const key = getApiKey(); // local dev only; production uses the relay
    const engine = key ? "direct:" + senseModel : "proxy";
    const cand = found.results.slice().sort(byCommon).slice(0, AI_CANDIDATE_CAP).map((e) => e.w);
    const cacheKey = sense.rel + "|" + sense.word + "|" + engine + "|" + cand.join(",");
    if (aiCache.has(cacheKey)) {
      const set = aiCache.get(cacheKey);
      applySenseFilter(tab, found, set, set.size.toLocaleString() + " of " + cand.length +
        " are " + sense.rel + " to “" + sense.word + "” (AI)");
      return;
    }
    // keep the current results visible but dimmed while Claude thinks;
    // only fall back to a bare message when there's nothing rendered yet
    const asking = "Asking Claude which rhymes are " + escapeHtml(sense.rel) +
      " to “" + escapeHtml(sense.word) + "”…";
    if (resultsEl.childElementCount) {
      resultsEl.classList.add("filtering");
      const pill = document.createElement("div");
      pill.className = "filter-pill";
      pill.innerHTML = '<span class="spinner"></span>' + asking;
      resultsEl.prepend(pill);
    } else {
      resultsEl.innerHTML = '<div class="empty">' + asking + "</div>";
    }
    setSenseStatus("Asking Claude…");
    const call = key
      ? aiSenseMatches(sense.word, sense.rel, cand, key, senseModel)
      : proxySenseMatches(sense.word, sense.rel, cand);
    call.then((raw) => {
      const candSet = new Set(cand);
      const clean = new Set();
      raw.forEach((w) => { if (candSet.has(w)) clean.add(w); });
      aiCache.set(cacheKey, clean);
      if (activeTabId === tab.id) {
        applySenseFilter(tab, found, clean, clean.size.toLocaleString() + " of " + cand.length +
          " are " + sense.rel + " to “" + sense.word + "” (AI)");
      }
    }).catch((err) => {
      if (activeTabId !== tab.id) return;
      // AI unavailable (rate limit, budget, offline…) — degrade to the
      // bundled word-vector/WordNet filter instead of failing the search.
      setSenseStatus("AI filter unavailable (" + err.message + ") — using the offline filter.", true);
      offlineFilterAndRender(tab, found);
    });
  }

  function offlineFilterAndRender(tab, found) {
    if (!senseLoaded) {
      resultsEl.innerHTML = '<div class="empty">Loading word-sense data…</div>';
      loadSenseData(() => { if (activeTabId === tab.id) renderTabContent(tab); });
      return;
    }
    const ctx = senseContext(tab.sense);
    if (ctx && !ctx.ok) {
      setSenseStatus(ctx.reason + " — showing unfiltered. (Add an API key for smarter results.)", true);
      const rctx = tabCtx(tab);
      rctx.doubles = found.doubles;
      rctx.dists = found.dists;
      renderResults(found.results, found.q, rctx);
      return;
    }
    const keptSet = new Set(found.results.filter((e) => sensePass(e.w, ctx)).map((e) => e.w));
    applySenseFilter(tab, found, keptSet, keptSet.size.toLocaleString() + " of " +
      found.results.length.toLocaleString() + " are " + ctx.rel + " to “" + ctx.w + "” (offline)");
  }

  // one-tap fragment examples for the blank state
  const FRAG_EXAMPLES = [
    { f: "AH N JH", hint: "the orange tail" },
    { f: "EH ZH ER", hint: "treasure, measure…" },
    { f: "UH K IY", hint: "cookie, rookie…" },
    { f: "AO R * JH", hint: "AO R then JH, in order" },
  ];

  function renderTabContent(tab) {
    resultsEl.classList.remove("filtering");
    resultsEl.innerHTML = "";
    if (!tab || !tab.raw.trim()) {
      const chips = FRAG_EXAMPLES.map((x) =>
        '<button type="button" class="ex-chip ex-frag" data-frag="' + escapeAttr(x.f) +
        '" title="' + escapeAttr(x.hint) + '">' + escapeHtml(x.f) + "</button>").join("");
      resultsEl.innerHTML = '<div class="empty">Type or paste a pronunciation fragment above — or try one:' +
        '<div class="empty-actions">' + chips + "</div></div>";
      setSenseStatus("");
      return;
    }
    const found = search(tab.raw, { ignoreStress: tab.ignoreStress, mode: tab.mode, fuzzy: tab.fuzzy });
    const sense = tab.sense;

    if (sense && sense.word) {
      aiFilterAndRender(tab, found); // relay (or local key); falls back to offline
      return;
    }
    setSenseStatus("");
    const ctx = tabCtx(tab);
    ctx.doubles = found.doubles;
    ctx.dists = found.dists;
    renderResults(found.results, found.q, ctx);
  }

  function showTab(id) {
    activeTabId = id;
    renderTabBar();
    renderTabContent(tabById(id));
    resultsEl.scrollIntoView({ behavior: SMOOTH, block: "nearest" });
  }

  function tabTitle(tab) {
    const q = parseQuery(tab.raw, tab.ignoreStress);
    let s = q ? queryDisplay(q) : (tab.raw || "").toUpperCase().trim();
    if (tab.fuzzy) s += " ~";
    return s.length > 22 ? s.slice(0, 21) + "…" : s;
  }

  function tabTooltip(tab) {
    const q = parseQuery(tab.raw, tab.ignoreStress);
    const s = q ? queryDisplay(q) : (tab.raw || "");
    const bits = [tab.mode, tab.fuzzy ? "fuzzy" : null, tab.ignoreStress ? "ignore-stress" : "with-stress", tab.sort];
    return s + "  [" + bits.filter(Boolean).join(" · ") + "]";
  }

  function pinCurrentTab() {
    const live = tabs[0];
    if (!live.raw.trim()) return;
    tabSeq += 1;
    const t = {
      id: "t" + tabSeq, live: false, raw: live.raw, mode: live.mode,
      fuzzy: live.fuzzy, ignoreStress: live.ignoreStress, sort: live.sort,
      sense: { word: (live.sense && live.sense.word) || "", rel: (live.sense && live.sense.rel) || "related" },
    };
    tabs.push(t);
    saveTabs();
    renderTabBar(t.id);  // flash the new tab; stay on live so you can keep searching
  }

  function closeTab(id) {
    const i = tabs.findIndex((t) => t.id === id);
    if (i <= 0) return; // never close the live tab
    tabs.splice(i, 1);
    if (activeTabId === id) { activeTabId = "live"; renderTabContent(tabs[0]); }
    saveTabs();
    renderTabBar();
  }

  function renderTabBar(flashId) {
    tabBarEl.innerHTML = "";
    tabs.forEach((tab) => {
      const b = document.createElement("button");
      b.className = "tab" + (tab.id === activeTabId ? " active" : "") + (tab.live ? " live" : "");
      b.title = tab.live ? "Current search — updates as you search" : tabTooltip(tab);
      const label = document.createElement("span");
      label.className = "tab-label";
      label.textContent = tab.live ? "Live" : tabTitle(tab);
      b.appendChild(label);
      if (!tab.live) {
        const x = document.createElement("span");
        x.className = "tab-close";
        x.innerHTML = icon("ic-x");
        x.title = "Close tab";
        x.addEventListener("click", (e) => { e.stopPropagation(); closeTab(tab.id); });
        b.appendChild(x);
      }
      b.addEventListener("click", () => showTab(tab.id));
      if (tab.id === flashId) b.classList.add("tab-new-flash");
      tabBarEl.appendChild(b);
    });
    const add = document.createElement("button");
    add.className = "tab tab-add";
    add.title = "Pin the current results to a new tab";
    add.innerHTML = icon("ic-plus") + "<span>New tab</span>";
    if (!tabs[0].raw.trim()) add.disabled = true;
    add.addEventListener("click", pinCurrentTab);
    tabBarEl.appendChild(add);
    tabBarEl.hidden = !(tabs.length > 1 || tabs[0].raw.trim());
  }

  function saveTabs() {
    try {
      const pinned = tabs.filter((t) => !t.live).map((t) => ({
        raw: t.raw, mode: t.mode, fuzzy: t.fuzzy, ignoreStress: t.ignoreStress, sort: t.sort, sense: t.sense,
      }));
      localStorage.setItem(TABS_KEY, JSON.stringify(pinned));
    } catch (e) { /* localStorage unavailable */ }
  }

  function loadTabs() {
    try {
      const arr = JSON.parse(localStorage.getItem(TABS_KEY) || "[]");
      arr.forEach((t) => {
        tabSeq += 1;
        tabs.push({ id: "t" + tabSeq, live: false, raw: t.raw || "", mode: t.mode || "end",
          fuzzy: !!t.fuzzy, ignoreStress: t.ignoreStress !== false, sort: t.sort || "common",
          sense: t.sense || { word: "", rel: "related" } });
      });
    } catch (e) { /* ignore */ }
  }

  const RENDER_CAP = 2500;

  // highlight context for the render pass: which fragment tokens matched.
  // Set by renderResults, read by chipHtml. { segs (match-space), fuzzy, ignoreStress }
  let HL = null;
  let DISTS = null; // word -> weighted sound distance (sounds-like renders only)
  let lastWords = []; // words currently listed, in display order (for "Copy list")

  // token indices covered by any (non-overlapping) occurrence of any segment
  function hlIndices(tokens, segs) {
    const idx = new Set();
    for (let s = 0; s < segs.length; s++) {
      const seg = segs[s];
      let i = 0;
      while (i + seg.length <= tokens.length) {
        const k = indexOfSub(tokens, seg, i);
        if (k < 0) break;
        for (let j = k; j < k + seg.length; j++) idx.add(j);
        i = k + seg.length;
      }
    }
    return idx;
  }

  // pronunciation display for a chip, with the matched tokens highlighted.
  // Match keys and display pron have identical token counts (fuzz/strip are 1:1).
  function pronHtml(e) {
    const disp = e.p.split(" ");
    if (!HL) return escapeHtml(e.p);
    const key = HL.fuzzy
      ? (HL.ignoreStress ? e.keyNSF : e.keyF)
      : (HL.ignoreStress ? e.keyNS : e.key);
    const idx = hlIndices(key.split(" "), HL.segs);
    if (!idx.size) return escapeHtml(e.p);
    return disp.map((t, i) => (idx.has(i) ? '<em class="hl">' + escapeHtml(t) + "</em>" : escapeHtml(t))).join(" ");
  }

  function chipHtml(e, dbl) {
    const pct = Math.max(0, Math.min(100, Math.round((e.z / 8) * 100)));
    const sylTxt = e.syl + " syll";
    const isUd = udInfo.has(e.w);
    const nu = newInfo.get(e.w);
    const title = (e.z > 0 ? "commonality (Zipf) " + e.z.toFixed(2) : "rare / not in frequency data") +
      " · " + sylTxt + (isUd ? " · Urban Dictionary (score " + udInfo.get(e.w).toLocaleString() + ")" : "") +
      (nu ? " · new this decade (mainstream since " + nu.year + ")" : "") +
      (dbl ? " · rhyme repeats ×" + dbl : "") +
      (DISTS && DISTS.has(e.w) ? " · sound distance " + DISTS.get(e.w).toFixed(2) : "");
    const udTag = isUd ? ' <span class="ud-tag">UD</span>' : "";
    const newTag = nu ? ' <span class="new-tag">’' + String(nu.year).slice(2) + "</span>" : "";
    const dblTag = dbl ? ' <span class="dbl-tag">×' + dbl + "</span>" : "";
    return '<button class="word-chip' + (dbl ? " is-double" : "") + '" data-w="' + escapeAttr(e.w) + '" title="' + escapeAttr(title) + '">' +
      '<span class="chip-row"><span class="w">' + escapeHtml(e.w) + udTag + newTag + dblTag + "</span>" +
      '<span class="p">' + pronHtml(e) + "</span></span>" +
      '<span class="freq-track"><span class="freq-fill" style="width:' + pct + '%"></span></span>' +
      "</button>";
  }

  // render a flat or syllable-grouped grid for a list of entries
  function gridHtml(list, sort) {
    if (sort === "syllable") {
      const groups = new Map();
      list.forEach((e) => {
        if (!groups.has(e.syl)) groups.set(e.syl, []);
        groups.get(e.syl).push(e);
      });
      return Array.from(groups.keys()).sort((a, b) => a - b).map((s) => {
        const g = groups.get(s);
        return '<div class="syl-group"><h3>' + s + " syllable" + (s === 1 ? "" : "s") +
          " · " + g.length + '</h3><div class="word-grid">' +
          g.map((e) => chipHtml(e)).join("") + "</div></div>";
      }).join("");
    }
    return '<div class="word-grid">' + list.map((e) => chipHtml(e)).join("") + "</div>";
  }

  function renderResults(matches, q, ctx) {
    ctx = ctx || { sort: sortMode, fuzzy: fuzzyEl.checked, ignoreStress: ignoreStressEl.checked, mode: mode };
    resultsEl.classList.remove("filtering");
    const sort = ctx.sort;
    const near = ctx.mode === "near";
    const doubles = (ctx.doubles instanceof Map) ? ctx.doubles : new Map();
    const disp = q ? queryDisplay(q) : "";
    if (!matches.length) {
      const hint = ctx.sense
        ? "No rhymes are <b>" + escapeHtml(ctx.sense.rel) + "</b> to “<b>" + escapeHtml(ctx.sense.w) +
          "</b>”. Try a broader relation, a different word, or turn on <b>Fuzzy</b>."
        : near
        ? "Nothing sounds close enough. Trim the pronunciation to its core, or switch matching to <b>Anywhere</b> to find it inside longer words."
        : "Try fewer phonemes, switch matching to <b>Anywhere</b>, or toggle <b>Ignore stress</b>.";
      // one-tap fixes — only offered on the live tab, where the controls apply
      const acts = [];
      if (ctx.live) {
        if (ctx.sense) {
          acts.push('<button type="button" class="ex-chip js-act" data-act="sense-clear">Clear the sense filter</button>');
          if (ctx.sense.rel !== "related") acts.push('<button type="button" class="ex-chip js-act" data-act="sense-related">Broaden to “Related”</button>');
        } else if (near) {
          // fuzzy/stress toggles don't apply in sounds-like mode
          acts.push('<button type="button" class="ex-chip js-act" data-act="mode-any">Match “Anywhere”</button>');
        } else {
          if (ctx.mode && ctx.mode !== "any") acts.push('<button type="button" class="ex-chip js-act" data-act="mode-any">Match “Anywhere”</button>');
          if (!ctx.fuzzy) acts.push('<button type="button" class="ex-chip js-act" data-act="fuzzy-on">Turn on Fuzzy</button>');
          if (ctx.ignoreStress === false) acts.push('<button type="button" class="ex-chip js-act" data-act="stress-on">Ignore stress</button>');
        }
      }
      resultsEl.innerHTML =
        '<div class="results-meta">No matches for <span class="frag">' + escapeHtml(disp) + "</span></div>" +
        '<div class="empty">' + hint +
        (acts.length ? '<div class="empty-actions">' + acts.join("") + "</div>" : "") + "</div>";
      if (announceEl) announceEl.textContent = "No matches for " + disp;
      return;
    }

    // sort by the chosen mode (most common first by default). Sounds-like
    // results order by distance band first (half-point steps), so the closest
    // sound-alikes lead and the chosen sort ranks within each band.
    DISTS = near && (ctx.dists instanceof Map) ? ctx.dists : null;
    const cmp = sort === "alpha" ? byAlpha : sort === "syllable" ? bySyllable : byCommon;
    let sorted;
    if (DISTS) {
      const D = DISTS;
      const band = (e) => Math.round((D.get(e.w) || 0) * 2);
      sorted = matches.slice().sort((a, b) => (band(a) - band(b)) || cmp(a, b));
    } else {
      sorted = matches.slice().sort(cmp);
    }

    // split off "double rhymes" — words where a rhyme segment repeats (×2+)
    const doubleList = doubles.size ? sorted.filter((e) => doubles.has(e.w)) : [];
    const singleList = doubles.size ? sorted.filter((e) => !doubles.has(e.w)) : sorted;

    // arm the matched-fragment highlighter for this render pass
    if (q) {
      HL = {
        segs: ctx.fuzzy ? q.segs.map((s) => s.map(fuzzToken)) : q.segs,
        fuzzy: !!ctx.fuzzy,
        ignoreStress: ctx.ignoreStress !== false,
      };
    }

    const total = sorted.length;
    const baseSortLabel = sort === "common" ? "most common first"
      : sort === "syllable" ? "by syllables, then common" : "A–Z";
    const sortLabel = near ? "closest first, then " + baseSortLabel : baseSortLabel;
    const fuzzNote = (ctx.fuzzy && !near) ? " · <span class=\"fuzz-note\">fuzzy sounds</span>" : "";
    const nearNote = near ? " · <span class=\"fuzz-note\">sound-alikes, close in pronunciation</span>" : "";
    const senseNote = ctx.sense ? " · <span class=\"fuzz-note\">" + escapeHtml(ctx.sense.rel) +
      " “" + escapeHtml(ctx.sense.w) + "”</span>" : "";

    const meta =
      '<div class="results-meta">' + icon("ic-list") +
      "<span><b style=\"color:var(--text)\">" + total.toLocaleString() + "</b> match" + (total === 1 ? "" : "es") +
      " for <span class=\"frag\">" + escapeHtml(disp) + "</span> · " + sortLabel + fuzzNote + nearNote + senseNote + "</span>" +
      '<button type="button" class="icon-btn js-copy-list" title="Copy the listed words, one per line">' +
      icon("ic-copy") + "Copy list</button></div>";

    let dblSection = "";
    if (doubleList.length) {
      const dShown = doubleList.slice(0, RENDER_CAP);
      dblSection = '<div class="double-section"><h3 class="double-head">' + icon("ic-layers") +
        "Double rhymes · " + doubleList.length + '</h3><div class="word-grid">' +
        dShown.map((e) => chipHtml(e, doubles.get(e.w))).join("") + "</div></div>";
    }

    const sShown = singleList.slice(0, RENDER_CAP);
    const body = sShown.length ? gridHtml(sShown, sort) : "";

    let note = "";
    if (singleList.length > RENDER_CAP) {
      note = '<div class="more-note">Showing the ' +
        (sort === "common" ? "most common " : "first ") + RENDER_CAP.toLocaleString() +
        " of " + singleList.length.toLocaleString() + ". Add more phonemes to narrow it down.</div>";
    }

    resultsEl.innerHTML = meta + dblSection + body + note;
    HL = null;
    DISTS = null;
    lastWords = doubleList.slice(0, RENDER_CAP).concat(singleList.slice(0, RENDER_CAP)).map((e) => e.w);
    if (announceEl) announceEl.textContent = total.toLocaleString() + " match" + (total === 1 ? "" : "es") + " for " + disp;

    Array.from(resultsEl.querySelectorAll(".word-chip")).forEach((chip) => {
      chip.addEventListener("click", () => {
        wordInput.value = chip.getAttribute("data-w");
        syncClearBtns();
        doLookup();
        document.querySelector("header").scrollIntoView({ behavior: SMOOTH, block: "start" });
      });
    });
  }

  // ---- utilities ----
  function speak(word) {
    try {
      if (!window.speechSynthesis) return;
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(word);
      u.rate = 0.95;
      window.speechSynthesis.speak(u);
    } catch (e) { /* no-op */ }
  }

  function copyText(text, btn) {
    const done = () => {
      if (!btn) return;
      btn.classList.add("copied");
      const orig = btn.innerHTML;
      btn.innerHTML = icon("ic-copy") + "Copied";
      setTimeout(() => { btn.classList.remove("copied"); btn.innerHTML = orig; }, 1200);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, () => fallbackCopy(text, done));
    } else {
      fallbackCopy(text, done);
    }
  }
  function fallbackCopy(text, done) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); } catch (e) {}
    document.body.removeChild(ta);
    done();
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function escapeAttr(s) { return escapeHtml(s); }

  // ---- wire up ----
  // explicit lookup (button / Enter) auto-fills the search box for single-pron words;
  // live typing just previews the pronunciation (no auto-fill, no clobbering the box).
  lookupBtn.addEventListener("click", () => doLookup(true));
  wordInput.addEventListener("keydown", (e) => { if (e.key === "Enter") doLookup(true); });
  let liveTimer = null;
  wordInput.addEventListener("input", () => {
    clearTimeout(liveTimer);
    liveTimer = setTimeout(() => doLookup(false), 180);
  });
  // the two "ignore stress" toggles are synced: flipping either updates both
  // (display/copy in step 1 + matching in step 2) and re-renders.
  function setIgnoreStress(on) {
    stripStress1El.checked = on;
    ignoreStressEl.checked = on;
    savePrefs();
    if (wordInput.value.trim()) doLookup();
    if (fragInput.value.trim()) doSearch();
  }
  stripStress1El.addEventListener("change", () => setIgnoreStress(stripStress1El.checked));

  searchBtn.addEventListener("click", doSearch);
  fragInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); doSearch(); }
  });
  ignoreStressEl.addEventListener("change", () => setIgnoreStress(ignoreStressEl.checked));
  fuzzyEl.addEventListener("change", () => { savePrefs(); if (fragInput.value.trim()) doSearch(); });

  // ---- input quality-of-life: auto-grow, clear buttons, shortcuts ----
  function autoGrow() {
    fragInput.style.height = "auto";
    fragInput.style.height = Math.min(fragInput.scrollHeight, 140) + "px";
  }
  function syncClearBtns() {
    if (wordClear) wordClear.hidden = !wordInput.value;
    if (fragClear) fragClear.hidden = !fragInput.value;
  }
  function clearWord() {
    wordInput.value = "";
    syncClearBtns();
    doLookup(); // empty query hides the pron result
    wordInput.focus();
  }
  function clearFrag() {
    fragInput.value = "";
    autoGrow();
    syncClearBtns();
    doSearch(); // renders the blank-state examples + resets URL/title
    fragInput.focus();
  }
  if (wordClear) wordClear.addEventListener("click", clearWord);
  if (fragClear) fragClear.addEventListener("click", clearFrag);
  wordInput.addEventListener("keydown", (e) => { if (e.key === "Escape" && wordInput.value) { e.preventDefault(); clearWord(); } });
  fragInput.addEventListener("keydown", (e) => { if (e.key === "Escape" && fragInput.value) { e.preventDefault(); clearFrag(); } });
  fragInput.addEventListener("input", () => { autoGrow(); syncClearBtns(); });
  wordInput.addEventListener("input", syncClearBtns);

  // "/" jumps to the lookup box from anywhere (unless already typing)
  document.addEventListener("keydown", (e) => {
    if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey) return;
    const t = e.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
    e.preventDefault();
    wordInput.focus();
    wordInput.select();
  });

  // ---- example chips under the lookup box ----
  if (lookupExamples) {
    lookupExamples.addEventListener("click", (e) => {
      const b = e.target.closest(".ex-chip[data-w]");
      if (!b) return;
      wordInput.value = b.getAttribute("data-w");
      syncClearBtns();
      doLookup(true);
    });
  }

  // ---- phoneme keyboard: tap sounds/operators to build the search box ----
  if (phonePanel) {
    phonePanel.addEventListener("click", (e) => {
      const key = e.target.closest(".ph-key");
      if (!key) return;
      const act = key.getAttribute("data-act");
      if (act === "clear") {
        fragInput.value = "";
      } else if (act === "back") {
        const toks = fragInput.value.trim().split(/\s+/).filter(Boolean);
        toks.pop();
        fragInput.value = toks.length ? toks.join(" ") + " " : "";
      } else {
        const ph = key.getAttribute("data-ph");
        const v = fragInput.value;
        fragInput.value = v + (v && !/\s$/.test(v) ? " " : "") + ph + " ";
      }
      autoGrow();
      syncClearBtns();
    });
  }

  // ---- delegated actions inside the results area ----
  resultsEl.addEventListener("click", (e) => {
    const frag = e.target.closest(".ex-frag");
    if (frag) { sendToSearch(frag.getAttribute("data-frag")); return; }
    const copyBtn = e.target.closest(".js-copy-list");
    if (copyBtn) { if (lastWords.length) copyText(lastWords.join("\n"), copyBtn); return; }
    const act = e.target.closest(".js-act");
    if (act) runEmptyAction(act.getAttribute("data-act"));
  });
  function runEmptyAction(a) {
    if (a === "mode-any") {
      const b = matchBtns.find((x) => x.getAttribute("data-mode") === "any");
      if (b) b.click();
    } else if (a === "fuzzy-on") {
      fuzzyEl.checked = true;
      doSearch();
    } else if (a === "stress-on") {
      setIgnoreStress(true);
    } else if (a === "sense-clear") {
      senseClearEl.click();
    } else if (a === "sense-related") {
      const b = senseRelBtns.find((x) => x.getAttribute("data-rel") === "related");
      if (b) b.click();
    }
  }

  // ---- slant-rhyme (fuzzy) group editor ----
  // Two independent sections: consonants (seeded defaults) and vowels
  // (unseeded — all loose until the user groups them). A picked-up sound can
  // only drop into boxes of its own section, so a vowel can never land in a
  // consonant group or vice versa.
  const fuzzyDialog = $("fuzzyDialog");
  const fzGroupsEl = $("fzGroups");
  const fzvGroupsEl = $("fzvGroups");
  const fuzzyCustomTag = $("fuzzyCustomTag");
  let fzEdit = null;      // consonant working copy while the dialog is open
  let fzvEdit = null;     // vowel working copy
  let fzPicked = null;    // sound currently "picked up"
  let fzPickedSet = null; // which section it came from: "cons" | "vows"

  function syncFuzzyTag() {
    if (fuzzyCustomTag) fuzzyCustomTag.hidden = fuzzyIsDefault(fuzzyGroups) && vowelsIsDefault(vowelGroups);
  }

  function fzLoose(groups, alphabet) {
    const used = new Set();
    groups.forEach((g) => g.forEach((c) => used.add(c)));
    return alphabet.filter((c) => !used.has(c));
  }

  function renderFzSection(rootEl, edit, alphabet, setName, looseLabel) {
    if (!rootEl) return;
    rootEl.innerHTML = "";
    const picked = fzPickedSet === setName ? fzPicked : null;
    const removeFromAll = (c) => edit.forEach((g) => {
      const i = g.indexOf(c);
      if (i >= 0) g.splice(i, 1);
    });
    const mkChip = (c) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "ph-key fz-chip" + (picked === c ? " picked" : "");
      b.title = picked === c ? "Tap a group to move " + c + " there" : "Pick up " + c;
      b.innerHTML = "<b></b>";
      b.firstChild.textContent = c;
      b.addEventListener("click", (e) => {
        e.stopPropagation(); // don't also trigger the box's move handler
        if (fzPicked === c && fzPickedSet === setName) { fzPicked = null; fzPickedSet = null; }
        else { fzPicked = c; fzPickedSet = setName; }
        renderFzEditor();
      });
      return b;
    };
    const mkBox = (label, chips, drop) => {
      const box = document.createElement("div");
      box.className = "fz-box" + (picked ? " droppable" : "");
      const h = document.createElement("div");
      h.className = "fz-box-label";
      h.textContent = label;
      box.appendChild(h);
      const row = document.createElement("div");
      row.className = "fz-row";
      chips.forEach((c) => row.appendChild(mkChip(c)));
      box.appendChild(row);
      const doDrop = () => {
        if (picked == null) return;
        drop(picked);
        fzPicked = null;
        fzPickedSet = null;
        renderFzEditor();
      };
      box.addEventListener("click", doDrop);
      if (picked != null) {
        // keyboard path: a picked-up chip must be droppable without a mouse
        box.tabIndex = 0;
        box.setAttribute("role", "button");
        box.setAttribute("aria-label", "Move " + picked + " to " + label);
        box.addEventListener("keydown", (e) => {
          if (e.key !== "Enter" && e.key !== " ") return;
          e.preventDefault();
          doDrop();
        });
      }
      return box;
    };
    edit.forEach((g, gi) => {
      rootEl.appendChild(mkBox("Group " + (gi + 1), g, (c) => { removeFromAll(c); g.push(c); }));
    });
    rootEl.appendChild(mkBox(looseLabel, fzLoose(edit, alphabet), removeFromAll));
  }

  function renderFzEditor() {
    renderFzSection(fzGroupsEl, fzEdit, ALL_CONSONANTS, "cons", "Loose sounds — each matches only itself");
    renderFzSection(fzvGroupsEl, fzvEdit, ALL_VOWELS, "vows", "Loose vowels — each matches only itself");
  }

  function openFuzzyDialog() {
    fzEdit = fuzzyGroups.map((g) => g.slice());
    fzvEdit = vowelGroups.map((g) => g.slice());
    fzPicked = null;
    fzPickedSet = null;
    renderFzEditor();
    if (typeof fuzzyDialog.showModal === "function") fuzzyDialog.showModal();
    else fuzzyDialog.setAttribute("open", "");
  }
  function closeFuzzyDialog() {
    fzPicked = null;
    fzPickedSet = null;
    if (fuzzyDialog.open) fuzzyDialog.close();
    else fuzzyDialog.removeAttribute("open");
  }

  if (fuzzyDialog) {
    $("fuzzyCfg").addEventListener("click", openFuzzyDialog);
    $("fzClose").addEventListener("click", closeFuzzyDialog);
    $("fzCancel").addEventListener("click", closeFuzzyDialog);
    $("fzNewGroup").addEventListener("click", () => { if (fzEdit) { fzEdit.push([]); renderFzEditor(); } });
    $("fzvNewGroup").addEventListener("click", () => { if (fzvEdit) { fzvEdit.push([]); renderFzEditor(); } });
    $("fzReset").addEventListener("click", () => {
      if (!fzEdit) return;
      fzEdit = DEFAULT_FUZZY_GROUPS.map((g) => g.slice());
      fzvEdit = DEFAULT_VOWEL_GROUPS.map((g) => g.slice());   // = all vowels loose
      fzPicked = null;
      fzPickedSet = null;
      renderFzEditor();
    });
    $("fzDone").addEventListener("click", () => {
      if (!fzEdit) return;
      // groups need 2+ sounds; anything smaller falls loose (matches itself)
      fuzzyGroups = fzEdit.map((g) => g.slice()).filter((g) => g.length >= 2);
      vowelGroups = fzvEdit.map((g) => g.slice()).filter((g) => g.length >= 2);
      CONS_MAP = buildRepMap(fuzzyGroups);
      VOW_MAP = buildRepMap(vowelGroups);
      try {
        if (fuzzyIsDefault(fuzzyGroups)) localStorage.removeItem(FUZZY_KEY);
        else localStorage.setItem(FUZZY_KEY, JSON.stringify(fuzzyGroups));
        if (vowelsIsDefault(vowelGroups)) localStorage.removeItem(VOWEL_FUZZY_KEY);
        else localStorage.setItem(VOWEL_FUZZY_KEY, JSON.stringify(vowelGroups));
      } catch (e) { /* localStorage unavailable */ }
      rebuildFuzzKeys();
      syncFuzzyTag();
      closeFuzzyDialog();
      // refresh whatever the user is LOOKING AT — pinned tabs re-run search()
      // against the rebuilt keys too, and live re-renders even when the box
      // was cleared after its last search
      if (activeTabId === "live" && fragInput.value.trim()) doSearch();
      else { const t = tabById(activeTabId); if (t) renderTabContent(t); }
    });
  }

  // ---- back to top ----
  if (toTopBtn) {
    window.addEventListener("scroll", () => { toTopBtn.hidden = window.scrollY < 600; }, { passive: true });
    toTopBtn.addEventListener("click", () => window.scrollTo({ top: 0, behavior: SMOOTH }));
  }

  // word-sense panel (offline bundles load lazily only if the AI path fails)
  let senseTimer = null;
  senseWordEl.addEventListener("input", () => {
    clearTimeout(senseTimer);
    senseTimer = setTimeout(() => { if (fragInput.value.trim()) doSearch(); }, 220);
  });
  senseWordEl.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); if (fragInput.value.trim()) doSearch(); } });
  senseClearEl.addEventListener("click", () => {
    senseWordEl.value = ""; setSenseStatus("");
    if (fragInput.value.trim()) doSearch();
  });
  senseRelBtns.forEach((b) => {
    b.addEventListener("click", () => {
      senseRelBtns.forEach((o) => o.classList.remove("on"));
      b.classList.add("on");
      senseRel = b.getAttribute("data-rel");
      savePrefs();
      if (senseWordEl.value.trim() && fragInput.value.trim()) doSearch();
    });
  });
  sensePanelEl.addEventListener("toggle", savePrefs);
  if (phonePanel) phonePanel.addEventListener("toggle", savePrefs);
  matchBtns.forEach((b) => {
    b.addEventListener("click", () => {
      matchBtns.forEach((o) => o.classList.remove("on"));
      b.classList.add("on");
      mode = b.getAttribute("data-mode");
      savePrefs();
      if (fragInput.value.trim()) doSearch();
    });
  });
  sortBtns.forEach((b) => {
    b.addEventListener("click", () => {
      sortBtns.forEach((o) => o.classList.remove("on"));
      b.classList.add("on");
      sortMode = b.getAttribute("data-sort");
      savePrefs();
      if (fragInput.value.trim()) doSearch();
    });
  });

  // ---- drop your best line (the wall) ----
  // Backend = /api/rhymer/lines on runcabin.com — a fixed-function relay next
  // to the sense proxy: it AI-checks every submission for spam before it goes
  // on the wall (see RhymerLinesController in the Cabin repo). The whole
  // section stays hidden unless the wall GET answers, so the page still works
  // over file:// and degrades cleanly if the endpoint is down or not yet
  // deployed.
  const PEN_KEY = "rf_penname";
  function linesApiUrl() {
    return window.RF_LINES_URL || "https://runcabin.com/api/rhymer/lines";
  }

  function lineWhen(iso) {
    const d = new Date(iso);
    if (isNaN(d)) return "";
    const opts = { month: "short", day: "numeric" };
    if (d.getFullYear() !== new Date().getFullYear()) opts.year = "numeric";
    return d.toLocaleDateString(undefined, opts);
  }

  function lineCard(entry, fresh) {
    const fig = document.createElement("figure");
    fig.className = "line-card" + (fresh ? " fresh" : "");
    const q = document.createElement("blockquote");
    q.textContent = entry.line;           // textContent only — never HTML
    const cap = document.createElement("figcaption");
    const pen = document.createElement("span");
    pen.className = "line-pen";
    pen.textContent = "— " + entry.penName;
    const when = document.createElement("span");
    when.className = "line-when";
    when.textContent = lineWhen(entry.at);
    cap.append(pen, when);
    fig.append(q, cap);
    return fig;
  }

  function renderWall(lines) {
    const wall = $("linesWall");
    wall.textContent = "";
    if (!lines.length) {
      const empty = document.createElement("p");
      empty.className = "lines-empty";
      empty.textContent = "The wall is fresh — no lines yet. Yours could be the first.";
      wall.appendChild(empty);
      return;
    }
    lines.forEach((l) => wall.appendChild(lineCard(l, false)));
  }

  function linesNoteSet(msg, kind) {
    const note = $("linesNote");
    note.textContent = msg;
    note.classList.remove("ok", "err");
    if (kind) note.classList.add(kind);
  }

  function initLines() {
    const panel = $("linesPanel");
    const form = $("linesForm");
    const penEl = $("penName");
    const lineEl = $("lineInput");
    const btn = $("lineSubmit");
    if (!panel || !form) return;

    let request;
    try {
      request = fetch(linesApiUrl());
    } catch (e) { return; }   // file:// quirks — keep the section hidden
    request
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("wall " + r.status))))
      .then((data) => {
        renderWall(data.lines || []);
        // Reveal BEFORE touching localStorage: with cookies/site-data blocked,
        // even reading window.localStorage throws, and we must not let a lost
        // pen-name prefill hide the whole (successfully rendered) wall.
        panel.hidden = false;
        try { penEl.value = localStorage.getItem(PEN_KEY) || ""; } catch (e) {}
      })
      .catch(() => {});       // backend absent — section stays hidden

    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const penName = penEl.value.trim();
      const line = lineEl.value.trim();
      if (penName.length < 1) { linesNoteSet("Pick a pen name first.", "err"); penEl.focus(); return; }
      if (line.length < 4) { linesNoteSet("That line needs a few more syllables.", "err"); lineEl.focus(); return; }

      btn.disabled = true;
      btn.classList.add("busy");
      linesNoteSet("Checking your line…");

      fetch(linesApiUrl(), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ penName: penName, line: line }),
      })
        .then((r) => {
          if (r.status === 429) throw new Error("slow-down");
          return r.json().then((d) => ({ http: r.status, d }));
        })
        .then(({ http, d }) => {
          if (d.status === "approved") {
            try { localStorage.setItem(PEN_KEY, penName); } catch (e) {}
            const wall = $("linesWall");
            const empty = wall.querySelector(".lines-empty");
            if (empty) empty.remove();
            wall.prepend(lineCard({ penName: d.penName, line: d.line, at: d.at }, true));
            lineEl.value = "";
            linesNoteSet("That's a bar — it's on the wall.", "ok");
            if (announceEl) announceEl.textContent = "Your line is on the wall.";
          } else if (d.status === "rejected") {
            linesNoteSet(d.reason || "That one didn't make the wall.", "err");
          } else {
            linesNoteSet(d.error || "Couldn't check your line right now — try again in a minute.", "err");
          }
        })
        .catch((err) => {
          linesNoteSet(err && err.message === "slow-down"
            ? "Easy — three drops a minute. Give it a moment."
            : "Couldn't reach the wall — try again in a minute.", "err");
        })
        .finally(() => {
          btn.disabled = false;
          btn.classList.remove("busy");
        });
    });
  }

  // ---- boot ----
  function boot() {
    loadPrefs(); // sticky settings first; a ?q= URL below still overrides
    syncFuzzyTag();
    statusEl.innerHTML = '<span class="loading-pill"><span class="spinner"></span>Loading dictionary…</span>';
    // defer parse one frame so the loading state paints
    setTimeout(() => {
      const t0 = performance.now ? performance.now() : 0;
      parseData();
      const ms = performance.now ? Math.round(performance.now() - t0) : 0;
      statusEl.innerHTML =
        "<b style=\"color:var(--muted)\">" + entries.length.toLocaleString() +
        "</b> pronunciations loaded" + (ms ? " in " + ms + " ms" : "") +
        " · CMU Pronouncing Dictionary + " + udInfo.size.toLocaleString() +
        " Urban Dictionary terms + " + newInfo.size.toLocaleString() +
        " new words of the 2020s · ranked by commonality.";
      [wordInput, lookupBtn, fragInput, searchBtn].forEach((el) => el.removeAttribute("disabled"));
      initLines();   // best-lines wall — reveals itself only if the API answers
      loadTabs();
      renderTabBar();
      syncClearBtns();
      if (!restoreFromUrl()) {
        renderTabContent(tabs[0]); // blank state with tap-to-try examples
        wordInput.focus();
      }
    }, 30);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
