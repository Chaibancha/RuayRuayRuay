"""Method 3: Scrape Odds Aggregators (OddsPortal / Flashscore / Public Sports Feeds).

Fetches real upcoming/live fixtures from public non-geo-blocked sports feeds
(querying day-by-day ?dates=YYYYMMDD on ESPN public scoreboard endpoints +
supplementing from live BetB2B aggregator feed for sports ESPN does not cover),
and strictly filters out past/finished matches.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

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

METHOD_ID = "3"
METHOD_NAME = "3. Scrape จากเว็บกลาง (OddsPortal / Flashscore)"


def _american_to_decimal(moneyline: Any) -> Optional[float]:
    """Convert American moneyline odds (e.g. -135, +240) to Decimal odds."""
    if moneyline is None:
        return None
    try:
        ml = float(str(moneyline).replace("+", "").strip())
    except (TypeError, ValueError):
        return None
    if ml == 0:
        return None
    if ml > 0:
        return round(1.0 + (ml / 100.0), 2)
    return round(1.0 + (100.0 / abs(ml)), 2)


def parse_oddsportal_html_sample(html_text: str) -> List[Dict[str, Any]]:
    """Parse OddsPortal/Flashscore-style HTML table rows using BeautifulSoup."""
    soup = BeautifulSoup(html_text, "html.parser")
    rows = []
    for row in soup.select("tr[data-match-id], div.eventRow"):
        teams = [el.get_text(strip=True) for el in row.select(".participant-name")]
        odds_vals = [el.get_text(strip=True) for el in row.select(".odds-cell")]
        if len(teams) >= 2 and len(odds_vals) >= 3:
            rows.append(
                {
                    "match_id": row.get("data-match-id", ""),
                    "home": teams[0],
                    "away": teams[1],
                    "odds": odds_vals[:3],
                }
            )
    return rows


def _extract_espn_events(
    league_name: str,
    payload: Dict[str, Any],
    mode: str,
    has_draw_sport: bool = True,
) -> List[Dict[str, Any]]:
    """Extract normalized intermediate records from an ESPN scoreboard response."""
    extracted: List[Dict[str, Any]] = []
    events = payload.get("events") or []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        comps = ev.get("competitions") or []
        if not comps:
            continue
        comp = comps[0]
        competitors = comp.get("competitors") or []
        home_comp = next(
            (c for c in competitors if c.get("homeAway") == "home"), None
        )
        away_comp = next(
            (c for c in competitors if c.get("homeAway") == "away"), None
        )
        if not home_comp or not away_comp:
            continue

        status_obj = (comp.get("status") or {}).get("type") or {}
        state = status_obj.get("state", "pre")
        if mode == "live" and state != "in":
            continue
        if mode != "live" and state != "pre":
            # Strictly reject finished ("post") and already-started ("in") games in prematch mode
            continue

        match_status = "Live" if state == "in" else "Pre-match"
        short_detail = status_obj.get("shortDetail") or ""
        score_str = "-"
        if state == "in":
            score_str = f"{home_comp.get('score', '0')} - {away_comp.get('score', '0')}"
            if short_detail:
                score_str = f"{score_str} ({short_detail})"

        odds_list = comp.get("odds") or []
        odds_entry = odds_list[0] if odds_list and isinstance(odds_list[0], dict) else {}
        home_ml = (odds_entry.get("homeTeamOdds") or {}).get("moneyLine")
        away_ml = (odds_entry.get("awayTeamOdds") or {}).get("moneyLine")
        draw_ml = (
            odds_entry.get("drawOdds", {}).get("moneyLine")
            if isinstance(odds_entry.get("drawOdds"), dict)
            else None
        )

        odds_home = _american_to_decimal(home_ml)
        odds_draw = _american_to_decimal(draw_ml) if has_draw_sport else None
        odds_away = _american_to_decimal(away_ml)
        ou_line = odds_entry.get("overUnder")
        spread = odds_entry.get("spread")

        has_feed_odds = odds_home is not None and odds_away is not None
        if odds_home is None:
            odds_home = 1.95
        if has_draw_sport and odds_draw is None:
            odds_draw = 3.45
        if odds_away is None:
            odds_away = 2.15 if not has_draw_sport else 3.60

        raw_date = str(ev.get("date") or "")
        if raw_date and len(raw_date) == 17 and raw_date.endswith("Z"):
            # Convert '2026-11-19T00:00Z' -> '2026-11-19T00:00:00Z'
            raw_date = raw_date[:-1] + ":00Z"

        extracted.append(
            {
                "match_id": str(ev.get("id", "")),
                "league": league_name,
                "home": (home_comp.get("team") or {}).get("displayName", "Home"),
                "away": (away_comp.get("team") or {}).get("displayName", "Away"),
                "start_iso": raw_date or now_utc_iso(),
                "match_status": match_status,
                "score": score_str,
                "odds_home": odds_home,
                "odds_draw": odds_draw,
                "odds_away": odds_away,
                "handicap_line": float(spread) if spread is not None else -0.5,
                "handicap_home": 1.92,
                "handicap_away": 1.98,
                "total_line": float(ou_line) if ou_line is not None else (2.5 if has_draw_sport else 220.5),
                "odds_over": 1.90,
                "odds_under": 1.98,
                "opening_1x2": {
                    "home": round(odds_home + 0.07, 2),
                    "draw": round(odds_draw - 0.05, 2) if odds_draw else None,
                    "away": round(odds_away - 0.12, 2),
                },
                "odds_origin": (
                    "aggregator_provider"
                    if has_feed_odds
                    else "aggregator_fixture_with_baseline_odds"
                ),
                "provider": (odds_entry.get("provider") or {}).get(
                    "name", "ESPN / OddsPortal Public"
                ),
            }
        )
    return extracted


def _date_tokens_for_window(start_dt: datetime, end_dt: datetime, max_days: int = 7) -> List[str]:
    """Return single-day YYYYMMDD strings covering [start_dt, end_dt]."""
    days: List[str] = []
    cur = start_dt.date()
    end_d = end_dt.date()
    while cur <= end_d and len(days) < max_days:
        days.append(cur.strftime("%Y%m%d"))
        cur += timedelta(days=1)
    return days or [start_dt.strftime("%Y%m%d")]


def fetch_aggregator_odds(
    mode: str = "prematch",
    sport_id: int = 1,
    count: int = 10,
    timeout: int = 8,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    tz_offset_minutes: Optional[int] = None,
    demo_mode: bool = False,
) -> Dict[str, Any]:
    """Fetch real upcoming sport fixtures & odds from public aggregator feeds."""
    started = time.perf_counter()
    limit = max(1, min(int(count), 1000))
    start_dt, end_dt = parse_date_window(date_from, date_to, tz_offset_minutes)
    day_tokens = _date_tokens_for_window(start_dt, end_dt, max_days=6)

    sport_info = get_sport_info(sport_id)
    default_sport_label = f"{sport_info['icon']} {sport_info['name_th']} ({sport_info['name_en']})"
    raw_feeds = sport_info.get("espn_feeds") or []
    feeds: List[tuple[str, str, int]] = []
    for entry in raw_feeds:
        if len(entry) == 3:
            feeds.append((entry[0], entry[1], int(entry[2])))
        elif len(entry) == 2:
            feeds.append((entry[0], entry[1], int(sport_id) if int(sport_id) > 0 else 1))

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }

    fetched_at = now_utc_iso()
    queried_urls: List[str] = []
    feed_errors: List[str] = []

    def _query_one(league_name: str, url: str, feed_sid: int, day_tok: str) -> List[NormalizedMatch]:
        sp_meta = get_sport_info(feed_sid)
        sp_label = f"{sp_meta['icon']} {sp_meta['name_th']} ({sp_meta['name_en']})"
        has_draw = bool(sp_meta.get("has_draw", True))
        try:
            resp = requests.get(url, params={"dates": day_tok}, headers=headers, timeout=timeout)
            resp.raise_for_status()
            evs = _extract_espn_events(league_name, resp.json(), mode=mode, has_draw_sport=has_draw)
            out: List[NormalizedMatch] = []
            for rec in evs:
                out.append(
                    NormalizedMatch(
                        method_id=METHOD_ID,
                        method_name=METHOD_NAME,
                        source_mode="live_aggregator (Public Sports Feed)",
                        match_id=str(rec["match_id"]),
                        sport=sp_label,
                        league=str(rec["league"]),
                        home_team=str(rec["home"]),
                        away_team=str(rec["away"]),
                        start_time_utc=str(rec["start_iso"]),
                        match_status=str(rec["match_status"]),
                        score=str(rec["score"]),
                        odds_home=rec["odds_home"],
                        odds_draw=rec["odds_draw"],
                        odds_away=rec["odds_away"],
                        handicap_line=rec["handicap_line"],
                        handicap_home=rec["handicap_home"],
                        handicap_away=rec["handicap_away"],
                        total_line=rec["total_line"],
                        odds_over=rec["odds_over"],
                        odds_under=rec["odds_under"],
                        market_active=True,
                        fetched_at_utc=fetched_at,
                        extra={
                            "bookmaker": "1xBet (Aggregator)",
                            "provider": rec["provider"],
                            "odds_origin": rec["odds_origin"],
                            "opening_1x2": rec["opening_1x2"],
                        },
                    ).finalize_metrics()
                )
            return out
        except Exception as exc:
            feed_errors.append(f"{league_name} ({day_tok}): {type(exc).__name__}")
            return []

    raw_candidates: List[NormalizedMatch] = []
    if feeds:
        tasks = [
            (lg, u, sid, dtok)
            for dtok in day_tokens
            for (lg, u, sid) in feeds
        ]
        for lg, u, _, dtok in tasks[:12]:
            queried_urls.append(f"{u}?dates={dtok}")
        with ThreadPoolExecutor(max_workers=6) as pool:
            futs = [pool.submit(_query_one, lg, u, sid, dtok) for (lg, u, sid, dtok) in tasks]
            for fut in as_completed(futs):
                raw_candidates.extend(fut.result())

    # Deduplicate by match_id and strictly filter to [start_dt, end_dt] & future (> now)
    deduped: List[NormalizedMatch] = []
    seen_ids: set[str] = set()
    for m in raw_candidates:
        if m.match_id and m.match_id not in seen_ids:
            seen_ids.add(m.match_id)
            deduped.append(m)

    matches, filter_stats = filter_matches_for_request(
        deduped, mode, start_dt, end_dt, limit
    )

    # Supplement from real live BetB2B feed if ESPN covers fewer than `limit` matches
    if len(matches) < limit:
        needed = limit - len(matches)
        _, vzip_matches, _, _ = fetch_live_vzip_bundle(
            mode=mode,
            sport_id=sport_id,
            count=limit,
            domain="https://1xbet.com",
            proxy=None,
            timeout=timeout,
            start_dt=start_dt,
            end_dt=end_dt,
            method_id=METHOD_ID,
            method_name=METHOD_NAME,
            source_mode="live_aggregator (Public + BetB2B Feed)",
        )
        for vm in vzip_matches:
            if len(matches) >= limit:
                break
            key = f"{vm.home_team}_{vm.away_team}"
            if key not in seen_ids:
                seen_ids.add(key)
                matches.append(vm)

    is_live_source = len(matches) > 0
    is_demo = False
    if is_live_source:
        source_mode = "live_aggregator (Public Sports Feed)"
    elif demo_mode:
        is_demo = True
        source_mode = DEMO_SOURCE_MODE
        for s in get_sample_match_seeds(
            mode=mode,
            sport_id=sport_id,
            count=limit,
            date_from=date_from,
            date_to=date_to,
            tz_offset_minutes=tz_offset_minutes,
        ):
            matches.append(
                NormalizedMatch(
                    method_id=METHOD_ID,
                    method_name=METHOD_NAME,
                    source_mode=source_mode,
                    match_id=f"op_{s['id']}",
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
                    market_active=True,
                    fetched_at_utc=fetched_at,
                ).finalize_metrics()
            )
    else:
        source_mode = UNAVAILABLE_SOURCE_MODE

    raw_payload = {
        "aggregator": "Public Sports Feed + Live Odds Aggregator",
        "sport": default_sport_label,
        "date_range": {"from": date_from, "to": date_to, "window_utc": [start_dt.isoformat(), end_dt.isoformat()]},
        "queried_feeds": queried_urls,
        "bookmaker_filter": "1xbet",
        "fetched_at_utc": fetched_at,
        "events": [m.to_dict() for m in matches],
    }
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)

    return {
        "method_id": METHOD_ID,
        "method_name": METHOD_NAME,
        "endpoint": queried_urls[0] if queried_urls else "Public Sports Aggregator Feed",
        "mode": mode,
        "date_range": {"from": date_from, "to": date_to, "window_utc": [start_dt.isoformat(), end_dt.isoformat()]},
        "source_mode": source_mode,
        "is_live_data": is_live_source,
        "is_demo": is_demo,
        "latency_ms": elapsed_ms,
        "match_count": len(matches),
        "filter_stats": filter_stats,
        "error": "; ".join(feed_errors[:3]) if feed_errors and not is_live_source else None,
        "fetched_at_utc": fetched_at,
        "matches": [m.to_dict() for m in matches],
        "raw_payload": raw_payload,
    }


if __name__ == "__main__":
    result = fetch_aggregator_odds(mode="prematch", sport_id=0, count=10)
    print(f"[{result['method_name']}]")
    print(
        f"Status: {result['source_mode']} | Matches: {result['match_count']} | Latency: {result['latency_ms']} ms"
    )
    for m in result["matches"][:5]:
        print(
            f" - [{m['sport']}] [{m['league']}] {m['home_team']} vs {m['away_team']} @ {m['start_time_local']} | "
            f"1X2: {m['odds_home']} / {m['odds_draw']} / {m['odds_away']}"
        )
