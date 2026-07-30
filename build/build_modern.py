#!/usr/bin/env python3
"""Build mod-data.js: words that entered general English roughly 2000-2026 and
are missing from every layer the site already has.

This is the NON-SLANG counterpart to build_new.py. Urban Dictionary gave us
the slang of the decade; this file covers the ordinary modern vocabulary a
2026 writer needs and a 1998 dictionary cannot have: podcast derivatives,
platform names, cybersecurity, AI, crypto, COVID, climate, gender and
identity language, food that arrived with the 2010s, and the science of the
last twenty years.

SELECTION (audited 2026-07-30)
1. A curated candidate list, category by category, of terms whose general
   currency began 2000 or later. Coinages that are really 1990s natives
   (webcam, malware, emoticon, javascript) are deliberately out — the brief
   is this century's lexicon.
2. A data-driven gap sweep backstopped the curation: every word in
   wordfreq's top 120k that the site could not look up was reviewed, which is
   how the inflections (podcasts, retweeted, hoodies) and the terms nobody
   thinks to list (relatable, positivity, remastered) got in. wordfreq's
   corpora end ~2021, so 2022-2026 terms come from curation only.
3. Anything already searchable via CMUdict, ud-data.js or new-data.js is
   dropped at build time — no duplicate keys, no churn in the existing sets.
4. Inflections are generated mechanically (plural / -ing / -ed / -er) and
   kept only when wordfreq shows the form in real use (zipf >= INFL_MIN_ZIPF)
   and the site lacks it.

PRONUNCIATIONS are built in four ways, in this order of preference:
1. PRON  - hand-written. Initialisms (ASMR, PPE, CBD), brand coinages (Lyft,
   Venmo, Shopify), loanwords (gochujang, halloumi, za'atar) and clipped
   compounds (fintech, e-bike). g2p cannot reach any of these.
2. PARTS - composed from the real CMUdict pronunciations of the parts
   ("touchscreen" = touch + screen). g2p is genuinely bad at compounds: it
   returned T UW0 K S K R EY1 N for touchscreen, B AY2 P AA1 L S T AH0 K for
   bioplastic and G L AA1 V G ER0 Z for vloggers. Composing from CMUdict is
   both correct and auditable. Stress: a Germanic compound keeps primary on
   its first element (TOUCH-screen) and a Latinate prefix moves it onto the
   root (micro-PLAS-tic) — hence LATIN_PREFIX.
3. Suffix rules - an inflected form is its base pronunciation plus the regular
   ending, with English voicing agreement (podcast + S, vlogger + Z,
   fanbase + IH0 Z). Never re-run g2p on an inflected form; that is how
   "vloggers" came out as G L AA1 V G ER0 Z.
4. g2p_en - everything left, which is the ordinary morphology it handles well.

Every g2p-generated pronunciation in this file was reviewed by hand against
the term; the PRON and PARTS tables are what that review produced.

Output line format (../mod-data.js, window.MOD_DATA):
  term \t phonemes \t zipf \t year \t category
- term      : lowercased headword or phrase
- phonemes  : ARPABET (hand-written where PRON has an entry, else g2p)
- zipf      : wordfreq commonality, floored at FLOOR_ZIPF so a genuinely new
              term that no corpus has seen yet still outranks nothing at all
- year      : roughly when the term entered general use (display: "since 2015")
- category  : one of the CATEGORIES below, for the badge tooltip

Helpers (clean_term / arpabet / LETTER) mirror build_ud.py and build_new.py —
the build scripts in this directory are standalone by convention.
"""
import os
import re
from wordfreq import zipf_frequency
from g2p_en import G2p

HERE = os.path.dirname(os.path.abspath(__file__))
CMUDICT = os.path.join(HERE, "cmudict.dict")
UD = os.path.join(HERE, "..", "ud-data.js")
NEW = os.path.join(HERE, "..", "new-data.js")
OUT = os.path.join(HERE, "..", "mod-data.js")

FLOOR_ZIPF = 1.60      # a 2020s term wordfreq has never seen still sorts above junk
INFL_MIN_ZIPF = 2.00   # generated inflections need this much real-world use

# wordfreq scores a multi-word string by combining its words as if they were
# independent, which badly OVERSTATES a specific collocation: it puts "girl
# power" at 5.14, up among the most common words in English. Uncapped, phrases
# would bury genuinely common single words in the commonality sort. Cap them
# below everyday vocabulary but above slang.
PHRASE_CAP = 3.40

CATEGORIES = ("internet", "tech", "ai", "crypto", "covid", "health",
              "climate", "business", "society", "culture", "music", "food",
              "science")

# ---------------------------------------------------------------- pronunciations
# Hand-written where g2p_en cannot get there: initialisms (spoken as letters or
# as an acronym), brand coinages, loanwords, and clipped compounds.
PRON = {
    # initialisms spoken letter by letter
    "asmr": "EY1 EH1 S EH1 M AA1 R",
    "ppe": "P IY1 P IY1 IY1",
    "cbd": "S IY1 B IY1 D IY1",
    "thc": "T IY1 EY1 CH S IY1",
    "vpn": "V IY1 P IY1 EH1 N",
    "dslr": "D IY1 EH1 S EH1 L AA1 R",
    "mbps": "EH1 M B IY1 P IY1 EH1 S",
    "rfid": "AA1 R EH1 F AY1 D IY1",
    "bnpl": "B IY1 EH1 N P IY1 EH1 L",
    "copd": "S IY1 OW1 P IY1 D IY1",
    "etf": "IY1 T IY1 EH1 F",
    "etfs": "IY1 T IY1 EH1 F S",
    "esg": "IY1 EH1 S JH IY1",
    "agi": "EY1 JH IY1 AY1",
    "llm": "EH1 L EH1 L EH1 M",
    "gpt": "JH IY1 P IY1 T IY1",
    "tpu": "T IY1 P IY1 Y UW1",
    "imdb": "AY1 EH1 M D IY1 B IY1",
    "aapi": "EY1 EY1 P IY1 AY1",
    "mrna": "EH1 M AA1 R EH1 N EY1",
    "nft": "EH1 N EH1 F T IY1",
    "nfts": "EH1 N EH1 F T IY1 Z",
    "nfc": "EH1 N EH1 F S IY1",
    "ios": "AY1 OW1 EH1 S",
    "macos": "M AE1 K OW1 EH1 S",
    "usb-c": "Y UW1 EH1 S B IY1 S IY1",
    "glp-1": "JH IY1 EH1 L P IY1 W AH1 N",
    "qr code": "K Y UW1 AA1 R K OW1 D",
    "airbnb": "EH1 R B IY1 EH1 N B IY1",
    "chatgpt": "CH AE1 T JH IY1 P IY1 T IY1",
    # initialisms spoken as words
    "oled": "OW1 L EH2 D",
    "ddos": "D IY1 D AO2 S",
    "ebitda": "IY0 B IH1 T D AH0",
    "cagr": "K EY1 G ER0",
    "mrsa": "M ER1 S AH0",
    "saas": "S AE1 S",
    "paas": "P AE1 S",
    "iaas": "AY1 AA0 S",
    "bipoc": "B AY1 P AA2 K",
    "daca": "D AA1 K AH0",
    "maga": "M AA1 G AH0",
    "qanon": "K Y UW1 AH0 N AA2 N",
    "nimby": "N IH1 M B IY0",
    "yimby": "Y IH1 M B IY0",
    "fomo": "F OW1 M OW0",
    "jomo": "JH OW1 M OW0",
    "hiit": "HH IH1 T",
    "mpox": "EH1 M P AA2 K S",
    "covid": "K OW1 V IH0 D",
    "covid-19": "K OW1 V IH0 D N AY2 N T IY2 N",
    "long covid": "L AO1 NG K OW1 V IH0 D",
    "defi": "D IY1 F AY0",
    "dao": "D AW1",
    "web3": "W EH1 B TH R IY1",
    "spac": "S P AE1 K",
    "json": "JH EY1 S AH0 N",
    "jquery": "JH EY1 K W IH1 R IY0",
    # clipped / hyphenated compounds
    "e-bike": "IY1 B AY2 K",
    "e-scooter": "IY1 S K UW2 T ER0",
    "e-commerce": "IY1 K AA2 M ER0 S",
    "ecommerce": "IY1 K AA2 M ER0 S",
    "e-waste": "IY1 W EY2 S T",
    "k-pop": "K EY1 P AA2 P",
    "kpop": "K EY1 P AA2 P",
    "lo-fi": "L OW1 F AY1",
    "fintech": "F IH1 N T EH2 K",
    "insurtech": "IH1 N SH ER0 T EH2 K",
    "proptech": "P R AA1 P T EH2 K",
    "edtech": "EH1 D T EH2 K",
    "agtech": "AE1 G T EH2 K",
    "healthtech": "HH EH1 L TH T EH2 K",
    "adtech": "AE1 D T EH2 K",
    "martech": "M AA1 R T EH2 K",
    "devops": "D EH1 V AA2 P S",
    "typescript": "T AY1 P S K R IH2 P T",
    "nodejs": "N OW1 D JH EY1 EH1 S",
    "powershell": "P AW1 ER0 SH EH2 L",
    "zero-day": "Z IH1 R OW0 D EY2",
    "dark web": "D AA1 R K W EH1 B",
    "spear phishing": "S P IH1 R F IH1 SH IH0 NG",
    # brand and platform coinages
    "lyft": "L IH1 F T",
    "venmo": "V EH1 N M OW0",
    "shopify": "SH AA1 P AH0 F AY2",
    "patreon": "P EY1 T R IY0 AA2 N",
    "doordash": "D AO1 R D AE2 SH",
    "instacart": "IH1 N S T AH0 K AA2 R T",
    "tiktok": "T IH1 K T AA2 K",
    "tiktoker": "T IH1 K T AA2 K ER0",
    "youtuber": "Y UW1 T UW2 B ER0",
    "subreddit": "S AH1 B R EH2 D IH0 T",
    "redditor": "R EH1 D IH0 T ER0",
    "bluesky": "B L UW1 S K AY2",
    "substack": "S AH1 B S T AE2 K",
    "onlyfans": "OW1 N L IY0 F AE2 N Z",
    "wordle": "W ER1 D AH0 L",
    "oculus": "AA1 K Y AH0 L AH0 S",
    "soundcloud": "S AW1 N D K L AW2 D",
    "gofundme": "G OW1 F AH1 N D M IY2",
    "groupon": "G R UW1 P AA2 N",
    "indiegogo": "IH1 N D IY0 G OW2 G OW0",
    "bandcamp": "B AE1 N D K AE2 M P",
    "grindr": "G R AY1 N D ER0",
    "okcupid": "OW2 K EY1 K Y UW1 P IH0 D",
    "tripadvisor": "T R IH1 P AH0 D V AY2 Z ER0",
    "vimeo": "V IH1 M IY0 OW2",
    "wechat": "W IY1 CH AE2 T",
    "weibo": "W EY1 B OW0",
    "alibaba": "AA2 L IY0 B AA1 B AH0",
    "tencent": "T EH1 N S EH2 N T",
    "bytedance": "B AY1 T D AE2 N S",
    "temu": "T IY1 M UW0",
    "shein": "SH IY1 IH0 N",
    "peloton": "P EH1 L AH0 T AA2 N",
    "coinbase": "K OY1 N B EY2 S",
    "spacex": "S P EY1 S EH1 K S",
    "starlink": "S T AA1 R L IH2 NG K",
    "ozempic": "OW0 Z EH1 M P IH0 K",
    "juul": "JH UW1 L",
    "juuling": "JH UW1 L IH0 NG",
    "fitbit": "F IH1 T B IH2 T",
    "kubernetes": "K UW2 B ER0 N EH1 T IY0 Z",
    # crypto
    "bitcoin": "B IH1 T K OY2 N",
    "ethereum": "IH0 TH IH1 R IY0 AH0 M",
    "blockchain": "B L AA1 K CH EY2 N",
    "stablecoin": "S T EY1 B AH0 L K OY2 N",
    "altcoin": "AO1 L T K OY2 N",
    "dogecoin": "D OW1 JH K OY2 N",
    "litecoin": "L AY1 T K OY2 N",
    "satoshi": "S AH0 T OW1 SH IY0",
    "tokenomics": "T OW2 K AH0 N AA1 M IH0 K S",
    "metaverse": "M EH1 T AH0 V ER2 S",
    # medicine
    "semaglutide": "S EH2 M AH0 G L UW1 T AY0 D",
    "tirzepatide": "T ER0 Z EH1 P AH0 T AY2 D",
    "crispr": "K R IH1 S P ER0",
    "omicron": "AA1 M IH0 K R AA2 N",
    "vax": "V AE1 K S",
    "vaxxed": "V AE1 K S T",
    "unvaxxed": "AH0 N V AE1 K S T",
    "antivaxxer": "AE2 N T IY0 V AE1 K S ER0",
    "immunocompromised": "IH0 M Y UW2 N OW0 K AA1 M P R AH0 M AY2 Z D",
    "comorbidity": "K OW2 M AO0 R B IH1 D AH0 T IY0",
    "seroprevalence": "S IH2 R OW0 P R EH1 V AH0 L AH0 N S",
    "telehealth": "T EH1 L AH0 HH EH2 L TH",
    "nootropic": "N OW2 AH0 T R OW1 P IH0 K",
    # food loanwords
    "boba": "B OW1 B AH0",
    "matcha": "M AA1 CH AH0",
    "gochujang": "G OW1 CH UW0 JH AA2 NG",
    "birria": "B IH1 R IY0 AH0",
    "elote": "EH0 L OW1 T EY0",
    "shakshuka": "SH AH0 K SH UW1 K AH0",
    "harissa": "HH ER0 IY1 S AH0",
    "za'atar": "Z AA1 T AA2 R",
    "labneh": "L AE1 B N EH0",
    "freekeh": "F R IY1 K AH0",
    "aquafaba": "AA2 K W AH0 F AA1 B AH0",
    "halloumi": "HH AH0 L UW1 M IY0",
    "burrata": "B UH0 R AA1 T AH0",
    "cronut": "K R OW1 N AH2 T",
    "cortado": "K AO0 R T AA1 D OW0",
    "seitan": "S EY1 T AE2 N",
    "tempeh": "T EH1 M P EY2",
    "jackfruit": "JH AE1 K F R UW2 T",
    "acai": "AA2 S AA0 IY1",
    "ube": "UW1 B EY2",
    "yuzu": "Y UW1 Z UW0",
    "mocktail": "M AA1 K T EY2 L",
    "gastropub": "G AE1 S T R OW0 P AH2 B",
    "spiralizer": "S P AY1 R AH0 L AY2 Z ER0",
    "locavore": "L OW1 K AH0 V AO2 R",
    "flexitarian": "F L EH2 K S IH0 T EH1 R IY0 AH0 N",
    # culture
    "athleisure": "AE0 TH L IY1 ZH ER0",
    "balayage": "B AA2 L AH0 Y AA1 ZH",
    "niacinamide": "N AY2 AH0 S IH1 N AH0 M AY2 D",
    "cottagecore": "K AA1 T IH0 JH K AO2 R",
    "vanlife": "V AE1 N L AY2 F",
    "parasocial": "P EH2 R AH0 S OW1 SH AH0 L",
    "isekai": "IY2 S EH0 K AY1",
    "gacha": "G AA1 CH AH0",
    "afrobeats": "AE1 F R OW0 B IY2 T S",
    "hyperpop": "HH AY1 P ER0 P AA2 P",
    "vaporwave": "V EY1 P ER0 W EY2 V",
    "synthwave": "S IH1 N TH W EY2 V",
    "fanfic": "F AE1 N F IH2 K",
    "glamping": "G L AE1 M P IH0 NG",
    "roguelike": "R OW1 G L AY2 K",
    "permadeath": "P ER1 M AH0 D EH2 TH",
    "pickleball": "P IH1 K AH0 L B AO2 L",
    "padel": "P AH0 D EH1 L",
    "sneakerhead": "S N IY1 K ER0 HH EH2 D",
    "speedrun": "S P IY1 D R AH2 N",
    "speedrunner": "S P IY1 D R AH2 N ER0",
    "loadout": "L OW1 D AW2 T",
    "metagame": "M EH1 T AH0 G EY2 M",
    "lootbox": "L UW1 T B AA2 K S",
    "esports": "IY1 S P AO2 R T S",
    # climate
    "solarpunk": "S OW1 L ER0 P AH2 NG K",
    "degrowth": "D IY0 G R OW1 TH",
    "agrivoltaics": "AE2 G R IH0 V OW0 L T EY1 IH0 K S",
    "biochar": "B AY1 OW0 CH AA2 R",
    "anthropocene": "AE1 N TH R AH0 P AH0 S IY2 N",
    "microgrid": "M AY1 K R OW0 G R IH2 D",
    "gigafactory": "G IH1 G AH0 F AE2 K T ER0 IY0",
    "perovskite": "P ER0 AA1 V S K AY2 T",
    "heat dome": "HH IY1 T D OW1 M",
    "net zero": "N EH1 T Z IH1 R OW0",
    "eco-anxiety": "IY1 K OW0 AE0 NG Z AY1 AH0 T IY0",
    # business / society
    "neobank": "N IY1 OW0 B AE2 NG K",
    "decacorn": "D EH1 K AH0 K AO2 R N",
    "shrinkflation": "SH R IH1 NG K F L EY2 SH AH0 N",
    "greedflation": "G R IY1 D F L EY2 SH AH0 N",
    "friendshoring": "F R EH1 N D SH AO2 R IH0 NG",
    "workation": "W ER0 K EY1 SH AH0 N",
    "staycation": "S T EY0 K EY1 SH AH0 N",
    "latinx": "L AE1 T IH0 N EH2 K S",
    "tradwife": "T R AE1 D W AY2 F",
    "sharenting": "SH EH1 R AH0 N T IH0 NG",
    "brexit": "B R EH1 K S IH0 T",
    "brexiteer": "B R EH2 K S IH0 T IH1 R",
    "whataboutism": "W AH2 T AH0 B AW1 T IH0 Z AH0 M",
    "infodemic": "IH2 N F OW0 D EH1 M IH0 K",
    "manosphere": "M AE1 N AH0 S F IH2 R",
    "incel": "IH1 N S EH2 L",
    "mansplain": "M AE1 N S P L EY2 N",
    "mansplaining": "M AE1 N S P L EY2 N IH0 NG",
    "humblebrag": "HH AH1 M B AH0 L B R AE2 G",
    "hangry": "HH AE1 NG G R IY0",
    "nomophobia": "N OW2 M AH0 F OW1 B IY0 AH0",
    "adulting": "AH0 D AH1 L T IH0 NG",
    "frenemy": "F R EH1 N AH0 M IY0",
    "throuple": "TH R AH1 P AH0 L",
    "polyamory": "P AA2 L IY0 AE1 M ER0 IY0",
    "enshittification": "EH0 N SH IH2 T IH0 F IH0 K EY1 SH AH0 N",
    "deplatform": "D IY0 P L AE1 T F AO2 R M",
    "mukbang": "M UH1 K B AE2 NG",
    "deepfake": "D IY1 P F EY2 K",
    "agentic": "EY0 JH EH1 N T IH0 K",
    "paywall": "P EY1 W AO2 L",
    "lidar": "L AY1 D AA2 R",
    "kanban": "K AA1 N B AA2 N",
    # science
    "qubit": "K Y UW1 B IH0 T",
    "exoplanet": "EH1 K S OW0 P L AE2 N AH0 T",
    "exomoon": "EH1 K S OW0 M UW2 N",
    "cubesat": "K Y UW1 B S AE2 T",
    "smallsat": "S M AO1 L S AE2 T",
    "oumuamua": "OW2 M UW0 AH0 M UW1 AH0",
    "regolith": "R EH1 G AH0 L IH0 TH",
    "connectome": "K AH0 N EH1 K T OW2 M",
    "organoid": "AO1 R G AH0 N OY2 D",
    "metagenomics": "M EH2 T AH0 JH AH0 N OW1 M IH0 K S",
    "optogenetics": "AA2 P T OW0 JH AH0 N EH1 T IH0 K S",
    "technosignature": "T EH1 K N OW0 S IH2 G N AH0 CH ER0",
    "biosignature": "B AY1 OW0 S IH2 G N AH0 CH ER0",
}

# Extra hand-written pronunciations found during the g2p review pass: words
# where g2p picked the wrong vowel or invented phonemes, and no clean part
# split exists.
PRON.update({
    "hoodie": "HH UH1 D IY0",
    "emoji": "IH0 M OW1 JH IY0",
    "vlog": "V L AA1 G",
    "vlogger": "V L AA1 G ER0",
    "cosplay": "K AA1 S P L EY2",
    "cosplayer": "K AA1 S P L EY2 ER0",
    "permalink": "P ER1 M AH0 L IH2 NG K",
    "insta": "IH1 N S T AH0",
    "tokenization": "T OW2 K AH0 N AH0 Z EY1 SH AH0 N",
    "ai": "EY1 AY1",
    "gen z": "JH EH1 N Z IY1",
    "gen alpha": "JH EH1 N AE1 L F AH0",
    "allyship": "AE1 L IY0 SH IH2 P",
    "cisgender": "S IH1 S JH EH2 N D ER0",
    "pansexual": "P AE1 N S EH2 K SH UW0 AH0 L",
    "insurrectionist": "IH2 N S ER0 EH1 K SH AH0 N IH0 S T",
    "intersectionality": "IH2 N T ER0 S EH2 K SH AH0 N AE1 L AH0 T IY0",
    "transphobic": "T R AE2 N S F OW1 B IH0 K",
    "wokeness": "W OW1 K N AH0 S",
    "brigading": "B R IH0 G EY1 D IH0 NG",
    "decarbonize": "D IY0 K AA1 R B AH0 N AY2 Z",
    "decarbonization": "D IY0 K AA2 R B AH0 N AH0 Z EY1 SH AH0 N",
    "derecho": "D ER0 EH1 CH OW0",
    "permafrost": "P ER1 M AH0 F R AO2 S T",
    "methylation": "M EH2 TH AH0 L EY1 SH AH0 N",
    "dysregulation": "D IH2 S R EH2 G Y AH0 L EY1 SH AH0 N",
    "microbiome": "M AY2 K R OW0 B AY1 OW0 M",
    "microdosing": "M AY1 K R OW0 D OW2 S IH0 NG",
    "mindfulness": "M AY1 N D F AH0 L N AH0 S",
    "cannabinoid": "K AH0 N AE1 B AH0 N OY2 D",
    "creatine": "K R IY1 AH0 T IY2 N",
    "terpene": "T ER1 P IY2 N",
    "opioid": "OW1 P IY0 OY2 D",
    "comorbidity": "K OW2 M AO0 R B IH1 D AH0 T IY0",
    "pentest": "P EH1 N T EH2 S T",
    "quadcopter": "K W AA1 D K AA2 P T ER0",
    "ransomware": "R AE1 N S AH0 M W EH2 R",
    "robotaxi": "R OW1 B OW0 T AE2 K S IY0",
    "smartglasses": "S M AA1 R T G L AE2 S IH0 Z",
    "petabyte": "P EH1 T AH0 B AY2 T",
    "exabyte": "EH1 K S AH0 B AY2 T",
    "zettabyte": "Z EH1 T AH0 B AY2 T",
    "dslrs": "D IY1 EH1 S EH1 L AA1 R Z",
    "horchata": "AO0 R CH AA1 T AH0",
    "kombucha": "K AA0 M B UW1 CH AH0",
    "sriracha": "S R IY0 R AA1 CH AH0",
    "sous vide": "S UW1 V IY1 D",
    "umami": "UW0 M AA1 M IY0",
    "tahini": "T AH0 HH IY1 N IY0",
    "dermaplaning": "D ER1 M AH0 P L EY2 N IH0 NG",
    "generative ai": "JH EH1 N ER0 AH0 T IH0 V EY1 AY1",
    "deplatforming": "D IY0 P L AE1 T F AO2 R M IH0 NG",
    "rewatchable": "R IY0 W AA1 CH AH0 B AH0 L",
    "microblading": "M AY2 K R OW0 B L EY1 D IH0 NG",
    "influencer": "IH1 N F L UW0 AH0 N S ER0",
    "sourdough starter": "S AW1 R D OW2 S T AA1 R T ER0",
})

# The 1990s pass (added 2026-07-30): initialisms of the dial-up era, the decade's
# music genres, and its office and clinic vocabulary.
PRON.update({
    "cd-rom": "S IY1 D IY1 R AA1 M",
    "mp3": "EH1 M P IY1 TH R IY1",
    "mpeg": "EH1 M P EH2 G",
    "jpeg": "JH EY1 P EH2 G",
    "gsm": "JH IY1 EH1 S EH1 M",
    "pcr": "P IY1 S IY1 AA1 R",
    "pda": "P IY1 D IY1 EY1",
    "wto": "D AH1 B AH0 L Y UW0 T IY1 OW1",
    "b2b": "B IY1 T UW1 B IY1",
    "b2c": "B IY1 T UW1 S IY1",
    "hmo": "EY1 CH EH1 M OW1",
    "ppo": "P IY1 P IY1 OW1",
    "ssri": "EH1 S EH1 S AA1 R AY1",
    "haart": "HH AA1 R T",
    "y2k": "W AY1 T UW1 K EY1",
    "rsi": "AA1 R EH1 S AY1",
    "omega-3": "OW0 M EY1 G AH0 TH R IY1",
    "hiv-positive": "EY1 CH AY1 V IY1 P AA1 Z AH0 T IH0 V",
    "dot-com": "D AA1 T K AA2 M",
    "dotcom": "D AA1 T K AA2 M",
    "e-tailer": "IY1 T EY2 L ER0",
    "etailer": "IY1 T EY2 L ER0",
    "ezine": "IY1 Z IY2 N",
    "weblog": "W EH1 B L AO2 G",
    "webring": "W EH1 B R IH2 NG",
    "webzine": "W EH1 B Z IY2 N",
    "webcam": "W EH1 B K AE2 M",
    "webcast": "W EH1 B K AE2 S T",
    "webpage": "W EH1 B P EY2 JH",
    "webmaster": "W EH1 B M AE2 S T ER0",
    "netiquette": "N EH1 T AH0 K AH0 T",
    "netizen": "N EH1 T AH0 Z AH0 N",
    "warez": "W EH1 R Z",
    "defrag": "D IY0 F R AE1 G",
    "dongle": "D AA1 NG G AH0 L",
    "bitrate": "B IH1 T R EY2 T",
    "palmtop": "P AA1 M T AA2 P",
    "cybercafe": "S AY1 B ER0 K AE2 F EY0",
    "cyberbully": "S AY1 B ER0 B UH2 L IY0",
    "cyberbullying": "S AY1 B ER0 B UH2 L IY0 IH0 NG",
    "clickthrough": "K L IH1 K TH R UW2",
    "tamagotchi": "T AA2 M AH0 G AA1 CH IY0",
    "winamp": "W IH1 N AE2 M P",
    "geocities": "JH IY1 OW0 S IH2 T IY0 Z",
    "spammer": "S P AE1 M ER0",
    "vaporware": "V EY1 P ER0 W EH2 R",
    "stickiness": "S T IH1 K IY0 N AH0 S",
    "disintermediation": "D IH0 S IH2 N T ER0 M IY2 D IY0 EY1 SH AH0 N",
    "intrapreneur": "IH2 N T R AH0 P R AH0 N ER1",
    "downshifting": "D AW1 N SH IH2 F T IH0 NG",
    "reengineering": "R IY2 EH2 N JH AH0 N IH1 R IH0 NG",
    "telecommute": "T EH1 L AH0 K AH0 M Y UW2 T",
    "telecommuting": "T EH1 L AH0 K AH0 M Y UW2 T IH0 NG",
    "infotainment": "IH2 N F OW0 T EY1 N M AH0 N T",
    "edutainment": "EH2 JH UW0 T EY1 N M AH0 N T",
    "securitization": "S IH0 K Y UH2 R AH0 T AH0 Z EY1 SH AH0 N",
    "copay": "K OW1 P EY2",
    "mcjob": "M AH0 K JH AA1 B",
    "docusoap": "D AA1 K Y UW0 S OW2 P",
    "spinmeister": "S P IH1 N M AY2 S T ER0",
    "twentysomething": "T W EH1 N T IY0 S AH2 M TH IH0 NG",
    "latchkey": "L AE1 CH K IY2",
    "heroin chic": "HH EH1 R OW0 AH0 N SH IY1 K",
    "three-peat": "TH R IY1 P IY2 T",
    "wonkish": "W AA1 NG K IH0 SH",
    "himbo": "HH IH1 M B OW0",
    "wigger": "W IH1 G ER0",
    "ladette": "L AH0 D EH1 T",
    "yardie": "Y AA1 R D IY0",
    "alcopop": "AE1 L K OW0 P AA2 P",
    "blingbling": "B L IH1 NG B L IH2 NG",
    # 1990s music
    "britpop": "B R IH1 T P AA2 P",
    "nu metal": "N Y UW1 M EH1 T AH0 L",
    "trip hop": "T R IH1 P HH AA1 P",
    "acid jazz": "AE1 S AH0 D JH AE1 Z",
    "drum and bass": "D R AH1 M AH0 N D B EY1 S",
    "breakbeat": "B R EY1 K B IY2 T",
    "big beat": "B IH1 G B IY1 T",
    "psytrance": "S AY1 T R AE2 N S",
    "darkwave": "D AA1 R K W EY2 V",
    "chillout": "CH IH1 L AW2 T",
    "turntablism": "T ER1 N T AH0 B L IH2 Z AH0 M",
    "screamo": "S K R IY1 M OW0",
    "rapcore": "R AE1 P K AO2 R",
    "hyphy": "HH AY1 F IY0",
    "moshing": "M AA1 SH IH0 NG",
    "grrrl": "G ER1 L",
    "riot grrrl": "R AY1 AH0 T G ER1 L",
    # 1990s medicine / science
    "prion": "P R IY1 AA0 N",
    "fibromyalgia": "F AY2 B R OW0 M AY0 AE1 L JH AH0",
    "rohypnol": "R OW0 HH IH1 P N AO0 L",
    "roofie": "R UW1 F IY0",
    "nutraceutical": "N UW2 T R AH0 S UW1 T IH0 K AH0 L",
    "phytochemical": "F AY2 T OW0 K EH1 M IH0 K AH0 L",
    "olestra": "OW0 L EH1 S T R AH0",
    "transgenic": "T R AE0 N Z JH EH1 N IH0 K",
    "hantavirus": "HH AE1 N T AH0 V AY2 R AH0 S",
    # g2p slips caught in the 1990s review pass
    "low-hanging fruit": "L OW1 HH AE2 NG IH0 NG F R UW1 T",
    "adware": "AE1 D W EH2 R",
    "core competency": "K AO1 R K AH0 M P EH1 T AH0 N S IY0",
})

# Compounds composed from CMUdict parts (see docstring). "a+b" — each part is
# either a CMUdict word or a key in PREFIX_PRON.
PARTS = {
    # AI / tech
    "backpropagation": "back+propagation", "multimodal": "multi+modal",
    "superintelligence": "super+intelligence", "hyperparameter": "hyper+parameter",
    "overfitting": "over+fitting", "pretraining": "pre+training",
    "upscaling": "up+scaling", "midjourney": "mid+journey",
    "touchscreen": "touch+screen", "darknet": "dark+net",
    "dashcam": "dash+cam", "bodycam": "body+cam",
    "cyberattack": "cyber+attack", "cybercrime": "cyber+crime",
    "earbuds": "ear+buds", "sandboxing": "sand+boxing",
    "microservice": "micro+service", "microservices": "micro+services",
    "botnet": "bot+net", "airpods": "air+pods",
    "hoverboard": "hover+board", "powerbank": "power+bank",
    "serverless": "server+less", "passkey": "pass+key",
    "e-waste": "e+waste",
    # business
    "clawback": "claw+back", "coworking": "co+working",
    "dropship": "drop+ship", "dropshipping": "drop+shipping",
    "nearshoring": "near+shoring", "offshoring": "off+shoring",
    "reshoring": "re+shoring", "offboarding": "off+boarding",
    "onboarding": "on+boarding", "reskill": "re+skill",
    "upskill": "up+skill", "upskilling": "up+skilling",
    "subprime": "sub+prime", "telework": "tele+work",
    # climate
    "biofuel": "bio+fuel", "bioplastic": "bio+plastic",
    "geoengineering": "geo+engineering", "greenwash": "green+wash",
    "greenwashing": "green+washing", "microplastic": "micro+plastic",
    "microplastics": "micro+plastics", "biohacking": "bio+hacking",
    "nanoplastics": "nano+plastics", "upcycle": "up+cycle",
    "upcycling": "up+cycling", "heatwave": "heat+wave",
    # health
    "monkeypox": "monkey+pox", "superspreader": "super+spreader",
    "biosimilar": "bio+similar", "neurodivergent": "neuro+divergent",
    "neurodiverse": "neuro+diverse", "neurodiversity": "neuro+diversity",
    "neurotypical": "neuro+typical", "maskless": "mask+less",
    "self-care": "self+care", "microdose": "micro+dose",
    # internet
    "audiobook": "audio+book", "livestream": "live+stream",
    "livestreaming": "live+streaming", "microinfluencer": "micro+influencer",
    "mixtape": "mix+tape", "photobomb": "photo+bomb",
    "crowdsource": "crowd+source", "crowdsourcing": "crowd+sourcing",
    "crowdsourced": "crowd+sourced", "crowdfunding": "crowd+funding",
    "crowdfunded": "crowd+funded", "doomscroll": "doom+scroll",
    "doomscrolling": "doom+scrolling", "geolocation": "geo+location",
    "geotag": "geo+tag", "geotagging": "geo+tagging",
    "fanbase": "fan+base", "fanfiction": "fan+fiction",
    "headcanon": "head+canon", "retweet": "re+tweet",
    "subtweet": "sub+tweet", "rewatch": "re+watch",
    "rewatched": "re+watched", "remaster": "re+master",
    "remastered": "re+mastered", "preorder": "pre+order",
    "unfollow": "un+follow", "unfollowed": "un+followed",
    "unfriend": "un+friend", "unfriended": "un+friended",
    "shadowban": "shadow+ban", "shadowbanned": "shadow+banned",
    "catfishing": "cat+fishing", "ebook": "e+book",
    "binge-watch": "binge+watch",
    # society
    "deadname": "dead+name", "deadnaming": "dead+naming",
    "genderqueer": "gender+queer", "misgender": "mis+gender",
    "misgendering": "mis+gendering", "nonbinary": "non+binary",
    "non-binary": "non+binary", "microaggression": "micro+aggression",
    "astroturfing": "astro+turfing", "breadcrumbing": "bread+crumbing",
    "post-truth": "post+truth", "intersex": "inter+sex",
    # culture / food
    "crossfit": "cross+fit", "multiverse": "multi+verse",
    "skincare": "skin+care", "streetwear": "street+wear",
    "microtransaction": "micro+transaction", "ultramarathon": "ultra+marathon",
    "contouring": "contour+ing", "mouthfeel": "mouth+feel",
    "plant-based": "plant+based", "gluten-free": "gluten+free",
    # 1990s
    "videogame": "video+game", "videogames": "video+games",
    "dial-up": "dial+up", "boy band": "boy+band", "girl power": "girl+power",
    "teen pop": "teen+pop", "battle rap": "battle+rap", "pop punk": "pop+punk",
    "mall rat": "mall+rat", "soccer mom": "soccer+mom",
    "road rage": "road+rage", "air rage": "air+rage",
    # science
    "biomarker": "bio+marker", "decoherence": "de+coherence",
    "metamaterial": "meta+material", "nanotube": "nano+tube",
    "neuroplasticity": "neuro+plasticity", "spaceflight": "space+flight",
    "spacetime": "space+time", "suborbital": "sub+orbital",
    "supersymmetry": "super+symmetry", "terraform": "terra+form",
}

# Bound morphemes with no CMUdict headword of their own. Written with primary
# stress; compose() demotes whichever element is not the head.
PREFIX_PRON = {
    "micro": "M AY1 K R OW0", "bio": "B AY1 OW0", "geo": "JH IY1 OW0",
    "neuro": "N UH1 R OW0", "nano": "N AE1 N OW0", "meta": "M EH1 T AH0",
    "exo": "EH1 K S OW0", "tele": "T EH1 L AH0", "cyber": "S AY1 B ER0",
    "astro": "AE1 S T R OW0", "ultra": "AH1 L T R AH0", "multi": "M AH1 L T IY0",
    "hyper": "HH AY1 P ER0", "terra": "T EH1 R AH0", "co": "K OW1",
    "e": "IY1", "un": "AH1 N", "non": "N AA1 N", "mis": "M IH1 S",
    "pre": "P R IY1", "post": "P OW1 S T", "de": "D IY1", "re": "R IY1",
    "sub": "S AH1 B", "up": "AH1 P", "over": "OW1 V ER0", "self": "S EH1 L F",
    "inter": "IH1 N T ER0", "audio": "AO1 D IY0 OW0", "auto": "AO1 T OW0",
}

# Latinate prefixes put primary stress on the ROOT (micro-PLAS-tic); every
# other first element keeps it (TOUCH-screen).
LATIN_PREFIX = {"micro", "bio", "geo", "neuro", "nano", "meta", "exo", "tele",
                "astro", "ultra", "multi", "hyper", "inter", "de", "re", "pre",
                "mis", "un", "sub", "auto"}

# ---------------------------------------------------------------------- terms
# (term, year of general currency, category)
TERMS = [
    # ------------------------------------------------ internet & platforms
    ("podcasts", 2004, "internet"), ("podcaster", 2005, "internet"),
    ("vlog", 2005, "internet"), ("vlogger", 2007, "internet"),
    ("youtuber", 2008, "internet"), ("tiktok", 2018, "internet"),
    ("tiktoker", 2019, "internet"), ("subreddit", 2008, "internet"),
    ("redditor", 2008, "internet"), ("retweet", 2009, "internet"),
    ("unfriend", 2009, "internet"), ("unfollow", 2010, "internet"),
    ("hashtags", 2007, "internet"), ("emojis", 2010, "internet"),
    ("photobomb", 2008, "internet"), ("paywall", 2003, "internet"),
    ("paywalled", 2010, "internet"), ("clickbaity", 2013, "internet"),
    ("influencer", 2015, "internet"), ("microinfluencer", 2016, "internet"),
    ("livestream", 2010, "internet"), ("livestreaming", 2010, "internet"),
    ("streamer", 2015, "internet"), ("binge-watch", 2013, "internet"),
    ("bingeable", 2015, "internet"), ("rewatch", 2010, "internet"),
    ("rewatchable", 2015, "internet"), ("spoilery", 2015, "internet"),
    ("crowdsourcing", 2006, "internet"), ("crowdsource", 2006, "internet"),
    ("crowdfunding", 2009, "internet"), ("crowdfunded", 2011, "internet"),
    ("asmr", 2013, "internet"), ("mukbang", 2015, "internet"),
    ("unboxing", 2010, "internet"), ("cosplay", 2000, "internet"),
    ("cosplayer", 2003, "internet"), ("fanbase", 2005, "internet"),
    ("fanfic", 2005, "internet"), ("fanfiction", 2005, "internet"),
    ("headcanon", 2010, "internet"), ("parasocial", 2020, "internet"),
    ("relatable", 2010, "internet"), ("positivity", 2010, "internet"),
    ("doomscroll", 2020, "internet"), ("doomscrolling", 2020, "internet"),
    ("catfishing", 2012, "internet"), ("doxx", 2012, "internet"),
    ("doxxing", 2012, "internet"), ("swatting", 2013, "internet"),
    ("brigading", 2015, "internet"), ("shadowban", 2018, "internet"),
    ("shadowbanned", 2018, "internet"), ("deplatform", 2018, "internet"),
    ("deplatforming", 2018, "internet"), ("subtweet", 2012, "internet"),
    ("virality", 2010, "internet"), ("geotag", 2006, "internet"),
    ("geotagging", 2006, "internet"), ("geolocation", 2005, "internet"),
    ("permalink", 2000, "internet"), ("ebook", 2007, "internet"),
    ("audiobook", 2005, "internet"), ("mixtape", 2000, "internet"),
    ("hoodie", 2000, "internet"), ("gifs", 2010, "internet"),
    ("insta", 2013, "internet"), ("selfie stick", 2014, "internet"),
    ("ecommerce", 2000, "internet"), ("e-commerce", 2000, "internet"),
    ("imdb", 2000, "internet"), ("wordle", 2022, "internet"),
    ("airbnb", 2008, "internet"), ("lyft", 2012, "internet"),
    ("venmo", 2012, "internet"), ("shopify", 2006, "internet"),
    ("patreon", 2013, "internet"), ("doordash", 2013, "internet"),
    ("instacart", 2012, "internet"), ("substack", 2017, "internet"),
    ("onlyfans", 2019, "internet"), ("bluesky", 2023, "internet"),
    ("soundcloud", 2010, "internet"), ("bandcamp", 2008, "internet"),
    ("gofundme", 2012, "internet"), ("groupon", 2010, "internet"),
    ("indiegogo", 2011, "internet"), ("kickstarter", 2009, "internet"),
    ("grindr", 2009, "internet"), ("okcupid", 2004, "internet"),
    ("tripadvisor", 2005, "internet"), ("vimeo", 2005, "internet"),
    ("wechat", 2011, "internet"), ("weibo", 2010, "internet"),
    ("alibaba", 2005, "internet"), ("tencent", 2004, "internet"),
    ("bytedance", 2017, "internet"), ("temu", 2023, "internet"),
    ("shein", 2020, "internet"), ("oculus", 2014, "internet"),
    ("remaster", 2010, "internet"), ("remastered", 2010, "internet"),
    ("preorder", 2005, "internet"), ("customization", 2005, "internet"),

    # -------------------------------------------------- computing & devices
    ("smartwatch", 2013, "tech"), ("smartglasses", 2013, "tech"),
    ("touchscreen", 2005, "tech"), ("earbuds", 2005, "tech"),
    ("airpods", 2016, "tech"), ("powerbank", 2012, "tech"),
    ("e-bike", 2015, "tech"), ("e-scooter", 2018, "tech"),
    ("e-waste", 2005, "tech"), ("dashcam", 2012, "tech"),
    ("bodycam", 2014, "tech"), ("quadcopter", 2012, "tech"),
    ("hoverboard", 2015, "tech"), ("robotaxi", 2019, "tech"),
    ("lidar", 2010, "tech"), ("phablet", 2012, "tech"),
    ("tethering", 2008, "tech"), ("qr code", 2010, "tech"),
    ("nfc", 2010, "tech"), ("usb-c", 2015, "tech"),
    ("passkey", 2022, "tech"), ("biometrics", 2003, "tech"),
    ("metadata", 2000, "tech"), ("vpn", 2005, "tech"),
    ("dslr", 2005, "tech"), ("oled", 2010, "tech"),
    ("mbps", 2005, "tech"), ("rfid", 2005, "tech"),
    ("petabyte", 2005, "tech"), ("exabyte", 2010, "tech"),
    ("zettabyte", 2015, "tech"), ("ransomware", 2013, "tech"),
    ("cyberattack", 2005, "tech"), ("cybercrime", 2003, "tech"),
    ("botnet", 2005, "tech"), ("darknet", 2010, "tech"),
    ("dark web", 2013, "tech"), ("smishing", 2018, "tech"),
    ("vishing", 2010, "tech"), ("spear phishing", 2010, "tech"),
    ("ddos", 2005, "tech"), ("zero-day", 2005, "tech"),
    ("pentest", 2010, "tech"), ("sandboxing", 2010, "tech"),
    ("saas", 2005, "tech"), ("paas", 2008, "tech"), ("iaas", 2008, "tech"),
    ("serverless", 2015, "tech"), ("microservice", 2014, "tech"),
    ("microservices", 2014, "tech"), ("kubernetes", 2015, "tech"),
    ("devops", 2009, "tech"), ("kanban", 2007, "tech"),
    ("typescript", 2014, "tech"), ("nodejs", 2010, "tech"),
    ("json", 2001, "tech"), ("jquery", 2006, "tech"),
    ("powershell", 2006, "tech"), ("macos", 2016, "tech"),
    ("ios", 2010, "tech"), ("gamify", 2011, "tech"),
    ("gamified", 2011, "tech"), ("gamification", 2011, "tech"),
    ("adtech", 2015, "tech"), ("martech", 2015, "tech"),
    ("dark pattern", 2010, "tech"), ("enshittification", 2023, "tech"),

    # ---------------------------------------------------------------- AI
    ("chatbot", 2016, "ai"), ("chatgpt", 2022, "ai"),
    ("deepfake", 2018, "ai"), ("generative ai", 2022, "ai"),
    ("agentic", 2024, "ai"), ("multimodal", 2023, "ai"),
    ("machine learning", 2010, "ai"), ("deep learning", 2015, "ai"),
    ("neural network", 2015, "ai"), ("large language model", 2022, "ai"),
    ("prompt engineering", 2022, "ai"), ("embeddings", 2015, "ai"),
    ("tokenizer", 2018, "ai"), ("tokenization", 2018, "ai"),
    ("fine-tune", 2020, "ai"), ("pretraining", 2019, "ai"),
    ("guardrails", 2023, "ai"), ("superintelligence", 2014, "ai"),
    ("overfitting", 2010, "ai"), ("hyperparameter", 2015, "ai"),
    ("backpropagation", 2010, "ai"), ("quantization", 2020, "ai"),
    ("upscaling", 2018, "ai"), ("agi", 2015, "ai"), ("llm", 2022, "ai"),
    ("gpt", 2020, "ai"), ("tpu", 2016, "ai"), ("midjourney", 2022, "ai"),

    # ------------------------------------------------------------- crypto
    ("blockchain", 2015, "crypto"), ("bitcoin", 2011, "crypto"),
    ("ethereum", 2016, "crypto"), ("altcoin", 2014, "crypto"),
    ("stablecoin", 2018, "crypto"), ("dogecoin", 2014, "crypto"),
    ("litecoin", 2013, "crypto"), ("satoshi", 2011, "crypto"),
    ("nft", 2021, "crypto"), ("nfts", 2021, "crypto"),
    ("metaverse", 2021, "crypto"), ("defi", 2020, "crypto"),
    ("web3", 2021, "crypto"), ("dao", 2021, "crypto"),
    ("tokenomics", 2018, "crypto"), ("coinbase", 2015, "crypto"),

    # ------------------------------------------------------- covid & health
    ("covid", 2020, "covid"), ("covid-19", 2020, "covid"),
    ("long covid", 2020, "covid"), ("social distancing", 2020, "covid"),
    ("contact tracing", 2020, "covid"), ("herd immunity", 2020, "covid"),
    ("spike protein", 2020, "covid"), ("superspreader", 2020, "covid"),
    ("immunocompromised", 2020, "covid"), ("comorbidity", 2020, "covid"),
    ("seroprevalence", 2020, "covid"), ("maskless", 2020, "covid"),
    ("quarantining", 2020, "covid"), ("lockdowns", 2020, "covid"),
    ("antivaxxer", 2015, "covid"), ("vax", 2021, "covid"),
    ("vaxxed", 2021, "covid"), ("unvaxxed", 2021, "covid"),
    ("omicron", 2021, "covid"), ("mpox", 2022, "covid"),
    ("monkeypox", 2022, "covid"), ("ppe", 2020, "covid"),
    ("mrna", 2020, "health"), ("telehealth", 2020, "health"),
    ("telemedicine", 2015, "health"), ("cbd", 2018, "health"),
    ("thc", 2005, "health"), ("cannabinoid", 2010, "health"),
    ("terpene", 2015, "health"), ("dispensary", 2010, "health"),
    ("vaper", 2013, "health"), ("juul", 2018, "health"),
    ("juuling", 2018, "health"), ("microdose", 2015, "health"),
    ("microdosing", 2015, "health"), ("nootropic", 2015, "health"),
    ("biohacking", 2015, "health"), ("wearable", 2013, "health"),
    ("wearables", 2013, "health"), ("fitbit", 2010, "health"),
    ("mindfulness", 2005, "health"), ("self-care", 2015, "health"),
    ("microbiome", 2010, "health"), ("probiotic", 2005, "health"),
    ("celiac", 2005, "health"), ("gluten-free", 2008, "health"),
    ("neurodivergent", 2018, "health"), ("neurodiverse", 2018, "health"),
    ("neurodiversity", 2015, "health"), ("neurotypical", 2010, "health"),
    ("dysregulation", 2015, "health"), ("biosimilar", 2010, "health"),
    ("semaglutide", 2021, "health"), ("tirzepatide", 2022, "health"),
    ("ozempic", 2021, "health"), ("glp-1", 2023, "health"),
    ("opioid", 2015, "health"), ("copd", 2005, "health"),
    ("mrsa", 2005, "health"), ("creatine", 2005, "health"),
    ("immunotherapy", 2013, "health"),

    # ------------------------------------------------------------- climate
    ("microplastic", 2015, "climate"), ("microplastics", 2015, "climate"),
    ("nanoplastics", 2020, "climate"), ("greenwash", 2010, "climate"),
    ("greenwashing", 2010, "climate"), ("decarbonize", 2015, "climate"),
    ("decarbonization", 2015, "climate"), ("net zero", 2019, "climate"),
    ("carbon neutral", 2010, "climate"), ("carbon footprint", 2005, "climate"),
    ("upcycle", 2010, "climate"), ("upcycling", 2010, "climate"),
    ("rewilding", 2015, "climate"), ("solarpunk", 2019, "climate"),
    ("degrowth", 2015, "climate"), ("eco-anxiety", 2019, "climate"),
    ("climate anxiety", 2019, "climate"), ("heat dome", 2021, "climate"),
    ("atmospheric river", 2019, "climate"), ("bomb cyclone", 2018, "climate"),
    ("derecho", 2012, "climate"), ("microgrid", 2010, "climate"),
    ("agrivoltaics", 2020, "climate"), ("geoengineering", 2010, "climate"),
    ("bioplastic", 2010, "climate"), ("biochar", 2010, "climate"),
    ("permafrost", 2005, "climate"), ("anthropocene", 2010, "climate"),
    ("regenerative", 2015, "climate"), ("gigafactory", 2014, "climate"),
    ("electrification", 2018, "climate"), ("renewables", 2005, "climate"),
    ("biofuel", 2005, "climate"), ("heatwave", 2010, "climate"),

    # ------------------------------------------------------------ business
    ("fintech", 2015, "business"), ("insurtech", 2016, "business"),
    ("proptech", 2017, "business"), ("edtech", 2015, "business"),
    ("agtech", 2015, "business"), ("healthtech", 2015, "business"),
    ("neobank", 2017, "business"), ("decacorn", 2015, "business"),
    ("spac", 2020, "business"), ("shrinkflation", 2022, "business"),
    ("greedflation", 2022, "business"), ("subprime", 2007, "business"),
    ("clawback", 2008, "business"), ("gig economy", 2015, "business"),
    ("gig worker", 2015, "business"), ("side hustle", 2015, "business"),
    ("coworking", 2010, "business"), ("telework", 2005, "business"),
    ("hybrid work", 2021, "business"), ("hot desking", 2010, "business"),
    ("upskill", 2015, "business"), ("upskilling", 2015, "business"),
    ("reskill", 2015, "business"), ("offshoring", 2003, "business"),
    ("nearshoring", 2010, "business"), ("reshoring", 2012, "business"),
    ("friendshoring", 2022, "business"), ("disruptor", 2010, "business"),
    ("freemium", 2006, "business"), ("onboarding", 2005, "business"),
    ("offboarding", 2010, "business"), ("dropship", 2015, "business"),
    ("dropshipping", 2015, "business"), ("bnpl", 2020, "business"),
    ("ebitda", 2005, "business"), ("cagr", 2005, "business"),
    ("etf", 2005, "business"), ("etfs", 2005, "business"),
    ("esg", 2018, "business"), ("monetization", 2005, "business"),
    ("workation", 2020, "business"), ("staycation", 2008, "business"),
    ("great resignation", 2021, "business"), ("return to office", 2021, "business"),
    ("ghost kitchen", 2019, "business"), ("last mile", 2010, "business"),

    # ------------------------------------------------------------- society
    ("nonbinary", 2015, "society"), ("non-binary", 2015, "society"),
    ("genderqueer", 2010, "society"), ("cisgender", 2013, "society"),
    ("transphobia", 2010, "society"), ("transphobic", 2010, "society"),
    ("deadname", 2015, "society"), ("deadnaming", 2015, "society"),
    ("misgender", 2013, "society"), ("misgendering", 2013, "society"),
    ("pansexual", 2010, "society"), ("demisexual", 2015, "society"),
    ("aromantic", 2015, "society"), ("intersex", 2005, "society"),
    ("latinx", 2016, "society"), ("bipoc", 2020, "society"),
    ("aapi", 2020, "society"), ("microaggression", 2013, "society"),
    ("intersectionality", 2015, "society"), ("allyship", 2018, "society"),
    ("wokeness", 2019, "society"), ("mansplain", 2010, "society"),
    ("mansplaining", 2010, "society"), ("manosphere", 2015, "society"),
    ("incel", 2018, "society"), ("alt-right", 2016, "society"),
    ("antifa", 2017, "society"), ("prepper", 2010, "society"),
    ("tradwife", 2020, "society"), ("sharenting", 2015, "society"),
    ("millennials", 2000, "society"), ("zoomer", 2019, "society"),
    ("gen z", 2019, "society"), ("gen alpha", 2023, "society"),
    ("nimby", 2005, "society"), ("yimby", 2016, "society"),
    ("gentrifier", 2010, "society"), ("post-truth", 2016, "society"),
    ("whataboutism", 2016, "society"), ("astroturfing", 2010, "society"),
    ("dog whistle", 2010, "society"), ("infodemic", 2020, "society"),
    ("fact-check", 2010, "society"), ("brexit", 2016, "society"),
    ("brexiteer", 2016, "society"), ("maga", 2016, "society"),
    ("qanon", 2019, "society"), ("insurrectionist", 2021, "society"),
    ("daca", 2012, "society"), ("islamophobia", 2005, "society"),
    ("cancel culture", 2019, "society"), ("virtue signaling", 2015, "society"),
    ("toxic masculinity", 2015, "society"), ("body positivity", 2015, "society"),
    ("imposter syndrome", 2015, "society"), ("emotional labor", 2015, "society"),
    ("trigger warning", 2013, "society"), ("safe space", 2013, "society"),
    ("ghosting", 2015, "society"), ("breadcrumbing", 2017, "society"),
    ("polyamory", 2010, "society"), ("polyamorous", 2010, "society"),
    ("throuple", 2015, "society"), ("frenemy", 2000, "society"),
    ("bromance", 2005, "society"), ("man cave", 2005, "society"),
    ("man bun", 2014, "society"), ("dad bod", 2015, "society"),
    ("hangry", 2015, "society"), ("humblebrag", 2010, "society"),
    ("adulting", 2015, "society"), ("nomophobia", 2010, "society"),
    ("fomo", 2011, "society"), ("jomo", 2015, "society"),

    # ---------------------------------------------------------------- food
    ("sriracha", 2010, "food"), ("gochujang", 2015, "food"),
    ("matcha", 2015, "food"), ("boba", 2015, "food"),
    ("horchata", 2010, "food"), ("kombucha", 2015, "food"),
    ("hard seltzer", 2019, "food"), ("mocktail", 2015, "food"),
    ("oat milk", 2018, "food"), ("almond milk", 2012, "food"),
    ("aquafaba", 2015, "food"), ("jackfruit", 2016, "food"),
    ("seitan", 2010, "food"), ("tempeh", 2010, "food"),
    ("halloumi", 2015, "food"), ("burrata", 2010, "food"),
    ("cronut", 2013, "food"), ("birria", 2020, "food"),
    ("elote", 2015, "food"), ("shakshuka", 2015, "food"),
    ("harissa", 2012, "food"), ("za'atar", 2015, "food"),
    ("tahini", 2010, "food"), ("labneh", 2015, "food"),
    ("farro", 2012, "food"), ("freekeh", 2015, "food"),
    ("ketogenic", 2018, "food"), ("flexitarian", 2010, "food"),
    ("plant-based", 2018, "food"), ("veganism", 2015, "food"),
    ("locavore", 2007, "food"), ("gastropub", 2005, "food"),
    ("food truck", 2010, "food"), ("sous vide", 2010, "food"),
    ("air fryer", 2018, "food"), ("spiralizer", 2015, "food"),
    ("cold brew", 2015, "food"), ("cortado", 2012, "food"),
    ("flat white", 2010, "food"), ("pour over", 2012, "food"),
    ("craft beer", 2010, "food"), ("umami", 2005, "food"),
    ("mouthfeel", 2010, "food"), ("sourdough starter", 2020, "food"),
    ("acai", 2010, "food"), ("ube", 2018, "food"),
    ("yuzu", 2015, "food"),

    # -------------------------------------------------------------- culture
    ("skincare", 2015, "culture"), ("niacinamide", 2018, "culture"),
    ("microblading", 2016, "culture"), ("dermaplaning", 2018, "culture"),
    ("balayage", 2015, "culture"), ("contouring", 2013, "culture"),
    ("athleisure", 2014, "culture"), ("normcore", 2014, "culture"),
    ("cottagecore", 2020, "culture"), ("dark academia", 2020, "culture"),
    ("streetwear", 2010, "culture"), ("sneakerhead", 2005, "culture"),
    ("fast fashion", 2010, "culture"), ("thrifting", 2015, "culture"),
    ("vanlife", 2018, "culture"), ("glamping", 2007, "culture"),
    ("esports", 2015, "culture"), ("speedrun", 2015, "culture"),
    ("speedrunner", 2015, "culture"), ("roguelike", 2010, "culture"),
    ("permadeath", 2010, "culture"), ("loadout", 2010, "culture"),
    ("metagame", 2010, "culture"), ("lootbox", 2017, "culture"),
    ("battle royale", 2018, "culture"), ("microtransaction", 2010, "culture"),
    ("modding", 2005, "culture"), ("pickleball", 2020, "culture"),
    ("padel", 2022, "culture"), ("crossfit", 2010, "culture"),
    ("hiit", 2013, "culture"), ("peloton", 2018, "culture"),
    ("ultramarathon", 2010, "culture"), ("multiverse", 2019, "culture"),
    ("k-pop", 2012, "culture"), ("isekai", 2018, "culture"),
    ("gacha", 2018, "culture"), ("afrobeats", 2015, "culture"),
    ("hyperpop", 2019, "culture"), ("vaporwave", 2013, "culture"),
    ("synthwave", 2013, "culture"), ("lo-fi", 2018, "culture"),

    # -------------------------------------------------------------- science
    ("exoplanet", 2005, "science"), ("exomoon", 2015, "science"),
    ("dwarf planet", 2006, "science"), ("spacex", 2010, "science"),
    ("starlink", 2019, "science"), ("cubesat", 2010, "science"),
    ("smallsat", 2015, "science"), ("suborbital", 2004, "science"),
    ("oumuamua", 2017, "science"), ("regolith", 2010, "science"),
    ("terraform", 2015, "science"), ("astrobiology", 2005, "science"),
    ("biosignature", 2015, "science"), ("technosignature", 2018, "science"),
    ("qubit", 2005, "science"), ("boson", 2012, "science"),
    ("supersymmetry", 2010, "science"), ("decoherence", 2015, "science"),
    ("graphene", 2010, "science"), ("nanotube", 2005, "science"),
    ("perovskite", 2015, "science"), ("metamaterial", 2010, "science"),
    ("crispr", 2015, "science"), ("epigenetics", 2005, "science"),
    ("proteomics", 2005, "science"), ("metagenomics", 2010, "science"),
    ("connectome", 2010, "science"), ("organoid", 2015, "science"),
    ("optogenetics", 2010, "science"), ("neuroplasticity", 2005, "science"),
    ("methylation", 2005, "science"), ("biomarker", 2005, "science"),
    ("spacetime", 2005, "science"), ("spaceflight", 2005, "science"),

    # ================================================================ 1990s
    # Added 2026-07-30 at the operator's request: a rich palette for writers,
    # communicators and songwriters needs the decade CMUdict was frozen in the
    # middle of. It has "internet" and "email" but not "webcam" or "dial-up",
    # and almost none of the decade's music vocabulary.

    # ---- the dial-up internet ----
    ("webpage", 1995, "internet"), ("webmaster", 1993, "internet"),
    ("hyperlink", 1990, "internet"), ("dial-up", 1994, "internet"),
    ("netiquette", 1993, "internet"), ("netizen", 1994, "internet"),
    ("emoticon", 1990, "internet"), ("spammer", 1995, "internet"),
    ("webcam", 1994, "internet"), ("webcast", 1995, "internet"),
    ("webzine", 1994, "internet"), ("ezine", 1994, "internet"),
    ("weblog", 1997, "internet"), ("webring", 1995, "internet"),
    ("clickthrough", 1996, "internet"), ("banner ad", 1994, "internet"),
    ("chat room", 1994, "internet"), ("chatroom", 1994, "internet"),
    ("instant messaging", 1996, "internet"), ("cybercafe", 1994, "internet"),
    ("cyberbully", 1998, "internet"), ("cyberbullying", 1998, "internet"),
    ("geocities", 1995, "internet"), ("winamp", 1997, "internet"),
    ("dot-com", 1994, "internet"), ("dotcom", 1994, "internet"),
    ("e-tailer", 1997, "internet"), ("videogame", 1990, "internet"),
    ("videogames", 1990, "internet"),

    # ---- the machines ----
    ("cd-rom", 1990, "tech"), ("mp3", 1995, "tech"), ("mpeg", 1992, "tech"),
    ("jpeg", 1992, "tech"), ("pda", 1992, "tech"), ("palmtop", 1990, "tech"),
    ("gsm", 1991, "tech"), ("ringtone", 1996, "tech"),
    ("malware", 1990, "tech"), ("spyware", 1995, "tech"),
    ("adware", 1995, "tech"), ("freeware", 1990, "tech"),
    ("shareware", 1990, "tech"), ("warez", 1990, "tech"),
    ("vaporware", 1990, "tech"), ("defrag", 1990, "tech"),
    ("dongle", 1990, "tech"), ("bitrate", 1995, "tech"),
    ("y2k", 1997, "tech"), ("killer app", 1990, "tech"),
    ("open source", 1998, "tech"), ("bleeding edge", 1990, "tech"),

    # ---- the decade's music ----
    ("britpop", 1994, "music"), ("trip hop", 1994, "music"),
    ("acid jazz", 1990, "music"), ("drum and bass", 1993, "music"),
    ("breakbeat", 1990, "music"), ("big beat", 1996, "music"),
    ("psytrance", 1996, "music"), ("darkwave", 1990, "music"),
    ("chillout", 1994, "music"), ("nu metal", 1996, "music"),
    ("rapcore", 1993, "music"), ("screamo", 1994, "music"),
    ("pop punk", 1994, "music"), ("teen pop", 1997, "music"),
    ("boy band", 1990, "music"), ("girl power", 1996, "music"),
    ("riot grrrl", 1991, "music"), ("grrrl", 1991, "music"),
    ("turntablism", 1995, "music"), ("battle rap", 1990, "music"),
    ("moshing", 1990, "music"), ("hyphy", 1998, "music"),
    ("blingbling", 1999, "music"),

    # ---- the decade's people ----
    ("slacker", 1990, "culture"), ("twentysomething", 1990, "culture"),
    ("generation x", 1991, "culture"), ("latchkey", 1990, "culture"),
    ("soccer mom", 1992, "culture"), ("mall rat", 1990, "culture"),
    ("himbo", 1990, "culture"), ("wigger", 1990, "culture"),
    ("ladette", 1995, "culture"), ("yardie", 1990, "culture"),
    ("wonkish", 1993, "culture"), ("three-peat", 1993, "culture"),
    ("heroin chic", 1996, "culture"), ("alcopop", 1995, "culture"),
    ("extreme sports", 1993, "culture"), ("tamagotchi", 1997, "culture"),
    ("road rage", 1994, "society"), ("air rage", 1997, "society"),
    ("docusoap", 1997, "culture"), ("reality tv", 1992, "culture"),
    ("infotainment", 1990, "culture"), ("edutainment", 1990, "culture"),
    ("shock jock", 1990, "culture"), ("spin doctor", 1990, "society"),
    ("spinmeister", 1990, "society"), ("sound bite", 1990, "society"),
    ("photo op", 1990, "society"), ("wedge issue", 1990, "society"),
    ("soft money", 1990, "society"), ("glass ceiling", 1990, "society"),

    # ---- the decade's office ----
    ("mcjob", 1991, "business"), ("downshifting", 1994, "business"),
    ("reengineering", 1993, "business"), ("telecommute", 1990, "business"),
    ("telecommuting", 1990, "business"), ("casual friday", 1992, "business"),
    ("mommy track", 1990, "business"), ("road warrior", 1990, "business"),
    ("knowledge worker", 1990, "business"), ("six sigma", 1990, "business"),
    ("core competency", 1990, "business"), ("paradigm shift", 1990, "business"),
    ("low-hanging fruit", 1990, "business"), ("mission critical", 1990, "business"),
    ("value-added", 1990, "business"), ("win-win", 1990, "business"),
    ("intrapreneur", 1990, "business"), ("disintermediation", 1995, "business"),
    ("stickiness", 1997, "business"), ("b2b", 1998, "business"),
    ("b2c", 1998, "business"), ("emerging markets", 1990, "business"),
    ("venture capital", 1990, "business"), ("angel investor", 1994, "business"),
    ("burn rate", 1995, "business"), ("securitization", 1990, "business"),
    ("wto", 1995, "business"), ("early adopter", 1990, "business"),
    ("rebranding", 1990, "business"), ("viral marketing", 1996, "business"),
    ("guerrilla marketing", 1990, "business"),

    # ---- the decade's clinic and lab ----
    ("prion", 1990, "health"), ("mad cow", 1990, "health"),
    ("hantavirus", 1993, "health"), ("haart", 1996, "health"),
    ("protease inhibitor", 1995, "health"), ("hiv-positive", 1990, "health"),
    ("ssri", 1990, "health"), ("fibromyalgia", 1990, "health"),
    ("carpal tunnel", 1990, "health"), ("rsi", 1990, "health"),
    ("rohypnol", 1995, "health"), ("roofie", 1995, "health"),
    ("crystal meth", 1990, "health"), ("needle exchange", 1990, "health"),
    ("harm reduction", 1990, "health"), ("managed care", 1990, "health"),
    ("hmo", 1990, "health"), ("ppo", 1990, "health"), ("copay", 1990, "health"),
    ("nutraceutical", 1990, "health"), ("phytochemical", 1995, "health"),
    ("olestra", 1996, "health"), ("omega-3", 1990, "health"),
    ("trans fat", 1994, "health"),
    ("transgenic", 1990, "science"), ("gene therapy", 1990, "science"),
    ("stem cell", 1990, "science"), ("human genome", 1990, "science"),
    ("pcr", 1990, "science"),
]

ok_re = re.compile(r"^[a-z0-9][a-z0-9 '.\-]*$")


def inflections(t):
    """Plausible inflected spellings of a one-word term, each tagged with the
    ending that produced it so its pronunciation can be derived from the base
    rather than re-guessed by g2p. Returns [(form, kind), ...]."""
    if " " in t or "-" in t or len(t) < 4:
        return []
    out = []
    if t.endswith(("s", "x", "z", "ch", "sh")):
        out.append((t + "es", "es"))
    elif t.endswith("y") and t[-2] not in "aeiou":
        out.append((t[:-1] + "ies", "ies"))
    else:
        out.append((t + "s", "s"))
    if t.endswith("e"):
        out += [(t + "d", "ed"), (t[:-1] + "ing", "ing"), (t + "r", "er")]
    elif t.endswith(("ing", "ed", "er", "ly", "ic", "ous", "al")):
        pass  # already inflected / not a verb stem
    else:
        out += [(t + "ed", "ed"), (t + "ing", "ing"), (t + "er", "er")]
    return out


# ------------------------------------------------------- what the site already has
CMU = {}   # word -> first CMUdict pronunciation


def existing_keys():
    keys = set()
    alt = re.compile(r"\(\d+\)$")
    with open(CMUDICT, "r", encoding="utf-8") as f:
        for line in f:
            tok, _, rest = line.partition(" ")
            if not tok:
                continue
            base = alt.sub("", tok)
            keys.add(base)
            if base == tok:   # skip the (2)/(3) alternates
                CMU[base] = rest.split("#", 1)[0].strip()
    for path in (UD, NEW):
        with open(path, "r", encoding="utf-8") as f:
            txt = f.read()
        # anchor on "= `" — never the first backtick in the file
        body = txt[txt.index("= `") + 3:txt.rindex("`")]
        for line in body.split("\n"):
            k = line.split("\t", 1)[0]
            if k:
                keys.add(k)
    return keys


# --------------------------------------------------------------- pronunciation
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


VOICELESS = {"P", "T", "K", "F", "TH", "S", "SH", "CH", "HH"}
SIBILANT = {"S", "Z", "SH", "ZH", "CH", "JH"}


def demote(ph):
    """Primary stress -> secondary; the non-head element of a compound."""
    return " ".join(t[:-1] + "2" if t.endswith("1") else t for t in ph.split())


def g2p_word(tok):
    if no_vowel.match(tok):
        return " ".join(LETTER[ch] for ch in tok)
    ph = [p for p in g2p(tok) if p.strip() and p != " "]
    return " ".join(p for p in ph if re.match(r"^[A-Z]+[0-2]?$", p))


def part_pron(p):
    if p in PREFIX_PRON:
        return PREFIX_PRON[p]
    if p in PRON:
        return PRON[p]
    if p in CMU:
        return CMU[p]
    if p in PARTS:
        return compose(PARTS[p])
    return g2p_word(p)


def compose(spec):
    """'touch+screen' -> the two CMUdict pronunciations, stress-adjusted."""
    parts = spec.split("+")
    head = len(parts) - 1 if parts[0] in LATIN_PREFIX else 0
    out = []
    for i, p in enumerate(parts):
        ph = part_pron(p)
        out.append(ph if i == head else demote(ph))
    return " ".join(out)


def add_suffix(ph, kind):
    """Regular ending, with English voicing agreement."""
    tail = re.sub(r"\d", "", ph.split()[-1])
    if kind in ("s", "es", "ies"):
        if kind == "ies" and ph.endswith(("IY0", "IY1", "IY2")):
            return ph + " Z"
        if tail in SIBILANT:
            return ph + " IH0 Z"
        return ph + (" S" if tail in VOICELESS else " Z")
    if kind == "ed":
        if tail in ("T", "D"):
            return ph + " IH0 D"
        return ph + (" T" if tail in VOICELESS else " D")
    if kind == "ing":
        return ph + " IH0 NG"
    if kind == "er":
        return ph + " ER0"
    raise ValueError(kind)


def arpabet(term):
    """Pronunciation for a headword: hand-written, then composed, then per-word
    (CMUdict where possible) for phrases, then g2p."""
    if term in PRON:
        return PRON[term]
    if term in PARTS:
        return compose(PARTS[term])
    words = [w for w in term.split(" ") if w]
    if len(words) > 1:   # a phrase: every word keeps its own stress
        return " ".join(part_pron(w) for w in words)
    tok = words[0]
    if "-" in tok:       # hyphenated and not in PARTS: treat as a compound
        return compose(tok.replace("-", "+"))
    return CMU.get(tok) or g2p_word(tok)


# ------------------------------------------------------------------------ build
def main():
    have = existing_keys()
    rows = []            # (term, pron, zipf, year, category)
    emitted = set()
    skipped_existing = []

    def emit(term, year, cat, pron=None):
        if term in emitted:
            return False
        if term in have:
            skipped_existing.append(term)
            return False
        if not ok_re.match(term):
            print(f"  SKIP (unsupported characters): {term!r}")
            return False
        ph = pron or arpabet(term)
        if not ph:
            print(f"  SKIP (no pronunciation): {term!r}")
            return False
        z = zipf_frequency(term, "en")
        if " " in term or "-" in term:
            z = min(z, PHRASE_CAP)   # see PHRASE_CAP
        z = max(z, FLOOR_ZIPF)
        rows.append((term, ph, z, year, cat))
        emitted.add(term)
        return True

    for term, year, cat in TERMS:
        assert cat in CATEGORIES, f"unknown category {cat!r} on {term!r}"
        emit(term, year, cat)
    base_n = len(rows)
    print(f"curated terms added      : {base_n}")
    print(f"curated already covered  : {len(skipped_existing)}")

    # inflections of everything we just added, gated on real-world use. The
    # pronunciation comes from the base + the regular ending, never from g2p.
    infl = 0
    for term, base_pron, _, year, cat in list(rows):
        for form, kind in inflections(term):
            if form in have or form in emitted:
                continue
            if zipf_frequency(form, "en") < INFL_MIN_ZIPF:
                continue
            ph = PRON.get(form) or (compose(PARTS[form]) if form in PARTS
                                    else add_suffix(base_pron, kind))
            if emit(form, year, cat, ph):
                infl += 1
    print(f"inflections added        : {infl}")

    rows.sort(key=lambda r: (r[4], r[0]))
    lines = ["%s\t%s\t%.2f\t%d\t%s" % r for r in rows]
    blob = "\n".join(lines)
    assert "`" not in blob and "${" not in blob, "unexpected template-literal char"

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("// Modern lexicon: words that entered general English roughly 2000-2026 and\n")
        f.write("// are absent from CMUdict, ud-data.js and new-data.js. Non-slang counterpart\n")
        f.write("// to new-data.js: technology, AI, crypto, COVID, climate, identity, food,\n")
        f.write("// science. Curated + backstopped by a wordfreq gap sweep; see\n")
        f.write("// build/build_modern.py for the selection rules.\n")
        f.write("// Pronunciations: g2p_en, hand-written for initialisms, brands and loanwords.\n")
        f.write("// Format per line: term\\tARPABET\\tzipf\\tyear\\tcategory\n")
        f.write("window.MOD_DATA = `")
        f.write(blob)
        f.write("`;\n")

    cats, years = {}, {}
    for t, p, z, y, c in rows:
        cats[c] = cats.get(c, 0) + 1
        d = str(y // 10 * 10) + "s"
        years[d] = years.get(d, 0) + 1
    print(f"written terms            : {len(rows)}")
    print(f"by category              : {dict(sorted(cats.items(), key=lambda kv: -kv[1]))}")
    print(f"by decade                : {dict(sorted(years.items()))}")
    print(f"output file              : {os.path.normpath(OUT)}")
    print(f"output size              : {os.path.getsize(OUT) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
