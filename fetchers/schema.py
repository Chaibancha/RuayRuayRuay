"""Shared data models, 20-sport catalog, normalization utilities, and realistic fallback generators."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


SPORTS_CATALOG: List[Dict[str, Any]] = [
    {
        "id": 0,
        "oddspapi_id": 0,
        "slug": "all",
        "icon": "🌐",
        "name_th": "กีฬาทั้งหมด",
        "name_en": "All Sports",
        "label": "🌐 กีฬาทั้งหมด (All Sports - รวมทุกประเภทกีฬา)",
        "espn_feeds": [
            ("England. Premier League", "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard", 1),
            ("USA. NBA", "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard", 3),
            ("USA. NHL", "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard", 2),
            ("USA. MLB", "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard", 5),
            ("USA. NFL", "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard", 13),
            ("UFC Fight Night / PPV", "https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard", 56),
        ],
        "has_draw": True,
    },
    {
        "id": 1,
        "oddspapi_id": 10,
        "slug": "football",
        "icon": "⚽",
        "name_th": "ฟุตบอล",
        "name_en": "Football / Soccer",
        "label": "⚽ ฟุตบอล (Football / Soccer)",
        "espn_feeds": [
            ("England. Premier League", "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard"),
            ("UEFA Champions League", "https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.champions/scoreboard"),
            ("Spain. LaLiga", "https://site.api.espn.com/apis/site/v2/sports/soccer/esp.1/scoreboard"),
        ],
        "has_draw": True,
    },
    {
        "id": 3,
        "oddspapi_id": 11,
        "slug": "basketball",
        "icon": "🏀",
        "name_th": "บาสเกตบอล",
        "name_en": "Basketball",
        "label": "🏀 บาสเกตบอล (Basketball - NBA / EuroLeague)",
        "espn_feeds": [
            ("USA. NBA", "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"),
            ("USA. WNBA", "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard"),
        ],
        "has_draw": False,
    },
    {
        "id": 4,
        "oddspapi_id": 13,
        "slug": "tennis",
        "icon": "🎾",
        "name_th": "เทนนิส",
        "name_en": "Tennis",
        "label": "🎾 เทนนิส (Tennis - ATP / WTA)",
        "espn_feeds": [
            ("ATP Tour", "https://site.api.espn.com/apis/site/v2/sports/tennis/atp/scoreboard"),
            ("WTA Tour", "https://site.api.espn.com/apis/site/v2/sports/tennis/wta/scoreboard"),
        ],
        "has_draw": False,
    },
    {
        "id": 6,
        "oddspapi_id": 15,
        "slug": "volleyball",
        "icon": "🏐",
        "name_th": "วอลเลย์บอล",
        "name_en": "Volleyball",
        "label": "🏐 วอลเลย์บอล (Volleyball - VNL / Pro League)",
        "espn_feeds": [],
        "has_draw": False,
    },
    {
        "id": 2,
        "oddspapi_id": 12,
        "slug": "ice_hockey",
        "icon": "🏒",
        "name_th": "ฮอกกี้น้ำแข็ง",
        "name_en": "Ice Hockey",
        "label": "🏒 ฮอกกี้น้ำแข็ง (Ice Hockey - NHL / KHL)",
        "espn_feeds": [
            ("USA. NHL", "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard"),
        ],
        "has_draw": True,
    },
    {
        "id": 16,
        "oddspapi_id": 21,
        "slug": "badminton",
        "icon": "🏸",
        "name_th": "แบดมินตัน",
        "name_en": "Badminton",
        "label": "🏸 แบดมินตัน (Badminton - BWF World Tour)",
        "espn_feeds": [],
        "has_draw": False,
    },
    {
        "id": 10,
        "oddspapi_id": 20,
        "slug": "table_tennis",
        "icon": "🏓",
        "name_th": "เทเบิลเทนนิส (ปิงปอง)",
        "name_en": "Table Tennis",
        "label": "🏓 เทเบิลเทนนิส / ปิงปอง (Table Tennis)",
        "espn_feeds": [],
        "has_draw": False,
    },
    {
        "id": 9,
        "oddspapi_id": 22,
        "slug": "boxing",
        "icon": "🥊",
        "name_th": "มวยสากล / มวยไทย",
        "name_en": "Boxing / Muay Thai",
        "label": "🥊 มวยสากล / มวยไทย (Boxing / ONE Muay Thai)",
        "espn_feeds": [],
        "has_draw": True,
    },
    {
        "id": 56,
        "oddspapi_id": 23,
        "slug": "mma",
        "icon": "🥋",
        "name_th": "ศิลปะการต่อสู้ผสมผสาน (MMA)",
        "name_en": "MMA / UFC",
        "label": "🥋 ศิลปะการต่อสู้ผสมผสาน (MMA / UFC / ONE)",
        "espn_feeds": [
            ("UFC Fight Night / PPV", "https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard"),
        ],
        "has_draw": False,
    },
    {
        "id": 40,
        "oddspapi_id": 17,
        "slug": "esports",
        "icon": "🎮",
        "name_th": "อีสปอร์ต",
        "name_en": "Esports",
        "label": "🎮 อีสปอร์ต (Esports - Dota 2 / CS2 / LoL / Valorant)",
        "espn_feeds": [],
        "has_draw": False,
    },
    {
        "id": 5,
        "oddspapi_id": 14,
        "slug": "baseball",
        "icon": "⚾",
        "name_th": "เบสบอล",
        "name_en": "Baseball",
        "label": "⚾ เบสบอล (Baseball - MLB / NPB)",
        "espn_feeds": [
            ("USA. MLB", "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard"),
        ],
        "has_draw": False,
    },
    {
        "id": 13,
        "oddspapi_id": 16,
        "slug": "american_football",
        "icon": "🏈",
        "name_th": "อเมริกันฟุตบอล",
        "name_en": "American Football",
        "label": "🏈 อเมริกันฟุตบอล (NFL / NCAA)",
        "espn_feeds": [
            ("USA. NFL", "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"),
        ],
        "has_draw": False,
    },
    {
        "id": 19,
        "oddspapi_id": 24,
        "slug": "snooker",
        "icon": "🎱",
        "name_th": "สนุกเกอร์",
        "name_en": "Snooker",
        "label": "🎱 สนุกเกอร์ (Snooker - World Tour)",
        "espn_feeds": [],
        "has_draw": False,
    },
    {
        "id": 29,
        "oddspapi_id": 25,
        "slug": "futsal",
        "icon": "⚽",
        "name_th": "ฟุตซอล",
        "name_en": "Futsal",
        "label": "⚽ ฟุตซอล (Futsal - Thai League / UEFA)",
        "espn_feeds": [],
        "has_draw": True,
    },
    {
        "id": 8,
        "oddspapi_id": 18,
        "slug": "handball",
        "icon": "🤾",
        "name_th": "แฮนด์บอล",
        "name_en": "Handball",
        "label": "🤾 แฮนด์บอล (Handball - EHF Champions)",
        "espn_feeds": [],
        "has_draw": True,
    },
    {
        "id": 7,
        "oddspapi_id": 19,
        "slug": "rugby",
        "icon": "🏉",
        "name_th": "รักบี้",
        "name_en": "Rugby",
        "label": "🏉 รักบี้ (Rugby Union / League)",
        "espn_feeds": [],
        "has_draw": True,
    },
    {
        "id": 66,
        "oddspapi_id": 26,
        "slug": "cricket",
        "icon": "🏏",
        "name_th": "คริกเก็ต",
        "name_en": "Cricket",
        "label": "🏏 คริกเก็ต (Cricket - IPL / T20)",
        "espn_feeds": [],
        "has_draw": False,
    },
    {
        "id": 21,
        "oddspapi_id": 27,
        "slug": "darts",
        "icon": "🎯",
        "name_th": "ปาเป้า",
        "name_en": "Darts",
        "label": "🎯 ปาเป้า (Darts - PDC Premier League)",
        "espn_feeds": [],
        "has_draw": False,
    },
    {
        "id": 18,
        "oddspapi_id": 28,
        "slug": "golf",
        "icon": "⛳",
        "name_th": "กอล์ฟ",
        "name_en": "Golf",
        "label": "⛳ กอล์ฟ (Golf - PGA / LPGA Head-to-Head)",
        "espn_feeds": [],
        "has_draw": False,
    },
    {
        "id": 24,
        "oddspapi_id": 29,
        "slug": "motorsport",
        "icon": "🏎️",
        "name_th": "มอเตอร์สปอร์ต",
        "name_en": "Motorsport / F1",
        "label": "🏎️ มอเตอร์สปอร์ต / Formula 1 (Motorsport)",
        "espn_feeds": [],
        "has_draw": False,
    },
]

SPORTS_BY_ID: Dict[int, Dict[str, Any]] = {item["id"]: item for item in SPORTS_CATALOG}


def get_sport_info(sport_id: int) -> Dict[str, Any]:
    """Return sport catalog metadata for a given 1xBet sport_id."""
    return SPORTS_BY_ID.get(int(sport_id), SPORTS_BY_ID[1])


@dataclass
class NormalizedMatch:
    """Unified match odds record across all 4 fetching methods."""

    method_id: str
    method_name: str
    source_mode: str
    match_id: str
    sport: str
    league: str
    home_team: str
    away_team: str
    start_time_utc: str
    match_status: str
    score: str = "-"
    odds_home: Optional[float] = None
    odds_draw: Optional[float] = None
    odds_away: Optional[float] = None
    implied_prob_home: Optional[float] = None
    implied_prob_draw: Optional[float] = None
    implied_prob_away: Optional[float] = None
    overround_pct: Optional[float] = None
    handicap_line: Optional[float] = None
    handicap_home: Optional[float] = None
    handicap_away: Optional[float] = None
    total_line: Optional[float] = None
    odds_over: Optional[float] = None
    odds_under: Optional[float] = None
    market_active: bool = True
    fetched_at_utc: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def finalize_metrics(self) -> "NormalizedMatch":
        """Compute implied probabilities and bookmaker overround/margin."""
        if not self.fetched_at_utc:
            self.fetched_at_utc = now_utc_iso()

        self.implied_prob_home = calc_implied_prob(self.odds_home)
        self.implied_prob_draw = calc_implied_prob(self.odds_draw)
        self.implied_prob_away = calc_implied_prob(self.odds_away)

        probs = [
            p
            for p in (
                self.implied_prob_home,
                self.implied_prob_draw,
                self.implied_prob_away,
            )
            if p is not None
        ]
        if len(probs) >= 2:
            self.overround_pct = round(sum(probs) - 100.0, 2)
        else:
            self.overround_pct = None
        return self

    def to_dict(self) -> Dict[str, Any]:
        """Serialize dataclass to a JSON-safe dictionary."""
        return asdict(self)


def now_utc_iso() -> str:
    """Return current UTC timestamp formatted as ISO-8601 Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def unix_to_iso(ts: Optional[int | float]) -> str:
    """Convert Unix seconds timestamp to ISO-8601 UTC string."""
    if not ts:
        return now_utc_iso()
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    except (ValueError, OSError, TypeError):
        return now_utc_iso()


def calc_implied_prob(price: Optional[float]) -> Optional[float]:
    """Calculate implied probability percentage from decimal odds."""
    if price is None or price <= 1.0:
        return None
    return round((1.0 / float(price)) * 100.0, 2)


_SPORT_FIXTURE_BANK: Dict[int, List[Dict[str, Any]]] = {
    1: [
        ("England. Premier League", "Arsenal", "Chelsea", "1 - 0 (62')", 1.75, 3.80, 4.60, -0.75, 2.5),
        ("England. Premier League", "Liverpool", "Manchester City", "2 - 2 (78')", 2.38, 3.55, 2.85, -0.25, 3.0),
        ("Spain. LaLiga", "Real Madrid", "FC Barcelona", "0 - 1 (41')", 1.96, 3.92, 3.50, -0.5, 3.0),
        ("UEFA Champions League", "Bayern Munich", "Paris Saint-Germain", "1 - 1 (33')", 1.83, 4.10, 3.95, -0.75, 3.25),
        ("Italy. Serie A", "Inter Milan", "AC Milan", "1 - 0 (19')", 1.88, 3.62, 4.25, -0.5, 2.5),
        ("Thailand. Thai League 1", "Buriram United", "BG Pathum United", "2 - 0 (55')", 1.54, 4.20, 5.60, -1.0, 2.75),
    ],
    3: [
        ("USA. NBA", "Boston Celtics", "Los Angeles Lakers", "84 - 79 (Q3 04:12)", 1.48, None, 2.72, -5.5, 224.5),
        ("USA. NBA", "Denver Nuggets", "Golden State Warriors", "61 - 58 (Q2 01:40)", 1.76, None, 2.12, -2.5, 231.5),
        ("USA. NBA", "Milwaukee Bucks", "Miami Heat", "92 - 88 (Q4 06:50)", 1.62, None, 2.35, -3.5, 218.5),
        ("EuroLeague", "Real Madrid Baloncesto", "Olympiacos", "44 - 41 (HT)", 1.68, None, 2.24, -3.0, 162.5),
        ("EuroLeague", "Panathinaikos", "Fenerbahce", "53 - 49 (Q3)", 1.80, None, 2.05, -2.0, 165.5),
        ("Australia. NBL", "Melbourne United", "Sydney Kings", "77 - 73 (Q3)", 1.72, None, 2.16, -2.5, 184.5),
    ],
    4: [
        ("ATP Tour. Masters 1000", "Carlos Alcaraz", "Jannik Sinner", "1 - 1 (6:4, 4:6, 3:2)", 1.92, None, 1.92, -0.5, 22.5),
        ("ATP Tour. Masters 1000", "Novak Djokovic", "Alexander Zverev", "1 - 0 (7:5, 2:1)", 1.65, None, 2.28, -2.5, 23.5),
        ("WTA Tour. 1000", "Iga Swiatek", "Aryna Sabalenka", "1 - 0 (6:3, 4:4)", 1.78, None, 2.08, -1.5, 21.5),
        ("WTA Tour. 1000", "Coco Gauff", "Elena Rybakina", "0 - 1 (5:7, 3:2)", 2.10, None, 1.76, 1.5, 22.5),
        ("ATP 500", "Daniil Medvedev", "Taylor Fritz", "1 - 0 (6:4, 1:0)", 1.60, None, 2.36, -2.5, 22.5),
        ("ATP 500", "Holger Rune", "Casper Ruud", "0 - 0 (4:3)", 1.98, None, 1.86, 0.5, 22.5),
    ],
    6: [
        ("Volleyball Nations League", "Thailand (W)", "Japan (W)", "1 - 1 (25:21, 19:25, 14:12)", 2.65, None, 1.48, 7.5, 180.5),
        ("Volleyball Nations League", "Brazil (W)", "Italy (W)", "1 - 0 (25:22, 11:10)", 2.05, None, 1.78, 2.5, 182.5),
        ("Italy. Serie A1", "Perugia", "Trentino", "2 - 1 (Set 4: 18:16)", 1.62, None, 2.30, -5.5, 184.5),
        ("Poland. PlusLiga", "Jastrzebski Wegiel", "ZAKSA", "1 - 0 (25:20, 9:7)", 1.55, None, 2.45, -6.5, 178.5),
        ("Turkey. Sultanlar Ligi", "VakifBank", "Fenerbahce", "2 - 2 (Set 5: 8:7)", 1.88, None, 1.92, -1.5, 186.5),
        ("Thailand League", "Nakhon Ratchasima", "Diamond Food", "1 - 0 (25:19, 15:12)", 1.70, None, 2.15, -4.5, 179.5),
    ],
    2: [
        ("USA. NHL", "Edmonton Oilers", "Florida Panthers", "2 - 1 (P2 11:20)", 2.02, 4.10, 3.05, -0.5, 6.0),
        ("USA. NHL", "Toronto Maple Leafs", "Boston Bruins", "1 - 1 (P2 04:55)", 2.25, 4.00, 2.65, -0.5, 5.5),
        ("USA. NHL", "New York Rangers", "Carolina Hurricanes", "3 - 2 (P3 08:10)", 2.18, 3.95, 2.75, -0.5, 5.5),
        ("KHL", "SKA Saint Petersburg", "CSKA Moscow", "1 - 0 (P1 16:40)", 1.95, 4.05, 3.20, -0.5, 5.0),
        ("Sweden. SHL", "Frolunda", "Skelleftea", "2 - 2 (P2)", 2.35, 3.90, 2.55, 0.0, 5.5),
        ("Finland. Liiga", "Tappara", "Ilves", "1 - 0 (P2)", 2.10, 3.95, 2.90, -0.5, 5.0),
    ],
    16: [
        ("BWF Super 1000", "Kunlavut Vitidsarn", "Viktor Axelsen", "1 - 0 (21:18, 12:10)", 2.35, None, 1.60, 4.5, 79.5),
        ("BWF Super 1000", "Ratchanok Intanon", "An Se-young", "0 - 1 (17:21, 14:11)", 3.10, None, 1.38, 7.5, 76.5),
        ("BWF Super 750", "Dechapol / Sapsiree", "Zheng / Huang", "1 - 1 (19:21, 21:17, 11:9)", 2.45, None, 1.55, 4.5, 84.5),
        ("BWF Super 750", "Jonatan Christie", "Shi Yuqi", "0 - 0 (16:15)", 2.05, None, 1.78, 1.5, 80.5),
        ("BWF Super 500", "Lee Zii Jia", "Kodai Naraoka", "1 - 0 (21:16, 8:6)", 1.74, None, 2.10, -3.5, 78.5),
        ("BWF Super 500", "Pornpawee Chochuwong", "Akane Yamaguchi", "0 - 1 (15:21, 9:11)", 2.65, None, 1.48, 5.5, 77.5),
    ],
    10: [
        ("WTT Champions", "Fan Zhendong", "Tomokazu Harimoto", "2 - 1 (Set 4: 7:5)", 1.42, None, 2.85, -1.5, 74.5),
        ("WTT Champions", "Wang Chuqin", "Felix Lebrun", "1 - 1 (Set 3: 9:8)", 1.36, None, 3.10, -1.5, 73.5),
        ("WTT Champions", "Sun Yingsha", "Hina Hayata", "2 - 0 (Set 3: 6:4)", 1.28, None, 3.65, -2.5, 71.5),
        ("TT Elite Series", "Kamil Nalepa", "Dawid Kotwica", "1 - 2 (Set 4)", 1.88, None, 1.92, -0.5, 75.5),
        ("Setka Cup", "Oleg Shcherbak", "Ivan Moroz", "2 - 1 (Set 4)", 1.76, None, 2.06, -1.5, 74.5),
        ("WTT Star Contender", "Orawan Paranang", "Shin Yubin", "1 - 1 (Set 3)", 2.45, None, 1.55, 1.5, 75.5),
    ],
    9: [
        ("ONE Friday Fights (Muay Thai)", "Rodtang Jitmuangnon", "Superlek Kiatmoo9", "Round 2", 1.85, 15.0, 2.02, None, 2.5),
        ("ONE Championship (Muay Thai)", "Tawanchai PK Saenchai", "Jo Nattawut", "Round 1", 1.45, 18.0, 2.80, None, 2.5),
        ("World Boxing Heavyweight", "Oleksandr Usyk", "Tyson Fury", "Round 4", 1.68, 16.0, 2.28, None, 10.5),
        ("World Boxing Welterweight", "Naoya Inoue", "Sam Goodman", "Round 3", 1.18, 22.0, 5.20, None, 7.5),
        ("RWS Rajadamnern", "Buakaw Banchamek", "Kouzi", "Round 2", 1.35, 17.0, 3.25, None, 2.5),
        ("World Boxing Lightweight", "Gervonta Davis", "Shakur Stevenson", "Pre-fight", 1.75, 15.0, 2.15, None, 10.5),
    ],
    56: [
        ("UFC PPV Main Event", "Islam Makhachev", "Arman Tsarukyan", "Round 2 (03:10)", 1.44, None, 2.85, None, 3.5),
        ("UFC Co-Main Event", "Alex Pereira", "Magomed Ankalaev", "Round 1 (04:05)", 1.82, None, 2.02, None, 2.5),
        ("UFC Fight Night", "Ilia Topuria", "Alexander Volkanovski", "Pre-fight", 1.56, None, 2.48, None, 3.5),
        ("ONE MMA", "Stamp Fairtex", "Denice Zamboanga", "Round 1 (02:45)", 1.60, None, 2.38, None, 2.5),
        ("UFC Bantamweight", "Merab Dvalishvili", "Umar Nurmagomedov", "Pre-fight", 2.15, None, 1.72, None, 4.5),
        ("PFL Championship", "Francis Ngannou", "Renan Ferreira", "Pre-fight", 1.48, None, 2.70, None, 1.5),
    ],
    40: [
        ("Dota 2. DreamLeague", "Team Liquid", "Gaimin Gladiators", "1 - 1 (Map 3 · 24:10)", 1.82, None, 2.00, -0.5, 2.5),
        ("CS2. ESL Pro League", "Natus Vincere", "FaZe Clan", "1 - 0 (Map 2 · 9:7)", 1.74, None, 2.10, -1.5, 2.5),
        ("League of Legends. LCK", "T1", "Gen.G", "1 - 1 (Map 3 · 18:40)", 2.05, None, 1.78, 0.5, 2.5),
        ("Valorant. VCT Pacific", "Paper Rex", "DRX", "1 - 0 (Map 2 · 8:5)", 1.68, None, 2.18, -1.5, 2.5),
        ("RoV / Arena of Valor. RPL", "Bacon Time", "Buriram United Esports", "2 - 1 (Game 4)", 1.62, None, 2.30, -1.5, 4.5),
        ("CS2. BLAST Premier", "Team Vitality", "Team Spirit", "0 - 1 (Map 2 · 6:8)", 1.92, None, 1.90, -0.5, 2.5),
    ],
    5: [
        ("USA. MLB", "Los Angeles Dodgers", "New York Yankees", "4 - 2 (Top 6th)", 1.72, None, 2.18, -1.5, 8.5),
        ("USA. MLB", "Atlanta Braves", "Philadelphia Phillies", "3 - 3 (Bot 5th)", 1.88, None, 1.96, -0.5, 8.0),
        ("Japan. NPB", "Hanshin Tigers", "Yomiuri Giants", "2 - 1 (Top 7th)", 1.80, None, 2.05, -0.5, 6.5),
        ("South Korea. KBO", "KIA Tigers", "Samsung Lions", "5 - 3 (Bot 6th)", 1.66, None, 2.26, -1.5, 9.5),
        ("USA. MLB", "Houston Astros", "Texas Rangers", "1 - 0 (Top 4th)", 1.78, None, 2.08, -1.5, 8.5),
        ("USA. MLB", "Boston Red Sox", "Baltimore Orioles", "2 - 4 (Top 7th)", 2.12, None, 1.75, 1.5, 9.0),
    ],
    13: [
        ("USA. NFL", "Kansas City Chiefs", "Buffalo Bills", "17 - 14 (Q3 08:20)", 1.76, None, 2.10, -2.5, 48.5),
        ("USA. NFL", "Baltimore Ravens", "Cincinnati Bengals", "21 - 17 (Q3 02:15)", 1.58, None, 2.45, -3.5, 51.5),
        ("USA. NFL", "San Francisco 49ers", "Detroit Lions", "14 - 14 (HT)", 1.94, None, 1.90, -1.0, 50.5),
        ("USA. NFL", "Philadelphia Eagles", "Dallas Cowboys", "24 - 10 (Q3)", 1.42, None, 2.95, -6.5, 46.5),
        ("USA. NCAA", "Georgia Bulldogs", "Alabama Crimson Tide", "20 - 17 (Q3)", 1.82, None, 2.02, -2.0, 54.5),
        ("USA. NFL", "Miami Dolphins", "New York Jets", "10 - 7 (Q2)", 1.65, None, 2.28, -3.0, 44.5),
    ],
    19: [
        ("World Snooker Championship", "Ronnie O'Sullivan", "Judd Trump", "6 - 5 (Frame 12)", 1.86, None, 1.96, -1.5, 18.5),
        ("UK Championship", "Mark Selby", "Kyren Wilson", "4 - 3 (Frame 8)", 1.92, None, 1.90, -0.5, 9.5),
        ("Masters", "John Higgins", "Shaun Murphy", "3 - 3 (Frame 7)", 2.02, None, 1.82, 1.5, 9.5),
        ("Thailand Snooker Open", "Thepchaiya Un-Nooh", "Noppon Saengkham", "2 - 2 (Frame 5)", 1.88, None, 1.94, -0.5, 7.5),
        ("Champions League Snooker", "Mark Allen", "Neil Robertson", "2 - 1 (Frame 4)", 1.78, None, 2.06, -1.5, 5.5),
        ("Players Championship", "Ding Junhui", "Luca Brecel", "4 - 2 (Frame 7)", 1.70, None, 2.18, -1.5, 9.5),
    ],
    29: [
        ("Thailand Futsal League", "Chonburi Bluewave", "Port ASM", "2 - 1 (24')", 1.68, 4.30, 3.90, -0.75, 5.5),
        ("Thailand Futsal League", "Hongyen Thakam", "Black Pearl United", "3 - 2 (31')", 1.82, 4.10, 3.40, -0.5, 6.5),
        ("Spain. Primera Division", "Barca Futsal", "Inter Movistar", "1 - 1 (18')", 1.74, 4.25, 3.65, -0.5, 5.5),
        ("UEFA Futsal Champions", "Sporting CP", "Benfica", "2 - 2 (28')", 1.95, 4.00, 3.10, -0.25, 5.5),
        ("Brazil. LNF", "Magnus Futsal", "Joinville", "4 - 2 (33')", 1.60, 4.40, 4.20, -1.0, 6.5),
        ("FIFA Futsal Friendlies", "Thailand", "Iran", "1 - 2 (22')", 3.20, 4.10, 1.90, 0.75, 5.5),
    ],
    8: [
        ("EHF Champions League", "Barca Handball", "THW Kiel", "18 - 16 (38')", 1.55, 8.50, 3.10, -2.5, 61.5),
        ("EHF Champions League", "SC Magdeburg", "Aalborg", "22 - 21 (45')", 1.78, 8.00, 2.55, -1.5, 62.5),
        ("Germany. Bundesliga", "Fuchse Berlin", "SG Flensburg", "15 - 15 (30' HT)", 1.85, 7.80, 2.40, -1.0, 60.5),
        ("France. Starligue", "PSG Handball", "Montpellier", "20 - 17 (40')", 1.48, 8.80, 3.40, -3.5, 63.5),
        ("EHF Women", "Gyor Audi ETO", "Vipers Kristiansand", "16 - 14 (35')", 1.62, 8.20, 2.85, -2.0, 58.5),
        ("Spain. Liga ASOBAL", "Granollers", "Bidasoa Irun", "13 - 12 (27')", 1.92, 7.60, 2.30, -0.5, 57.5),
    ],
    7: [
        ("Six Nations", "Ireland", "France", "16 - 13 (52')", 1.75, 19.0, 2.22, -2.5, 45.5),
        ("Rugby Championship", "New Zealand All Blacks", "South Africa Springboks", "20 - 18 (58')", 1.90, 18.0, 1.98, -0.5, 46.5),
        ("Super Rugby Pacific", "Crusaders", "Blues", "14 - 17 (44')", 2.15, 20.0, 1.76, 2.5, 48.5),
        ("England. Premiership", "Saracens", "Harlequins", "21 - 14 (55')", 1.60, 21.0, 2.48, -4.5, 51.5),
        ("France. Top 14", "Toulouse", "La Rochelle", "18 - 10 (49')", 1.45, 22.0, 2.95, -6.5, 44.5),
        ("Australia. NRL", "Penrith Panthers", "Melbourne Storm", "12 - 12 (HT)", 1.88, 17.0, 2.02, -1.5, 39.5),
    ],
    66: [
        ("India. IPL", "Mumbai Indians", "Chennai Super Kings", "142/3 (15.2 ov)", 1.84, None, 2.00, None, 345.5),
        ("India. IPL", "Royal Challengers Bengaluru", "Kolkata Knight Riders", "118/4 (13.0 ov)", 1.96, None, 1.88, None, 355.5),
        ("International T20", "India", "Australia", "165/5 (17.4 ov)", 1.72, None, 2.16, None, 340.5),
        ("International T20", "England", "Pakistan", "98/2 (11.1 ov)", 1.68, None, 2.22, None, 330.5),
        ("Big Bash League", "Sydney Sixers", "Perth Scorchers", "124/3 (14.0 ov)", 1.90, None, 1.94, None, 325.5),
        ("SA20", "Sunrisers Eastern Cape", "MI Cape Town", "88/1 (9.5 ov)", 1.80, None, 2.04, None, 320.5),
    ],
    21: [
        ("PDC Premier League", "Luke Littler", "Luke Humphries", "5 - 4 (Legs)", 1.78, None, 2.06, -1.5, 16.5),
        ("PDC Premier League", "Michael van Gerwen", "Gerwyn Price", "4 - 4 (Legs)", 1.72, None, 2.14, -1.5, 16.5),
        ("PDC European Tour", "Nathan Aspinall", "Rob Cross", "3 - 2 (Legs)", 1.95, None, 1.88, 0.5, 9.5),
        ("PDC World Matchplay", "Gary Anderson", "Dave Chisnall", "7 - 6 (Legs)", 1.82, None, 2.02, -1.5, 18.5),
        ("MODUS Super Series", "Fallon Sherrock", "Beau Greaves", "2 - 3 (Legs)", 2.25, None, 1.66, 1.5, 6.5),
        ("PDC Players Championship", "Stephen Bunting", "Damon Heta", "4 - 3 (Legs)", 1.86, None, 1.96, -0.5, 9.5),
    ],
    18: [
        ("PGA Tour. Matchup", "Scottie Scheffler", "Rory McIlroy", "Thru 12 (-4 vs -3)", 1.65, None, 2.25, -0.5, None),
        ("PGA Tour. Matchup", "Xander Schauffele", "Jon Rahm", "Thru 14 (-5 vs -4)", 1.82, None, 2.02, -0.5, None),
        ("LPGA Tour. Matchup", "Atthaya Thitikul", "Nelly Korda", "Thru 11 (-3 vs -3)", 2.05, None, 1.78, 0.5, None),
        ("PGA Tour. Matchup", "Viktor Hovland", "Collin Morikawa", "Thru 9 (-2 vs -1)", 1.92, None, 1.90, -0.5, None),
        ("DP World Tour", "Tommy Fleetwood", "Shane Lowry", "Thru 15 (-6 vs -5)", 1.85, None, 1.98, -0.5, None),
        ("LPGA Tour. Matchup", "Patty Tavatanakit", "Lydia Ko", "Thru 10 (-2 vs -2)", 1.98, None, 1.84, 0.5, None),
    ],
    24: [
        ("Formula 1. Race H2H", "Max Verstappen", "Lando Norris", "Lap 32 / 57", 1.74, None, 2.12, None, None),
        ("Formula 1. Race H2H", "Charles Leclerc", "Oscar Piastri", "Lap 32 / 57", 1.86, None, 1.96, None, None),
        ("Formula 1. Race H2H", "Lewis Hamilton", "George Russell", "Lap 32 / 57", 1.95, None, 1.88, None, None),
        ("MotoGP. Race H2H", "Francesco Bagnaia", "Jorge Martin", "Lap 14 / 25", 1.88, None, 1.94, None, None),
        ("MotoGP. Race H2H", "Marc Marquez", "Enea Bastianini", "Lap 14 / 25", 1.62, None, 2.30, None, None),
        ("Formula 1. Qualifying H2H", "Carlos Sainz", "Fernando Alonso", "Q2", 1.54, None, 2.48, None, None),
    ],
}


def parse_date_window(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> tuple[datetime, datetime]:
    """Parse YYYY-MM-DD bounds into UTC start (00:00:00Z) and end (23:59:59Z)."""
    today_utc = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    def _parse_day(val: Optional[str], fallback: datetime) -> datetime:
        if not val or not str(val).strip():
            return fallback
        try:
            dt = datetime.strptime(str(val).strip()[:10], "%Y-%m-%d")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return fallback

    start_day = _parse_day(date_from, today_utc)
    end_day = _parse_day(date_to, start_day + timedelta(days=3))
    if end_day < start_day:
        start_day, end_day = end_day, start_day

    start_dt = start_day.replace(hour=0, minute=0, second=0, microsecond=0)
    end_dt = end_day.replace(hour=23, minute=59, second=59, microsecond=0)
    return start_dt, end_dt


def get_sample_match_seeds(
    mode: str = "prematch",
    sport_id: int = 1,
    count: int = 6,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return realistic match seeds for any sport_id (including 0 = All Sports) within date range."""
    is_live = mode == "live"
    target_count = max(1, min(int(count), 50))
    start_dt, end_dt = parse_date_window(date_from, date_to)
    span_seconds = max(3600, int((end_dt - start_dt).total_seconds()))

    sid_int = int(sport_id)
    pool: List[tuple[int, tuple[Any, ...]]] = []
    if sid_int == 0:
        sport_ids_order = [
            s["id"] for s in SPORTS_CATALOG if s["id"] != 0 and s["id"] in _SPORT_FIXTURE_BANK
        ]
        max_len = max(len(_SPORT_FIXTURE_BANK[k]) for k in sport_ids_order)
        for row_idx in range(max_len):
            for k in sport_ids_order:
                rows = _SPORT_FIXTURE_BANK[k]
                if row_idx < len(rows):
                    pool.append((k, rows[row_idx]))
    else:
        resolved_sid = sid_int if sid_int in _SPORT_FIXTURE_BANK else 1
        for row in _SPORT_FIXTURE_BANK[resolved_sid]:
            pool.append((resolved_sid, row))

    seeds: List[Dict[str, Any]] = []
    for idx in range(target_count):
        base_sid, row = pool[idx % len(pool)]
        cycle = idx // len(pool)
        sport_meta = get_sport_info(base_sid)
        league, home, away, live_score, o1, ox, o2, hdp_line, ou_line = row

        if cycle > 0:
            home_name = f"{home} (R{cycle + 1})"
            away_name = f"{away} (R{cycle + 1})"
            league_name = f"{league} · Group {chr(65 + (cycle % 4))}"
            o1 = round(max(1.12, o1 + (0.04 if cycle % 2 else -0.03)), 2)
            o2 = round(max(1.12, o2 + (-0.05 if cycle % 2 else 0.04)), 2)
        else:
            home_name = home
            away_name = away
            league_name = league

        # Distribute timestamps cleanly across [start_dt + 1h, end_dt - 1h]
        usable_span = max(60, span_seconds - 7200)
        offset_sec = 3600 + int((usable_span * idx) / max(1, target_count - 1))
        match_dt = min(end_dt, start_dt + timedelta(seconds=offset_sec))
        active = not (is_live and idx % 4 == 2)

        seeds.append(
            {
                "id": 549200000 + base_sid * 1000 + idx + 1,
                "oddspapi_id": f"id{base_sid:02d}0000123{idx + 1:03d}",
                "sport_id": base_sid,
                "sport_label": f"{sport_meta['icon']} {sport_meta['name_th']} ({sport_meta['name_en']})",
                "league": league_name,
                "home": home_name,
                "away": away_name,
                "start_unix": int(match_dt.timestamp()),
                "start_iso": match_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "score": live_score if is_live else "-",
                "status": "Live" if is_live else "Pre-match",
                "home_odds": o1,
                "draw_odds": ox,
                "away_odds": o2,
                "hdp_line": hdp_line,
                "hdp_home": 1.92 if hdp_line is not None else None,
                "hdp_away": 1.96 if hdp_line is not None else None,
                "ou_line": ou_line,
                "over_odds": 1.88 if ou_line is not None else None,
                "under_odds": 2.00 if ou_line is not None else None,
                "active": active,
            }
        )
    return seeds


def build_simulated_vzip_payload(
    mode: str = "prematch",
    count: int = 10,
    sport_id: int = 1,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a realistic 1xBet Get1x2_VZip raw JSON response (`Value` & `E` keys)."""
    seeds = get_sample_match_seeds(
        mode=mode,
        sport_id=sport_id,
        count=count,
        date_from=date_from,
        date_to=date_to,
    )
    value_items: List[Dict[str, Any]] = []
    for s in seeds:
        events: List[Dict[str, Any]] = [
            {"G": 1, "T": 1, "C": s["home_odds"], "B": not s["active"]},
        ]
        if s["draw_odds"] is not None:
            events.append({"G": 1, "T": 2, "C": s["draw_odds"], "B": not s["active"]})
        events.append({"G": 1, "T": 3, "C": s["away_odds"], "B": not s["active"]})

        if s["hdp_line"] is not None and s["hdp_home"] is not None and s["hdp_away"] is not None:
            events.extend(
                [
                    {"G": 2, "T": 7, "C": s["hdp_home"], "P": s["hdp_line"]},
                    {"G": 2, "T": 8, "C": s["hdp_away"], "P": -s["hdp_line"]},
                ]
            )
        if s["ou_line"] is not None and s["over_odds"] is not None and s["under_odds"] is not None:
            events.extend(
                [
                    {"G": 17, "T": 9, "C": s["over_odds"], "P": s["ou_line"]},
                    {"G": 17, "T": 10, "C": s["under_odds"], "P": s["ou_line"]},
                ]
            )

        entry: Dict[str, Any] = {
            "I": s["id"],
            "SI": int(s["sport_id"]),
            "L": s["league"],
            "O1": s["home"],
            "O2": s["away"],
            "S": s["start_unix"],
            "E": events,
        }
        if mode == "live":
            entry["SC"] = {"CPS": s["score"]}
        value_items.append(entry)

    return {
        "Error": "",
        "ErrorCode": 0,
        "Guid": "",
        "Id": 0,
        "Success": True,
        "Value": value_items,
    }
