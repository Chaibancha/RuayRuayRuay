"""Method 4: OddsPapi Free Tier REST API (/v4).

Implements the exact 2-step workflow from the Gemini guide:
  1. GET /v4/fixtures (sportId=10, bookmaker="1xbet", from/to UTC ISO-8601)
  2. GET /v4/odds (batch fixtureIds when supported, parsing 5-level nested schema:
     bookmakers -> "1xbet" -> markets -> "101" -> outcomes -> "101"/"102"/"103"
     -> players -> "0" -> {price, active, lastUpdated})
Also caches /v4/markets locally in cache/oddspapi_markets.json to conserve the
250 requests/month Free Tier quota.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from fetchers.schema import (
        NormalizedMatch,
        get_sample_match_seeds,
        get_sport_info,
        now_utc_iso,
        parse_date_window,
    )
else:
    from .schema import (
        NormalizedMatch,
        get_sample_match_seeds,
        get_sport_info,
        now_utc_iso,
        parse_date_window,
    )

METHOD_ID = "4"
METHOD_NAME = "4. OddsPapi (Free Tier)"
BASE_URL = "https://api.oddspapi.io/v4"
SPORT_FOOTBALL = 10
BOOKMAKER_SLUG = "1xbet"
MARKET_1X2 = "101"
MARKET_OU = "104"
MARKET_HDP = "105"

DEFAULT_MARKETS_CACHE = {
    "101": {"name": "Full Time Result (1X2)", "outcomes": {"101": "Home", "102": "Draw", "103": "Away"}},
    "104": {"name": "Over/Under Total Goals"},
    "105": {"name": "Asian Handicap"},
}

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"
MARKETS_CACHE_PATH = CACHE_DIR / "oddspapi_markets.json"


def load_or_cache_markets(api_key: Optional[str] = None) -> Dict[str, Any]:
    """Load cached OddsPapi market dictionary or fetch once if API key is provided."""
    if MARKETS_CACHE_PATH.exists():
        try:
            return json.loads(MARKETS_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass

    if api_key and api_key.strip() and api_key != "YOUR_API_KEY_HERE":
        try:
            resp = requests.get(
                f"{BASE_URL}/markets",
                params={"apiKey": api_key.strip()},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                MARKETS_CACHE_PATH.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                return data
        except Exception:
            pass

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    MARKETS_CACHE_PATH.write_text(
        json.dumps(DEFAULT_MARKETS_CACHE, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return DEFAULT_MARKETS_CACHE


def get_upcoming_fixtures(
    api_key: str,
    hours_ahead: int = 24,
    sport_id: int = SPORT_FOOTBALL,
    timeout: int = 12,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Step 1: Fetch upcoming fixtures carrying 1xBet odds."""
    if date_from or date_to:
        from_dt, to_dt = parse_date_window(date_from, date_to)
    else:
        from_dt = datetime.now(timezone.utc)
        to_dt = from_dt + timedelta(hours=hours_ahead)
    params: Dict[str, Any] = {
        "apiKey": api_key,
        "bookmaker": BOOKMAKER_SLUG,
        "from": from_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "to": to_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if int(sport_id) > 0:
        params["sportId"] = int(sport_id)
    resp = requests.get(f"{BASE_URL}/fixtures", params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else data.get("fixtures", [])


def get_1xbet_odds_batch(
    api_key: str,
    fixture_ids: List[str],
    timeout: int = 15,
) -> List[Dict[str, Any]]:
    """Step 2: Fetch 1xBet odds using comma-separated fixtureIds to save quota."""
    if not fixture_ids:
        return []
    params = {
        "apiKey": api_key,
        "fixtureIds": ",".join(fixture_ids),
        "bookmaker": BOOKMAKER_SLUG,
    }
    resp = requests.get(f"{BASE_URL}/odds", params=params, timeout=timeout)
    if resp.status_code == 400 and len(fixture_ids) == 1:
        params.pop("fixtureIds", None)
        params["fixtureId"] = fixture_ids[0]
        resp = requests.get(f"{BASE_URL}/odds", params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else [data]


def parse_oddspapi_payload(
    odds_payload: Dict[str, Any],
    fetched_at: Optional[str] = None,
    source_mode: str = "live",
) -> NormalizedMatch:
    """Parse OddsPapi 5-level nested JSON structure into NormalizedMatch."""
    bookmakers = odds_payload.get("bookmakers", {})
    xbet_data = bookmakers.get(BOOKMAKER_SLUG, {})
    markets = xbet_data.get("markets", {})

    market_1x2 = markets.get(MARKET_1X2, {})
    outcomes_1x2 = market_1x2.get("outcomes", {})

    def _extract_outcome(outcomes: Dict[str, Any], key: str) -> tuple[Optional[float], bool]:
        node = (outcomes.get(key) or {}).get("players", {}).get("0", {})
        price = node.get("price")
        active = bool(node.get("active", False))
        if price is not None and active:
            return float(price), True
        if price is not None and not active:
            return float(price), False
        return None, False

    p_home, act_h = _extract_outcome(outcomes_1x2, "101")
    p_draw, act_d = _extract_outcome(outcomes_1x2, "102")
    p_away, act_a = _extract_outcome(outcomes_1x2, "103")
    any_active = act_h or act_d or act_a

    # Optional Over/Under (market 104) & Handicap (market 105)
    market_ou = markets.get(MARKET_OU, {})
    ou_outcomes = market_ou.get("outcomes", {})
    p_over, _ = _extract_outcome(ou_outcomes, "104")
    p_under, _ = _extract_outcome(ou_outcomes, "105")
    ou_line = market_ou.get("handicap")

    market_hdp = markets.get(MARKET_HDP, {})
    hdp_outcomes = market_hdp.get("outcomes", {})
    p_hdp_h, _ = _extract_outcome(hdp_outcomes, "101")
    p_hdp_a, _ = _extract_outcome(hdp_outcomes, "103")
    hdp_line = market_hdp.get("handicap")

    return NormalizedMatch(
        method_id=METHOD_ID,
        method_name=METHOD_NAME,
        source_mode=source_mode,
        match_id=str(odds_payload.get("fixtureId", "")),
        sport=str(odds_payload.get("sportLabel") or ("Football" if odds_payload.get("sportId", 10) == 10 else f"Sport #{odds_payload.get('sportId')}")),
        league=str(odds_payload.get("tournamentName") or "OddsPapi Tournament"),
        home_team=str(odds_payload.get("participant1Name", "Home")),
        away_team=str(odds_payload.get("participant2Name", "Away")),
        start_time_utc=str(odds_payload.get("startTime") or now_utc_iso()),
        match_status=str(odds_payload.get("status") or "Pre-match"),
        score=str(odds_payload.get("score") or "-"),
        odds_home=p_home,
        odds_draw=p_draw,
        odds_away=p_away,
        handicap_line=hdp_line,
        handicap_home=p_hdp_h,
        handicap_away=p_hdp_a,
        total_line=ou_line,
        odds_over=p_over,
        odds_under=p_under,
        market_active=any_active,
        fetched_at_utc=fetched_at or now_utc_iso(),
        extra={
            "bookmaker_slug": BOOKMAKER_SLUG,
            "markets_count": len(markets),
            "quota_limit": "250 requests/month (Free Tier)",
        },
    ).finalize_metrics()


def _build_simulated_oddspapi_payloads(
    mode: str = "prematch",
    count: int = 10,
    sport_id: int = 1,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Create realistic 5-level nested OddsPapi /v4/odds payloads."""
    ts = now_utc_iso()
    payloads: List[Dict[str, Any]] = []
    seeds = get_sample_match_seeds(
        mode=mode,
        sport_id=sport_id,
        count=count,
        date_from=date_from,
        date_to=date_to,
    )
    for s in seeds:
        oddspapi_sid = get_sport_info(s["sport_id"])["oddspapi_id"]
        outcomes_1x2: Dict[str, Any] = {
            "101": {"players": {"0": {"price": s["home_odds"], "active": s["active"], "lastUpdated": ts}}},
            "103": {"players": {"0": {"price": s["away_odds"], "active": s["active"], "lastUpdated": ts}}},
        }
        if s["draw_odds"] is not None:
            outcomes_1x2["102"] = {"players": {"0": {"price": s["draw_odds"], "active": s["active"], "lastUpdated": ts}}}

        markets_obj: Dict[str, Any] = {MARKET_1X2: {"outcomes": outcomes_1x2}}
        if s["ou_line"] is not None and s["over_odds"] is not None:
            markets_obj[MARKET_OU] = {
                "handicap": s["ou_line"],
                "outcomes": {
                    "104": {"players": {"0": {"price": s["over_odds"], "active": s["active"], "lastUpdated": ts}}},
                    "105": {"players": {"0": {"price": s["under_odds"], "active": s["active"], "lastUpdated": ts}}},
                },
            }
        if s["hdp_line"] is not None and s["hdp_home"] is not None:
            markets_obj[MARKET_HDP] = {
                "handicap": s["hdp_line"],
                "outcomes": {
                    "101": {"players": {"0": {"price": s["hdp_home"], "active": s["active"], "lastUpdated": ts}}},
                    "103": {"players": {"0": {"price": s["hdp_away"], "active": s["active"], "lastUpdated": ts}}},
                },
            }

        payloads.append(
            {
                "fixtureId": s["oddspapi_id"],
                "sportId": oddspapi_sid,
                "sportLabel": s["sport_label"],
                "tournamentName": s["league"],
                "participant1Name": s["home"],
                "participant2Name": s["away"],
                "startTime": s["start_iso"],
                "status": s["status"],
                "score": s["score"],
                "bookmakers": {
                    BOOKMAKER_SLUG: {
                        "markets": markets_obj
                    }
                },
            }
        )
    return payloads


def fetch_oddspapi_odds(
    mode: str = "prematch",
    sport_id: int = 1,
    count: int = 5,
    api_key: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch 1xBet odds via OddsPapi /v4 REST API with local market cache & fallback."""
    started = time.perf_counter()
    resolved_key = (api_key or os.getenv("ODDSPAPI_API_KEY") or "").strip()
    load_or_cache_markets(resolved_key or None)
    sport_info = get_sport_info(sport_id)
    oddspapi_sid = sport_info["oddspapi_id"]

    raw_payloads: List[Dict[str, Any]] = []
    error_detail: Optional[str] = None
    source_mode = "live (OddsPapi v4)"
    requests_used = 0

    if resolved_key and resolved_key != "YOUR_API_KEY_HERE":
        try:
            fixtures = get_upcoming_fixtures(
                api_key=resolved_key,
                hours_ahead=24,
                sport_id=oddspapi_sid,
                date_from=date_from,
                date_to=date_to,
            )
            requests_used += 1
            target_ids = [
                str(f["fixtureId"])
                for f in fixtures[: max(1, min(int(count), 20))]
                if f.get("fixtureId")
            ]
            if target_ids:
                raw_payloads = get_1xbet_odds_batch(
                    api_key=resolved_key, fixture_ids=target_ids
                )
                for p in raw_payloads:
                    p.setdefault(
                        "sportLabel",
                        f"{sport_info['icon']} {sport_info['name_th']} ({sport_info['name_en']})",
                    )
                requests_used += 1
            else:
                error_detail = "No upcoming 1xBet fixtures returned in the selected date range."
        except Exception as exc:
            error_detail = f"{type(exc).__name__}: {exc}"
    else:
        error_detail = (
            "ODDSPAPI_API_KEY is not configured; using realistic 5-level nested "
            "OddsPapi v4 sample payload (enter your free API key to query live)."
        )

    is_live = len(raw_payloads) > 0
    if not is_live:
        source_mode = "simulated_fallback (No API Key / Quota)"
        raw_payloads = _build_simulated_oddspapi_payloads(
            mode=mode,
            count=count,
            sport_id=sport_id,
            date_from=date_from,
            date_to=date_to,
        )

    fetched_at = now_utc_iso()
    matches = [
        parse_oddspapi_payload(p, fetched_at=fetched_at, source_mode=source_mode)
        for p in raw_payloads
    ]
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)

    endpoint_hint = (
        f"{BASE_URL}/odds?bookmaker={BOOKMAKER_SLUG}"
        + (f"&sportId={oddspapi_sid}" if oddspapi_sid > 0 else "")
    )
    return {
        "method_id": METHOD_ID,
        "method_name": METHOD_NAME,
        "endpoint": endpoint_hint,
        "mode": mode,
        "date_range": {"from": date_from, "to": date_to},
        "source_mode": source_mode,
        "is_live_data": is_live,
        "requests_used_this_run": requests_used,
        "quota_monthly_limit": 250,
        "latency_ms": elapsed_ms,
        "match_count": len(matches),
        "error": error_detail,
        "fetched_at_utc": fetched_at,
        "matches": [m.to_dict() for m in matches],
        "raw_payload": raw_payloads,
    }


if __name__ == "__main__":
    result = fetch_oddspapi_odds(mode="prematch", count=5)
    print(f"[{result['method_name']}]")
    print(
        f"Status: {result['source_mode']} | Matches: {result['match_count']} | Latency: {result['latency_ms']} ms"
    )
    if result["error"]:
        print(f"Notice: {result['error']}")
    for m in result["matches"][:5]:
        print(
            f" - [{m['league']}] {m['home_team']} vs {m['away_team']} | "
            f"1X2: {m['odds_home']} / {m['odds_draw']} / {m['odds_away']} | "
            f"Implied %: {m['implied_prob_home']}% / {m['implied_prob_draw']}% / {m['implied_prob_away']}%"
        )
    if "--json" in sys.argv:
        print(json.dumps(result["matches"], ensure_ascii=False, indent=2))
