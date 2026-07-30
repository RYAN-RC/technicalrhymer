#!/usr/bin/env python3
"""Build co-data.js: the names of the S&P 500 and of the world's 500 largest
public companies, with ARPABET pronunciations.

Company names are the proper nouns modern writing is full of and a 1998
pronouncing dictionary cannot have. CMUdict does carry the household names of
its era (apple, boeing, pfizer), so this file only adds what is missing.

INPUTS (both gitignored; refresh with these commands from build/)
  curl -sL -o sp500.csv \
    https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv
  curl -sL -A Mozilla/5.0 -o global500.csv 'https://companiesmarketcap.com/?download=csv'

  sp500.csv     - S&P 500 constituents (Wikipedia-derived): Symbol, Security, ...
  global500.csv - every listed company ranked by market capitalisation; the
                  top TOP_WORLD rows are taken as "the world's 500 biggest".
                  Market cap, not revenue: it is the ranking that comes with a
                  machine-readable source, and it is dated (see HEADER below).

NAME NORMALISATION
  Legal and structural suffixes are dropped (Inc, Corp, plc, Ltd, AG, SA,
  Holdings, Group, Class A) because nobody says them: "AbbVie", not "AbbVie
  Inc". Accents are folded (Nestle). A parenthetical alias yields a second
  entry, so "Alphabet (Google)" is searchable both ways.

PRONUNCIATIONS
  - ACRONYM_PRON / PRON: hand-written. Initialisms said as letters (TSMC,
    ICBC, LVMH) are letter-spelled; initialisms said as words (Nasdaq, Aecom,
    IQVIA, Aon) and every name g2p mangles are written out.
  - An all-caps token in the source name that is not in ACRONYM_WORD is
    letter-spelled automatically — that rule is why the caps are read from the
    ORIGINAL name and not from the lowercased lookup key.
  - Otherwise CMUdict per word where it has the word, else g2p_en.
  These are approximations for foreign names especially, and the site labels
  them as such.

Output line format (../co-data.js, window.CO_DATA):
  name \t phonemes \t zipf \t source \t rank
- name     : lowercased lookup key (display key too, as everywhere else)
- phonemes : ARPABET
- zipf     : wordfreq commonality, floored at FLOOR_ZIPF
- source   : sp500 | world500 | sp500+world500
- rank     : best rank across the lists it appears in (1 = biggest)

Helpers mirror build_ud.py / build_new.py / build_modern.py — the build
scripts in this directory are standalone by convention.
"""
import csv
import html
import os
import re
import unicodedata
from wordfreq import zipf_frequency
from g2p_en import G2p

HERE = os.path.dirname(os.path.abspath(__file__))
SP = os.path.join(HERE, "sp500.csv")
WORLD = os.path.join(HERE, "global500.csv")
CMUDICT = os.path.join(HERE, "cmudict.dict")
UD = os.path.join(HERE, "..", "ud-data.js")
NEW = os.path.join(HERE, "..", "new-data.js")
MOD = os.path.join(HERE, "..", "mod-data.js")
OUT = os.path.join(HERE, "..", "co-data.js")

TOP_WORLD = 500
FLOOR_ZIPF = 1.40   # a company nobody writes about still beats nothing at all

# Initialisms read as a word, not as letters.
ACRONYM_WORD = {
    "NASDAQ": "N AE1 Z D AE0 K",
    "AECOM": "EY1 K AA0 M",
    "IQVIA": "AY0 K W IY1 V IY0 AH0",
    "EPAM": "IY1 P AE0 M",
    "AON": "EY1 AA0 N",
    "CACI": "K EY1 S IY0",
    "AMETEK": "AE1 M AH0 T EH2 K",
    "VICI": "V IY1 CH IY0",
    "ONEOK": "W AH1 N OW2 K",
    "DOW": "D AW1",
    "IDEX": "AY1 D EH2 K S",
    "KIOXIA": "K IY0 AA1 K S IY0 AH0",
    "TAQA": "T AA1 K AH0",
    "CNOOC": "S IY1 N UW2 K",
    "ENGIE": "AA0 N ZH IY1",
    "CITIC": "S AY1 T IH0 K",
    "ARGENX": "AA0 R JH EH1 N IH0 K S",
    "NAURA": "N AW1 R AH0",
    "GEHC": None,      # None = fall through to letter-spelling
}

# Whole-name pronunciations: g2p mangles them, or the name is foreign, or the
# spelling gives no clue how it is said.
PRON = {
    "3m": "TH R IY1 EH1 M",
    "abbvie": "AE1 B V IY0",
    "aflac": "EY1 F L AE2 K",
    "agilent": "AE1 JH AH0 L AH0 N T",
    "airbnb": "EH1 R B IY1 EH1 N B IY1",
    "akamai": "AA1 K AH0 M AY2",
    "albemarle": "AE1 L B AH0 M AA2 R L",
    "alnylam": "AE0 L N IH1 L AH0 M",
    "altria": "AE0 L T R IY1 AH0",
    "ameren": "AE1 M ER0 AH0 N",
    "ameriprise": "AH0 M EH1 R AH0 P R AY2 Z",
    "amphenol": "AE1 M F AH0 N AA2 L",
    "analog devices": "AE1 N AH0 L AO2 G D IH0 V AY1 S IH0 Z",
    "ansys": "AE1 N S IH0 S",
    "aptiv": "AE1 P T IH0 V",
    "arcelormittal": "AA2 R S EH1 L AO0 R M IH0 T AA1 L",
    "arista networks": "AH0 R IH1 S T AH0 N EH1 T W ER2 K S",
    "asml": "EY1 EH1 S EH1 M EH1 L",
    "assurant": "AH0 SH UH1 R AH0 N T",
    "astrazeneca": "AE2 S T R AH0 Z EH1 N AH0 K AH0",
    "atmos energy": "AE1 T M AH0 S EH1 N ER0 JH IY0",
    "autozone": "AO1 T OW0 Z OW2 N",
    "avalonbay communities": "AE1 V AH0 L AA2 N B EY2 K AH0 M Y UW1 N AH0 T IY0 Z",
    "axon enterprise": "AE1 K S AA2 N EH1 N T ER0 P R AY2 Z",
    "baidu": "B AY1 D UW0",
    "bajaj finance": "B AA1 JH AA0 JH F AY1 N AE0 N S",
    "bhp": "B IY1 EY1 CH P IY1",
    "biogen": "B AY1 OW0 JH EH2 N",
    "bio-techne": "B AY1 OW0 T EH1 K N IY0",
    "blackrock": "B L AE1 K R AA2 K",
    "broadcom": "B R AO1 D K AA2 M",
    "broadridge financial solutions": "B R AO1 D R IH2 JH F AY2 N AE1 N SH AH0 L S AH0 L UW1 SH AH0 N Z",
    "bytedance": "B AY1 T D AE2 N S",
    "cadence design systems": "K EY1 D AH0 N S D IH0 Z AY1 N S IH1 S T AH0 M Z",
    "carvana": "K AA0 R V AA1 N AH0",
    "catl": "S IY1 EY1 T IY1 EH1 L",
    "cboe global markets": "S IY1 B OW0 IY1 G L OW1 B AH0 L M AA1 R K AH0 T S",
    "cbre": "S IY1 B IY1 AA1 R IY1",
    "cencora": "S EH0 N K AO1 R AH0",
    "centene": "S EH0 N T IY1 N",
    "centerpoint energy": "S EH1 N T ER0 P OY2 N T EH1 N ER0 JH IY0",
    "chipotle mexican grill": "CH IH0 P OW1 T L EY0 M EH1 K S AH0 K AH0 N G R IH1 L",
    "ciena": "S IY0 EH1 N AH0",
    "cintas": "S IH1 N T AH0 S",
    "citigroup": "S IH1 T IY0 G R UW2 P",
    "cme group": "S IY1 EH1 M IY1",
    "cognizant": "K AA1 G N AH0 Z AH0 N T",
    "coinbase": "K OY1 N B EY2 S",
    "conocophillips": "K AA2 N AH0 K OW0 F IH1 L AH0 P S",
    "copart": "K OW1 P AA2 R T",
    "corpay": "K AO1 R P EY2",
    "corteva": "K AO0 R T EH1 V AH0",
    "coupang": "K UW1 P AE2 NG",
    "crowdstrike": "K R AW1 D S T R AY2 K",
    "danaher": "D AE1 N AH0 HH AA2 R",
    "datadog": "D EY1 T AH0 D AO2 G",
    "dexcom": "D EH1 K S K AA2 M",
    "diageo": "D IY0 AA1 JH IY0 OW0",
    "doordash": "D AO1 R D AE2 SH",
    "dsv": "D IY1 EH1 S V IY1",
    "dte energy": "D IY1 T IY1 IY1 EH1 N ER0 JH IY0",
    "enphase energy": "EH1 N F EY2 Z EH1 N ER0 JH IY0",
    "entegris": "EH0 N T EH1 G R IH0 S",
    "eog resources": "IY1 OW1 JH IY1 R IY1 S AO0 R S IH0 Z",
    "epam systems": "IY1 P AE0 M S IH1 S T AH0 M Z",
    "equinix": "EH1 K W AH0 N IH2 K S",
    "erie indemnity": "IH1 R IY0 IH0 N D EH1 M N AH0 T IY0",
    "fastenal": "F AE1 S T AH0 N AH0 L",
    "fico": "F AY1 K OW0",
    "fiserv": "F AY1 S ER0 V",
    "fortinet": "F AO1 R T AH0 N EH2 T",
    "gartner": "G AA1 R T N ER0",
    "gehc": "JH IY1 IY1 EY1 CH S IY1",
    "gen digital": "JH EH1 N D IH1 JH AH0 T AH0 L",
    "genuine parts": "JH EH1 N Y UW0 W AH0 N P AA1 R T S",
    "gevernova": "JH IY1 IY1 V ER0 N OW1 V AH0",
    "ge vernova": "JH IY1 IY1 V ER0 N OW1 V AH0",
    "haleon": "HH EY1 L IY0 AA0 N",
    "hdfc bank": "EY1 CH D IY1 EH1 F S IY1 B AE1 NG K",
    "hermes": "ER0 M EH1 Z",
    "hologic": "HH OW0 L OW1 JH IH0 K",
    "hubspot": "HH AH1 B S P AA2 T",
    "hynix": "HH AY1 N IH0 K S",
    "iberdrola": "IY2 B ER0 D R OW1 L AH0",
    "icbc": "AY1 S IY1 B IY1 S IY1",
    "idexx laboratories": "AY1 D EH0 K S L AE1 B R AH0 T AO2 R IY0 Z",
    "incyte": "IH1 N S AY2 T",
    "inditex": "IH1 N D IH0 T EH2 K S",
    "infosys": "IH1 N F OW0 S IH2 S",
    "ingersoll rand": "IH1 NG G ER0 S AO2 L R AE1 N D",
    "intuit": "IH1 N T UW0 IH0 T",
    "intuitive surgical": "IH0 N T UW1 IH0 T IH0 V S ER1 JH IH0 K AH0 L",
    "invitation homes": "IH2 N V AH0 T EY1 SH AH0 N HH OW1 M Z",
    "iqvia": "AY0 K W IY1 V IY0 AH0",
    "jd.com": "JH EY1 D IY1 D AA1 T K AA2 M",
    "jpmorgan chase": "JH EY1 P IY1 M AO1 R G AH0 N CH EY1 S",
    "keurig dr pepper": "K Y UH1 R IH0 G D AA1 K T ER0 P EH1 P ER0",
    "keysight technologies": "K IY1 S AY2 T T EH0 K N AA1 L AH0 JH IY0 Z",
    "kla": "K EY1 EH1 L EY1",
    "kweichow moutai": "K W EY1 CH AW0 M OW0 T AY1",
    "l3harris": "EH1 L TH R IY1 HH EH1 R IH0 S",
    "lam research": "L AE1 M R IY1 S ER0 CH",
    "lennar": "L EH1 N AA0 R",
    "linde": "L IH1 N D IY0",
    "lseg": "EH1 L EH1 S IY1 JH IY1",
    "lululemon athletica": "L UW2 L UW0 L EH1 M AH0 N AE0 TH L EH1 T IH0 K AH0",
    "lvmh": "EH1 L V IY1 EH1 M EY1 CH",
    "mediatek": "M IY1 D IY0 AH0 T EH2 K",
    "mercadolibre": "M ER0 K AA2 D OW0 L IY1 B R EY0",
    "meta platforms": "M EH1 T AH0 P L AE1 T F AO2 R M Z",
    "microstrategy": "M AY1 K R OW0 S T R AE2 T AH0 JH IY0",
    "moderna": "M AH0 D ER1 N AH0",
    "mondelez": "M AA1 N D AH0 L EH2 Z",
    "monolithic power systems": "M AA2 N AH0 L IH1 TH IH0 K P AW1 ER0 S IH1 S T AH0 M Z",
    "mplx": "EH1 M P IY1 EH1 L EH1 K S",
    "msci": "EH1 M EH1 S S IY1 AY1",
    "nasdaq": "N AE1 Z D AE0 K",
    "netease": "N EH1 T IY1 Z",
    "nextera energy": "N EH2 K S T EH1 R AH0 EH1 N ER0 JH IY0",
    "nordson": "N AO1 R D S AH0 N",
    "novartis": "N OW0 V AA1 R T AH0 S",
    "novo nordisk": "N OW1 V OW0 N AO1 R D IH0 S K",
    "nucor": "N UW1 K AO2 R",
    "nvidia": "EH0 N V IH1 D IY0 AH0",
    "nvr": "EH1 N V IY1 AA1 R",
    "nxp semiconductors": "EH1 N EH1 K S P IY1 S EH1 M IY0 K AH0 N D AH2 K T ER0 Z",
    "okta": "AA1 K T AH0",
    "otis worldwide": "OW1 T IH0 S W ER1 L D W AY2 D",
    "palantir": "P AE1 L AH0 N T IH2 R",
    "paycom": "P EY1 K AA2 M",
    "pdd": "P IY1 D IY1 D IY1",
    "pepsico": "P EH1 P S IY0 K OW2",
    "petrochina": "P EH2 T R OW0 CH AY1 N AH0",
    "pinduoduo": "P IH2 N D W OW0 D W OW1",
    "prologis": "P R OW1 L OW0 JH IH0 S",
    "prosus": "P R OW1 S AH0 S",
    "ptc": "P IY1 T IY1 S IY1",
    "quanta services": "K W AA1 N T AH0 S ER1 V AH0 S IH0 Z",
    "reddit": "R EH1 D IH0 T",
    "regeneron pharmaceuticals": "R IH0 JH EH1 N ER0 AA2 N F AA2 R M AH0 S UW1 T IH0 K AH0 L Z",
    "reliance industries": "R IH0 L AY1 AH0 N S IH1 N D AH0 S T R IY0 Z",
    "revvity": "R EH1 V AH0 T IY0",
    "rivian": "R IH1 V IY0 AH0 N",
    "roblox": "R OW1 B L AA2 K S",
    "roper technologies": "R OW1 P ER0 T EH0 K N AA1 L AH0 JH IY0 Z",
    "sap": "EH1 S EY1 P IY1",
    "saudi aramco": "S AW1 D IY0 AH0 R AE1 M K OW0",
    "sea limited": "S IY1",
    "sempra": "S EH1 M P R AH0",
    "sherwin-williams": "SH ER1 W IH0 N W IH1 L Y AH0 M Z",
    "shopify": "SH AA1 P AH0 F AY2",
    "smic": "EH1 S EH1 M AY1 S IY1",
    "snowflake": "S N OW1 F L EY2 K",
    "solventum": "S AA0 L V EH1 N T AH0 M",
    "spacex": "S P EY1 S EH1 K S",
    "steris": "S T EH1 R IH0 S",
    "stryker": "S T R AY1 K ER0",
    "synopsys": "S IH0 N AA1 P S IH0 S",
    "tapestry": "T AE1 P AH0 S T R IY0",
    "targa resources": "T AA1 R G AH0 R IY1 S AO0 R S IH0 Z",
    "tcs": "T IY1 S IY1 EH1 S",
    "teledyne": "T EH1 L AH0 D AY2 N",
    "teleflex": "T EH1 L AH0 F L EH2 K S",
    "tencent": "T EH1 N S EH2 N T",
    "teradyne": "T EH1 R AH0 D AY2 N",
    "tesla": "T EH1 S L AH0",
    "totalenergies": "T OW1 T AH0 L EH1 N ER0 JH IY0 Z",
    "tractor supply": "T R AE1 K T ER0 S AH0 P L AY1",
    "trane technologies": "T R EY1 N T EH0 K N AA1 L AH0 JH IY0 Z",
    "tsmc": "T IY1 EH1 S EH1 M S IY1",
    "tyler technologies": "T AY1 L ER0 T EH0 K N AA1 L AH0 JH IY0 Z",
    "uber": "UW1 B ER0",
    "ulta beauty": "AH1 L T AH0 B Y UW1 T IY0",
    "unitedhealth": "Y UW0 N AY1 T AH0 D HH EH2 L TH",
    "vertiv": "V ER1 T IH0 V",
    "vici properties": "V IY1 CH IY0 P R AA1 P ER0 T IY0 Z",
    "vistra": "V IH1 S T R AH0",
    "welltower": "W EH1 L T AW2 ER0",
    "workday": "W ER1 K D EY2",
    "wuxi apptec": "W UW1 SH IY0 AE1 P T EH2 K",
    "xylem": "Z AY1 L AH0 M",
    "zoetis": "Z OW0 EH1 T IH0 S",
    "zscaler": "Z IY1 S K EY2 L ER0",
}

# Second pass, from reviewing the generated pronunciations name by name: the
# ones g2p invented phonemes for, plus foreign names whose spelling gives an
# English reader no clue.
PRON.update({
    "at and t": "EY1 T IY1 AH0 N D T IY1",
    "air liquide": "EH1 R L IY0 K IY1 D",
    "ares management": "EH1 R IY0 Z M AE1 N AH0 JH M AH0 N T",
    "anheuser-busch inbev": "AE1 N HH AY0 Z ER0 B UH1 SH IH1 N B EH2 V",
    "argenx": "AA0 R JH EH1 N IH0 K S",
    "booking.com": "B UH1 K IH0 NG D AA1 T K AA2 M",
    "bunge global": "B AH1 N JH IY0 G L OW1 B AH0 L",
    "caixabank": "K AY1 SH AH0 B AE2 NG K",
    "cloudflare": "K L AW1 D F L EH2 R",
    "colgate-palmolive": "K OW1 L G EY2 T P AH0 M OW1 L IH0 V",
    "danone": "D AH0 N OW1 N",
    "diamondback energy": "D AY1 M AH0 N D B AE2 K EH1 N ER0 JH IY0",
    "edwards lifesciences": "EH1 D W ER0 D Z L AY1 F S AY2 AH0 N S IH0 Z",
    "elevance health": "EH1 L AH0 V AE2 N S HH EH1 L TH",
    "eoptolink technology": "IY1 AA0 P T OW0 L IH2 NG K T EH0 K N AA1 L AH0 JH IY0",
    "essilorluxottica": "EH1 S AH0 L AO0 R L UW2 K S AA1 T IH0 K AH0",
    "expeditors international": "EH2 K S P AH0 D IY1 T ER0 Z IH2 N T ER0 N AE1 SH AH0 N AH0 L",
    "exxonmobil": "EH1 K S AA0 N M OW1 B AH0 L",
    "factset": "F AE1 K T S EH2 T",
    "firstenergy": "F ER1 S T EH2 N ER0 JH IY0",
    "freeport-mcmoran": "F R IY1 P AO2 R T M AH0 K M AO0 R AE1 N",
    "insulet": "IH1 N S UW0 L EH2 T",
    "jabil": "JH EY1 B AH0 L",
    "keyence": "K IY1 EH0 N S",
    "keysight": "K IY1 S AY2 T",
    "kimberly-clark": "K IH1 M B ER0 L IY0 K L AA1 R K",
    "labcorp": "L AE1 B K AO2 R P",
    "leidos": "L AY1 D OW0 S",
    "loblaw companies": "L OW1 B L AO2 K AH1 M P AH0 N IY2 Z",
    "lyondellbasell": "L AY2 AH0 N D EH1 L B AH0 S EH1 L",
    "macquarie": "M AH0 K W AO1 R IY0",
    "meituan": "M EY1 T W AA1 N",
    "mercedes-benz": "M ER0 S EY1 D IY0 Z B EH1 N Z",
    "midea": "M IH0 D IY1 AH0",
    "mizuho financial": "M IY2 Z UW1 HH OW0 F AH0 N AE1 N SH AH0 L",
    "munchener ruck": "M UW1 N CH AH0 N ER0 R UH1 K",
    "munich re": "M Y UW1 N IH0 K R IY1",
    "murata seisakusho": "M UH0 R AA1 T AH0 S EY2 S AH0 K UW1 SH OW0",
    "nongfu spring": "N AO1 NG F UW0 S P R IH1 NG",
    "parker-hannifin": "P AA1 R K ER0 HH AE1 N IH0 F IH0 N",
    "phillips 66": "F IH1 L IH0 P S S IH1 K S T IY0 S IH1 K S",
    "pultegroup": "P UH1 L T IY0 G R UW2 P",
    "qnity electronics": "K W IH1 N AH0 T IY0 IH2 L EH0 K T R AA1 N IH0 K S",
    "sberbank": "S B EH1 R B AE2 NG K",
    "scotiabank": "S K OW1 SH AH0 B AE2 NG K",
    "supermicro": "S UW2 P ER0 M AY1 K R OW0",
    "take-two interactive": "T EY1 K T UW1 IH2 N T ER0 AE1 K T IH0 V",
    "thales": "T AA0 L EH1 S",
    "transdigm": "T R AE1 N Z D AY2 M",
    "unicredit": "Y UW1 N IH0 K R EH2 D IH0 T",
    "veeva systems": "V IY1 V AH0 S IH1 S T AH0 M Z",
    "verisign": "V EH1 R IH0 S AY2 N",
    "viatris": "V IY0 AE1 T R IH0 S",
    "warner bros. discovery": "W AO1 R N ER0 B R AH1 DH ER0 Z D IH0 S K AH1 V ER0 IY0",
    "williams-sonoma": "W IH1 L Y AH0 M Z S AH0 N OW1 M AH0",
    "wiwynn": "W AY1 W IH0 N",
    "xcel energy": "EH1 K S EH0 L EH1 N ER0 JH IY0",
    "xiaomi": "SH AW1 M IY0",
    "zhongji innolight": "ZH AO1 NG JH IY0 IH1 N OW0 L AY2 T",
    "zijin mining": "Z IY1 JH IH0 N M AY1 N IH0 NG",
    "cambricon technologies": "K AE1 M B R IH0 K AA2 N T EH0 K N AA1 L AH0 JH IY0 Z",
    "itau unibanco": "IY2 T AW1 Y UW2 N IH0 B AA1 NG K OW0",
    "guotai junan securities": "G W OW2 T AY1 JH UW0 N AA1 N S IH0 K Y UH1 R AH0 T IY0 Z",
    "naura technology": "N AW1 R AH0 T EH0 K N AA1 L AH0 JH IY0",
})

SUFFIX = re.compile(
    r"\b("
    r"inc|incorporated|corp|corporation|company|co|"
    r"plc|ltd|limited|llc|lp|nv|sa|ag|se|spa|ab|asa|oyj|kgaa|"
    r"pjsc|jsc|psc|qsc|bsc|tbk|sac|"
    r"holdings|holding|group|the"
    r")\b\.?", re.I)
# A removed suffix can leave a conjunction or preposition dangling:
# "Deere & Company" -> "deere and", "KKR & Co." -> "kkr and".
DANGLING = re.compile(r"^(and|of)\b|\b(and|of)$", re.I)
PARENS = re.compile(r"\(([^)]*)\)")
SHARE_CLASS = re.compile(r"\b(class [abc]|series [abc])\b", re.I)
ok_re = re.compile(r"^[a-z0-9][a-z0-9 '.\-]*$")
caps_token = re.compile(r"^[A-Z0-9&.]{2,6}$")


def fold(s):
    """Nestle, not Nestlé."""
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


def clean(s):
    s = fold(html.unescape(s)).replace("&", " and ").replace("’", "'")
    s = SHARE_CLASS.sub(" ", s)
    s = SUFFIX.sub(" ", s)
    s = re.sub(r"[^A-Za-z0-9'. -]", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" .-")
    for _ in range(2):   # "KKR & Co." leaves "kkr and"
        s = DANGLING.sub(" ", s).strip(" .-")
        s = re.sub(r"\s+", " ", s)
    if not (2 <= len(s) <= 40) or len(s.split(" ")) > 4:
        return None
    return s


def variants(raw):
    """'Alphabet (Google)' -> ['Alphabet', 'Google'] (original casing kept, so
    the acronym rule can still see it)."""
    out = []
    for part in [PARENS.sub(" ", raw)] + PARENS.findall(raw):
        c = clean(part)
        if c:
            out.append(c)
    return out


# ------------------------------------------------- what the site already has
CMU = {}


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
            if base == tok:
                CMU[base] = rest.split("#", 1)[0].strip()
    for path in (UD, NEW, MOD):
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            txt = f.read()
        body = txt[txt.index("= `") + 3:txt.rindex("`")]   # never the 1st backtick
        for line in body.split("\n"):
            k = line.split("\t", 1)[0]
            if k:
                keys.add(k)
    return keys


# ------------------------------------------------------------ pronunciation
g2p = G2p()

LETTER = {
    "a": "EY1", "b": "B IY1", "c": "S IY1", "d": "D IY1", "e": "IY1",
    "f": "EH1 F", "g": "JH IY1", "h": "EY1 CH", "i": "AY1", "j": "JH EY1",
    "k": "K EY1", "l": "EH1 L", "m": "EH1 M", "n": "EH1 N", "o": "OW1",
    "p": "P IY1", "q": "K Y UW1", "r": "AA1 R", "s": "EH1 S", "t": "T IY1",
    "u": "Y UW1", "v": "V IY1", "w": "D AH1 B AH0 L Y UW0", "x": "EH1 K S",
    "y": "W AY1", "z": "Z IY1",
}
DIGIT = {
    "0": "Z IH1 R OW0", "1": "W AH1 N", "2": "T UW1", "3": "TH R IY1",
    "4": "F AO1 R", "5": "F AY1 V", "6": "S IH1 K S", "7": "S EH1 V AH0 N",
    "8": "EY1 T", "9": "N AY1 N",
}


def spell(tok):
    out = []
    for ch in tok.lower():
        if ch in LETTER:
            out.append(LETTER[ch])
        elif ch in DIGIT:
            out.append(DIGIT[ch])
    return " ".join(out)


def g2p_word(tok):
    ph = [p for p in g2p(tok) if p.strip() and p != " "]
    return " ".join(p for p in ph if re.match(r"^[A-Z]+[0-2]?$", p))


def pron_for(key, original):
    """key = lowercased lookup key; original = source-cased name (so the
    all-caps acronym rule can fire)."""
    if key in PRON:
        return PRON[key]
    src_tokens = original.split(" ")
    out = []
    for i, tok in enumerate(key.split(" ")):
        src = src_tokens[i] if i < len(src_tokens) else tok
        if src.upper() in ACRONYM_WORD and ACRONYM_WORD[src.upper()]:
            out.append(ACRONYM_WORD[src.upper()])
            continue
        # an all-caps source token with no vowel, or a known letter initialism
        if caps_token.match(src) and src == src.upper() and not tok.isdigit():
            out.append(spell(re.sub(r"[^A-Za-z0-9]", "", tok)))
            continue
        out.append(word_pron(tok.strip(".'")))
    return " ".join(p for p in out if p)


def word_pron(bare):
    """CMUdict, then a hand entry, then the halves of a hyphenated name
    (g2p reads 'colgate-palmolive' as one impossible word), then g2p."""
    if bare in CMU:
        return CMU[bare]
    if bare in PRON:
        return PRON[bare]
    if "-" in bare:
        return " ".join(word_pron(p) for p in bare.split("-") if p)
    return g2p_word(bare)


# -------------------------------------------------------------------- build
def load_rows():
    """key -> {'orig': source-cased name, 'src': set, 'rank': best}"""
    rows = {}

    def put(key, orig, src, rank):
        e = rows.setdefault(key, {"orig": orig, "src": set(), "rank": rank})
        e["src"].add(src)
        e["rank"] = min(e["rank"], rank)

    with open(SP, encoding="utf-8") as f:
        for i, r in enumerate(csv.DictReader(f)):
            for v in variants(r["Security"]):
                put(v.lower(), v, "sp500", i + 1)
    with open(WORLD, encoding="utf-8") as f:
        for i, r in enumerate(csv.DictReader(f)):
            if i >= TOP_WORLD:
                break
            for v in variants(r["Name"]):
                put(v.lower(), v, "world500", i + 1)
    return rows


def main():
    have = existing_keys()
    rows = load_rows()
    print(f"company keys from both lists : {len(rows)}")

    out_rows, covered = [], 0
    for key in sorted(rows):
        info = rows[key]
        if key in have:
            covered += 1
            continue
        if not ok_re.match(key):
            print(f"  SKIP (unsupported characters): {key!r}")
            continue
        ph = pron_for(key, info["orig"])
        if not ph:
            print(f"  SKIP (no pronunciation): {key!r}")
            continue
        z = max(zipf_frequency(key, "en"), FLOOR_ZIPF)
        src = "+".join(sorted(info["src"]))
        out_rows.append((key, ph, z, src, info["rank"]))

    print(f"already searchable           : {covered}")
    print(f"new company names            : {len(out_rows)}")

    lines = ["%s\t%s\t%.2f\t%s\t%d" % r for r in out_rows]
    blob = "\n".join(lines)
    assert "`" not in blob and "${" not in blob, "unexpected template-literal char"

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("// Company names: the S&P 500 plus the world's 500 largest public companies\n")
        f.write("// by market capitalisation, minus every name CMUdict already has.\n")
        f.write("// Sources: datasets/s-and-p-500-companies (Wikipedia) and\n")
        f.write("// companiesmarketcap.com. Legal suffixes (Inc, plc, AG) are dropped.\n")
        f.write("// Pronunciations: hand-written for initialisms and awkward names, CMUdict\n")
        f.write("// per word where possible, else g2p_en - approximate for foreign names.\n")
        f.write("// Format per line: name\\tARPABET\\tzipf\\tsource\\trank\n")
        f.write("window.CO_DATA = `")
        f.write(blob)
        f.write("`;\n")

    srcs = {}
    for r in out_rows:
        srcs[r[3]] = srcs.get(r[3], 0) + 1
    print(f"by source                    : {srcs}")
    print(f"output file                  : {os.path.normpath(OUT)}")
    print(f"output size                  : {os.path.getsize(OUT) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
