"""Method 4: OddsPapi Free Tier REST API (/v4).

Implements the exact 2-step workflow from the Gemini guide:
  1. GET /v4/fixtures (bookmaker="1xbet", from/to UTC ISO-8601)
  2. GET /v4/odds (batch fixtureIds, parsing 5-level nested schema:
     bookmakers -> "1xbet" -> markets -> "101" -> outcomes -> "101"/"102"/"103"
     -> players -> "0" -> {price, active, lastUpdated})
When ODDSPAPI_API_KEY is not configured, maps REAL live upcoming 1xBet matches
for the selected date range into OddsPapi's 5-level nested JSON schema so the
user never receives fake/past matches.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from fetchers.method1_internal_feed import fetch_live_vzip_bundle
    from fetchers.schema import (
        DEMO_SOURCE_MODE,
        UNAVAILABLE_SOURCE_MODE,
        NormalizedMatch,
        filter_matches_for_request,
        get_sample_match_seeds,
        get_sport_info,
        now_utc_iso,
        parse_date_window,
    )
else:
    from .method1_internal_feed import fetch_live_vzip_bundle
    from .schema import (
        DEMO_SOURCE_MODE,
        UNAVAILABLE_SOURCE_MODE,
        NormalizedMatch,
        filter_matches_for_request,
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
    tz_offset_minutes: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Step 1: Fetch upcoming fixtures carrying 1xBet odds."""
    if date_from or date_to:
        from_dt, to_dt = parse_date_window(date_from, date_to, tz_offset_minutes)
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


def _matches_to_oddspapi_payloads(
    matches: List[NormalizedMatch], oddspapi_sid: int
) -> List[Dict[str, Any]]:
    """Convert real NormalizedMatch records into OddsPapi 5-level nested JSON schema."""
    ts = now_utc_iso()
    payloads: List[Dict[str, Any]] = []
    for m in matches:
        outcomes_1x2: Dict[str, Any] = {}
        if m.odds_home is not None:
            outcomes_1x2["101"] = {"players": {"0": {"price": m.odds_home, "active": m.market_active, "lastUpdated": ts}}}
        if m.odds_draw is not None:
            outcomes_1x2["102"] = {"players": {"0": {"price": m.odds_draw, "active": m.market_active, "lastUpdated": ts}}}
        if m.odds_away is not None:
            outcomes_1x2["103"] = {"players": {"0": {"price": m.odds_away, "active": m.market_active, "lastUpdated": ts}}}

        markets_obj: Dict[str, Any] = {MARKET_1X2: {"outcomes": outcomes_1x2}}
        if m.total_line is not None and m.odds_over is not None:
            markets_obj[MARKET_OU] = {
                "handicap": m.total_line,
                "outcomes": {
                    "104": {"players": {"0": {"price": m.odds_over, "active": m.market_active, "lastUpdated": ts}}},
                    "105": {"players": {"0": {"price": m.odds_under, "active": m.market_active, "lastUpdated": ts}}},
                },
            }
        if m.handicap_line is not None and m.handicap_home is not None:
            markets_obj[MARKET_HDP] = {
                "handicap": m.handicap_line,
                "outcomes": {
                    "101": {"players": {"0": {"price": m.handicap_home, "active": m.market_active, "lastUpdated": ts}}},
                    "103": {"players": {"0": {"price": m.handicap_away, "active": m.market_active, "lastUpdated": ts}}},
                },
            }

        payloads.append(
            {
                "fixtureId": f"id{m.match_id}",
                "sportId": oddspapi_sid or 10,
                "sportLabel": m.sport,
                "tournamentName": m.league,
                "participant1Name": m.home_team,
                "participant2Name": m.away_team,
                "startTime": m.start_time_utc,
                "status": m.match_status,
                "score": m.score,
                "bookmakers": {BOOKMAKER_SLUG: {"markets": markets_obj}},
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
    tz_offset_minutes: Optional[int] = None,
    demo_mode: bool = False,
) -> Dict[str, Any]:
    """Fetch 1xBet odds via OddsPapi /v4 REST API (or map live 1xBet feed into v4 schema)."""
    started = time.perf_counter()
    start_dt, end_dt = parse_date_window(date_from, date_to, tz_offset_minutes)
    resolved_key = (api_key or os.getenv("ODDSPAPI_API_KEY") or "").strip()
    load_or_cache_markets(resolved_key or None)
    sport_info = get_sport_info(sport_id)
    oddspapi_sid = sport_info["oddspapi_id"]
    fetched_at = now_utc_iso()

    raw_payloads: List[Dict[str, Any]] = []
    matches: List[NormalizedMatch] = []
    filter_stats: Dict[str, int] = {}
    error_detail: Optional[str] = None
    source_mode = "live (OddsPapi v4)"
    requests_used = 0
    is_live = False
    is_demo = False

    if resolved_key and resolved_key != "YOUR_API_KEY_HERE":
        try:
            fixtures = get_upcoming_fixtures(
                api_key=resolved_key,
                hours_ahead=24,
                sport_id=oddspapi_sid,
                date_from=date_from,
                date_to=date_to,
                tz_offset_minutes=tz_offset_minutes,
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
                parsed = [
                    parse_oddspapi_payload(p, fetched_at=fetched_at, source_mode=source_mode)
                    for p in raw_payloads
                ]
                matches, filter_stats = filter_matches_for_request(
                    parsed, mode, start_dt, end_dt, count
                )
                is_live = True
        except Exception as exc:
            error_detail = f"{type(exc).__name__}: {exc}"

    if not is_live:
        # Map real upcoming 1xBet matches into OddsPapi 5-level schema so matches are real & in range
        source_mode = "live_1xbet_in_oddspapi_v4_schema (No API Key)"
        endpoint_used, vzip_matches, _, filter_stats = fetch_live_vzip_bundle(
            mode=mode,
            sport_id=sport_id,
            count=count,
            domain="https://1xbet.com",
            proxy=None,
            timeout=8,
            start_dt=start_dt,
            end_dt=end_dt,
            method_id=METHOD_ID,
            method_name=METHOD_NAME,
            source_mode=source_mode,
        )
        if endpoint_used is not None and vzip_matches:
            raw_payloads = _matches_to_oddspapi_payloads(vzip_matches, oddspapi_sid)
            matches = [
                parse_oddspapi_payload(p, fetched_at=fetched_at, source_mode=source_mode)
                for p in raw_payloads
            ]
            is_live = True
        elif demo_mode:
            is_demo = True
            source_mode = DEMO_SOURCE_MODE
            seeds = get_sample_match_seeds(
                mode=mode,
                sport_id=sport_id,
                count=count,
                date_from=date_from,
                date_to=date_to,
                tz_offset_minutes=tz_offset_minutes,
            )
            demo_matches = [
                NormalizedMatch(
                    method_id=METHOD_ID,
                    method_name=METHOD_NAME,
                    source_mode=source_mode,
                    match_id=s["oddspapi_id"],
                    sport=s["sport_label"],
                    league=s["league"],
                    home_team=s["home"],
                    away_team=s["away"],
                    start_time_utc=s["start_iso"],
                    match_status=s["status"],
                    score=s["score"],
                    odds_home=s["home_odds"],
                    odds_draw=s["draw_odds"],
                    odds_away=s["away_odds"],
                    handicap_line=s["hdp_line"],
                    handicap_home=s["hdp_home"],
                    handicap_away=s["hdp_away"],
                    total_line=s["ou_line"],
                    odds_over=s["over_odds"],
                    odds_under=s["under_odds"],
                    market_active=s["active"],
                    fetched_at_utc=fetched_at,
                ).finalize_metrics()
                for s in seeds
            ]
            raw_payloads = _matches_to_oddspapi_payloads(demo_matches, oddspapi_sid)
            matches = demo_matches
        else:
            source_mode = UNAVAILABLE_SOURCE_MODE

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
        "date_range": {
            "from": date_from,
            "to": date_to,
            "window_utc": [start_dt.isoformat(), end_dt.isoformat()],
        },
        "source_mode": source_mode,
        "is_live_data": is_live,
        "is_demo": is_demo,
        "requests_used_this_run": requests_used,
        "quota_monthly_limit": 250,
        "latency_ms": elapsed_ms,
        "match_count": len(matches),
        "filter_stats": filter_stats,
        "error": error_detail,
        "fetched_at_utc": fetched_at,
        "matches": [m.to_dict() for m in matches],
        "raw_payload": raw_payloads,
    }


if __name__ == "__main__":
    result = fetch_oddspapi_odds(mode="prematch", sport_id=0, count=5)
    print(f"[{result['method_name']}]")
    print(
        f"Status: {result['source_mode']} | Matches: {result['match_count']} | Latency: {result['latency_ms']} ms"
    )
    for m in result["matches"][:5]:
        print(
            f" - [{m['sport']}] [{m['league']}] {m['home_team']} vs {m['away_team']} @ {m['start_time_local']} | "
            f"1X2: {m['odds_home']} / {m['odds_draw']} / {m['odds_away']}"
        )
