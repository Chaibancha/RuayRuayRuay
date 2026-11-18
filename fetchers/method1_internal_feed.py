"""Method 1: Direct Internal JSON Feed (1xBet LineFeed / LiveFeed Get1x2_VZip).

Queries 1xBet's internal frontend JSON endpoints directly and decodes the short
keys ("Value", "I", "L", "S", "O1", "O2", "SC", "E" -> "G", "T", "C", "P").
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from fetchers.schema import (
        NormalizedMatch,
        build_simulated_vzip_payload,
        get_sport_info,
        now_utc_iso,
        unix_to_iso,
    )
else:
    from .schema import (
        NormalizedMatch,
        build_simulated_vzip_payload,
        get_sport_info,
        now_utc_iso,
        unix_to_iso,
    )

METHOD_ID = "1"
METHOD_NAME = "1. ยิง Internal Feed ตรง (LineFeed / LiveFeed)"
DEFAULT_DOMAIN = "https://1xbet.com"


def decode_vzip_payload(
    raw_payload: Dict[str, Any],
    mode: str = "prematch",
    sport_id: int = 1,
    method_id: str = METHOD_ID,
    method_name: str = METHOD_NAME,
    source_mode: str = "live",
    fetched_at: Optional[str] = None,
) -> List[NormalizedMatch]:
    """Decode 1xBet Get1x2_VZip JSON payload into NormalizedMatch objects."""
    matches_raw = raw_payload.get("Value") or []
    if not isinstance(matches_raw, list):
        return []

    ts_now = fetched_at or now_utc_iso()
    normalized: List[NormalizedMatch] = []

    for item in matches_raw:
        if not isinstance(item, dict):
            continue

        item_sid = item.get("SI", sport_id)
        try:
            item_sid_int = int(item_sid)
        except (TypeError, ValueError):
            item_sid_int = 1
        if item_sid_int == 0:
            item_sid_int = 1
        sport_info = get_sport_info(item_sid_int)
        sport_label = f"{sport_info['icon']} {sport_info['name_th']} ({sport_info['name_en']})"

        match_id = str(item.get("I", ""))
        league = str(item.get("L") or "Unknown League")
        home = str(item.get("O1") or "Home")
        away = str(item.get("O2") or "Away")
        start_iso = unix_to_iso(item.get("S"))

        sc_obj = item.get("SC") or {}
        score_str = "-"
        if isinstance(sc_obj, dict) and sc_obj:
            cps = sc_obj.get("CPS")
            fs = sc_obj.get("FS") or {}
            if cps:
                score_str = str(cps)
            elif isinstance(fs, dict) and ("S1" in fs or "S2" in fs):
                score_str = f"{fs.get('S1', 0)} - {fs.get('S2', 0)}"

        odds_1x2: Dict[int, float] = {}
        market_active = True
        hdp_line: Optional[float] = None
        hdp_home: Optional[float] = None
        hdp_away: Optional[float] = None
        ou_line: Optional[float] = None
        odds_over: Optional[float] = None
        odds_under: Optional[float] = None

        for ev in item.get("E") or []:
            if not isinstance(ev, dict):
                continue
            group = ev.get("G")
            t_code = ev.get("T")
            price = ev.get("C")
            param = ev.get("P")
            blocked = bool(ev.get("B", False))

            if price is None:
                continue
            try:
                price_f = float(price)
            except (TypeError, ValueError):
                continue

            if group == 1 and t_code in (1, 2, 3):
                odds_1x2[int(t_code)] = price_f
                if blocked:
                    market_active = False
            elif group == 2 and t_code in (7, 8):
                if t_code == 7:
                    hdp_home = price_f
                    if param is not None:
                        hdp_line = float(param)
                elif t_code == 8:
                    hdp_away = price_f
            elif group == 17 and t_code in (9, 10):
                if param is not None:
                    ou_line = float(param)
                if t_code == 9:
                    odds_over = price_f
                elif t_code == 10:
                    odds_under = price_f

        match = NormalizedMatch(
            method_id=method_id,
            method_name=method_name,
            source_mode=source_mode,
            match_id=match_id,
            sport=sport_label,
            league=league,
            home_team=home,
            away_team=away,
            start_time_utc=start_iso,
            match_status="Live" if (mode == "live" or sc_obj) else "Pre-match",
            score=score_str,
            odds_home=odds_1x2.get(1),
            odds_draw=odds_1x2.get(2),
            odds_away=odds_1x2.get(3),
            handicap_line=hdp_line,
            handicap_home=hdp_home,
            handicap_away=hdp_away,
            total_line=ou_line,
            odds_over=odds_over,
            odds_under=odds_under,
            market_active=market_active,
            fetched_at_utc=ts_now,
            extra={
                "vzip_events_count": len(item.get("E") or []),
                "raw_keys": sorted(list(item.keys())),
            },
        ).finalize_metrics()
        normalized.append(match)

    return normalized


def fetch_internal_feed(
    mode: str = "prematch",
    sport_id: int = 1,
    count: int = 10,
    domain: str = DEFAULT_DOMAIN,
    proxy: Optional[str] = None,
    timeout: int = 8,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch 1xBet LineFeed or LiveFeed JSON directly with safe fallback if blocked."""
    started = time.perf_counter()
    clean_domain = (domain or DEFAULT_DOMAIN).strip().rstrip("/")
    if not clean_domain.startswith(("http://", "https://")):
        clean_domain = f"https://{clean_domain}"

    feed_path = (
        "/LiveFeed/Get1x2_VZip" if mode == "live" else "/LineFeed/Get1x2_VZip"
    )
    url = f"{clean_domain}{feed_path}"
    params: Dict[str, Any] = {
        "count": int(count),
        "lng": "en",
        "mode": 4,
        "country": 1,
        "getEmpty": "true",
    }
    if int(sport_id) > 0:
        params["sports"] = int(sport_id)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9,th;q=0.8",
        "Referer": f"{clean_domain}/en/{'live' if mode == 'live' else 'line'}/football",
    }
    proxies = {"http": proxy, "https": proxy} if proxy and proxy.strip() else None

    error_detail: Optional[str] = None
    raw_payload: Optional[Dict[str, Any]] = None
    source_mode = "live"

    try:
        resp = requests.get(
            url,
            params=params,
            headers=headers,
            proxies=proxies,
            timeout=timeout,
        )
        resp.raise_for_status()
        parsed = resp.json()
        if isinstance(parsed, dict) and isinstance(parsed.get("Value"), list):
            raw_payload = parsed
        else:
            error_detail = "Unexpected JSON schema from endpoint (missing 'Value' list)."
    except Exception as exc:
        error_detail = f"{type(exc).__name__}: {exc}"

    if raw_payload is None:
        source_mode = "simulated_fallback (ISP/WAF blocked)"
        raw_payload = build_simulated_vzip_payload(
            mode=mode,
            count=count,
            sport_id=sport_id,
            date_from=date_from,
            date_to=date_to,
        )

    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    fetched_at = now_utc_iso()
    matches = decode_vzip_payload(
        raw_payload=raw_payload,
        mode=mode,
        sport_id=sport_id,
        method_id=METHOD_ID,
        method_name=METHOD_NAME,
        source_mode=source_mode,
        fetched_at=fetched_at,
    )

    return {
        "method_id": METHOD_ID,
        "method_name": METHOD_NAME,
        "endpoint": url,
        "mode": mode,
        "date_range": {"from": date_from, "to": date_to},
        "source_mode": source_mode,
        "is_live_data": source_mode == "live",
        "latency_ms": elapsed_ms,
        "match_count": len(matches),
        "error": error_detail,
        "fetched_at_utc": fetched_at,
        "matches": [m.to_dict() for m in matches],
        "raw_payload": raw_payload,
    }


if __name__ == "__main__":
    result = fetch_internal_feed(mode="prematch", count=10)
    print(f"[{result['method_name']}]")
    print(
        f"Status: {result['source_mode']} | Matches: {result['match_count']} | Latency: {result['latency_ms']} ms"
    )
    if result["error"]:
        print(f"Notice: {result['error']}")
    for m in result["matches"][:5]:
        print(
            f" - [{m['league']}] {m['home_team']} vs {m['away_team']} | "
            f"1X2: {m['odds_home']} / {m['odds_draw']} / {m['odds_away']}"
        )
    if "--json" in sys.argv:
        print(json.dumps(result["matches"], ensure_ascii=False, indent=2))
