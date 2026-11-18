"""Method 1: Direct Internal JSON Feed (1xBet / BetB2B LineFeed & LiveFeed Get1x2_VZip).

Queries 1xBet/BetB2B internal frontend JSON endpoints directly using Chrome TLS
impersonation (`curl_cffi`) to bypass WAF/ISP blocks, decodes the short keys
("Value", "I", "SI", "SN", "L", "S", "O1", "O2", "SC", "E" -> "G", "T", "C", "P"),
and strictly filters to real upcoming matches within the requested date range.
"""

from __future__ import annotations

from datetime import datetime
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests as std_requests

try:
    from curl_cffi import requests as cffi_requests  # type: ignore
except ImportError:
    cffi_requests = None

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from fetchers.schema import (
        DEMO_SOURCE_MODE,
        SPORTS_BY_ID,
        UNAVAILABLE_SOURCE_MODE,
        NormalizedMatch,
        build_simulated_vzip_payload,
        filter_matches_for_request,
        now_utc_iso,
        parse_date_window,
        unix_to_iso,
    )
else:
    from .schema import (
        DEMO_SOURCE_MODE,
        SPORTS_BY_ID,
        UNAVAILABLE_SOURCE_MODE,
        NormalizedMatch,
        build_simulated_vzip_payload,
        filter_matches_for_request,
        now_utc_iso,
        parse_date_window,
        unix_to_iso,
    )

METHOD_ID = "1"
METHOD_NAME = "1. ยิง Internal Feed ตรง (LineFeed / LiveFeed)"
DEFAULT_DOMAIN = "https://1xbet.com"
WORKING_BETB2B_API_BASES = [
    "https://888starz.bet/service-api",
]
ALL_SPORTS_QUERY_IDS = [1, 3, 4, 6, 2, 40, 16, 10, 9, 56, 5, 13, 19, 29, 8, 7, 66, 21, 18, 24]

_SESSION_LOCK = threading.Lock()
_CFFI_SESSION: Any = None
_VZIP_CACHE: Dict[tuple[str, str, int], tuple[float, List[Dict[str, Any]]]] = {}
_VZIP_CACHE_TTL = 300.0
_DISK_CACHE_PATH = Path(__file__).resolve().parent.parent / "cache" / "live_vzip_snapshot.json"


def _load_disk_cache() -> Dict[str, Any]:
    if _DISK_CACHE_PATH.exists():
        try:
            return json.loads(_DISK_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_disk_cache(data: Dict[str, Any]) -> None:
    try:
        _DISK_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _DISK_CACHE_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

_SUBMARKET_KEYWORDS = (
    "home",
    "away",
    "1st players",
    "2nd players",
    "team 1",
    "team 2",
    "player 1",
    "player 2",
    "hosts",
    "guests",
)


def _is_submarket_item(item: Dict[str, Any]) -> bool:
    """Return True if a VZip item is a prop/sub-game (e.g. 'Home vs Away', corners, stats)."""
    if item.get("TG") or item.get("DI"):
        return True
    o1 = str(item.get("O1") or "").strip().lower()
    o2 = str(item.get("O2") or "").strip().lower()
    if not o1 or not o2:
        return True
    for kw in _SUBMARKET_KEYWORDS:
        if o1 == kw or o2 == kw or o1.startswith(kw + " (") or o2.startswith(kw + " ("):
            return True
    return False


def _sport_label_for(item: Dict[str, Any], fallback_sid: int) -> str:
    """Resolve a human sport label from the item's own SI/SN keys."""
    raw_sid = item.get("SI", fallback_sid)
    try:
        sid = int(raw_sid)
    except (TypeError, ValueError):
        sid = -1
    if sid in SPORTS_BY_ID and sid != 0:
        info = SPORTS_BY_ID[sid]
        return f"{info['icon']} {info['name_th']} ({info['name_en']})"
    if item.get("SN"):
        return str(item["SN"])
    return f"Sport #{raw_sid}"


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
    seen_ids: set[str] = set()

    for item in matches_raw:
        if not isinstance(item, dict) or _is_submarket_item(item):
            continue

        match_id = str(item.get("I", ""))
        if not match_id or match_id in seen_ids:
            continue
        seen_ids.add(match_id)

        sport_label = _sport_label_for(item, sport_id)
        league = str(item.get("L") or "Unknown League")
        home = str(item.get("O1") or "Home")
        away = str(item.get("O2") or "Away")
        start_iso = unix_to_iso(item.get("S"))

        sc_obj = item.get("SC") or {}
        score_str = "-"
        if mode == "live" and isinstance(sc_obj, dict) and sc_obj:
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
            elif group == 101 and t_code in (401, 402):
                # Basketball / American sports Moneyline (Team Wins incl. OT)
                mapped = 1 if t_code == 401 else 3
                odds_1x2.setdefault(mapped, price_f)
                if blocked:
                    market_active = False
            elif group == 2766 and t_code in (3653, 3654, 3655):
                # Basketball 1X2 Regular Time fallback
                mapped = 1 if t_code == 3653 else (2 if t_code == 3654 else 3)
                odds_1x2.setdefault(mapped, price_f)
            elif group == 2 and t_code in (7, 8):
                if t_code == 7:
                    hdp_home = price_f
                    if param is not None:
                        hdp_line = float(param)
                else:
                    hdp_away = price_f
            elif group == 17 and t_code in (9, 10):
                if param is not None:
                    ou_line = float(param)
                if t_code == 9:
                    odds_over = price_f
                else:
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
            match_status="Live" if mode == "live" else "Pre-match",
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
            extra={"vzip_events_count": len(item.get("E") or [])},
        ).finalize_metrics()
        normalized.append(match)

    return normalized


def _candidate_api_bases(domain: str) -> List[str]:
    """Return ordered list of 1xBet/BetB2B base URLs to try."""
    clean = (domain or DEFAULT_DOMAIN).strip().rstrip("/")
    if not clean.startswith(("http://", "https://")):
        clean = f"https://{clean}"

    bases: List[str] = []
    is_default_1xbet = clean.lower() in ("https://1xbet.com", "http://1xbet.com", "https://www.1xbet.com")
    if not is_default_1xbet:
        if clean.endswith("/service-api"):
            bases.append(clean)
        else:
            bases.append(f"{clean}/service-api")
            bases.append(clean)

    for mirror in WORKING_BETB2B_API_BASES:
        if mirror not in bases:
            bases.append(mirror)

    if is_default_1xbet:
        bases.append("https://1xbet.com")
    return bases


def _is_disk_cache_fresh(max_age_sec: float = 900.0) -> bool:
    if not _DISK_CACHE_PATH.exists():
        return False
    try:
        return (time.time() - _DISK_CACHE_PATH.stat().st_mtime) < max_age_sec
    except Exception:
        return False


def _http_get_json(
    url: str,
    params: Dict[str, Any],
    proxy: Optional[str] = None,
    timeout: int = 4,
) -> Optional[Dict[str, Any]]:
    """Fetch JSON from a 1xBet/BetB2B endpoint reusing warm Chrome TLS session."""
    global _CFFI_SESSION
    proxies = {"http": proxy, "https": proxy} if proxy and proxy.strip() else None
    req_headers = {"Accept": "application/json, text/plain, */*"}

    for attempt in range(2):
        try:
            with _SESSION_LOCK:
                if cffi_requests is not None:
                    if _CFFI_SESSION is None:
                        _CFFI_SESSION = cffi_requests.Session(impersonate="chrome")
                    resp = _CFFI_SESSION.get(
                        url,
                        params=params,
                        headers=req_headers,
                        proxies=proxies,
                        timeout=min(timeout, 4),
                    )
                else:
                    resp = std_requests.get(
                        url,
                        params=params,
                        headers=req_headers,
                        proxies=proxies,
                        timeout=min(timeout, 4),
                    )
            if resp.status_code == 200 and "json" in (resp.headers.get("Content-Type") or "").lower():
                data = resp.json()
                if isinstance(data, dict) and isinstance(data.get("Value"), list):
                    return data
        except Exception:
            with _SESSION_LOCK:
                _CFFI_SESSION = None
            time.sleep(0.1)
    return None


def fetch_live_vzip_bundle(
    mode: str,
    sport_id: int,
    count: int,
    domain: str,
    proxy: Optional[str],
    timeout: int,
    start_dt: datetime,
    end_dt: datetime,
    method_id: str = METHOD_ID,
    method_name: str = METHOD_NAME,
    source_mode: str = "live",
) -> tuple[Optional[str], List[NormalizedMatch], List[Dict[str, Any]], Dict[str, int]]:
    """Fetch and filter real VZip items across one sport or all sports."""
    feed_path = "/LiveFeed/Get1x2_VZip" if mode == "live" else "/LineFeed/Get1x2_VZip"
    bases = _candidate_api_bases(domain)
    active_base: Optional[str] = None
    disk_snap = _load_disk_cache()
    disk_fresh = _is_disk_cache_fresh(900.0)
    disk_dirty = False

    def _fetch_sport(sid: int, base_url: str) -> List[Dict[str, Any]]:
        nonlocal disk_dirty
        cache_key = (base_url, feed_path, int(sid))
        now_m = time.monotonic()
        cached = _VZIP_CACHE.get(cache_key)
        if cached and (now_m - cached[0]) < _VZIP_CACHE_TTL:
            return cached[1]

        snap_vals = disk_snap.get(f"{mode}:{sid}")
        if disk_fresh and isinstance(snap_vals, list) and snap_vals:
            _VZIP_CACHE[cache_key] = (now_m, snap_vals)
            return snap_vals

        p: Dict[str, Any] = {}
        if sid > 0:
            p["sports"] = sid
        p["count"] = 250
        p["lng"] = "en"
        p["mode"] = 4
        res = _http_get_json(f"{base_url}{feed_path}", p, proxy=proxy, timeout=timeout)
        if res and isinstance(res.get("Value"), list) and res["Value"]:
            vals = res["Value"]
            _VZIP_CACHE[cache_key] = (now_m, vals)
            disk_snap[f"{mode}:{sid}"] = vals
            disk_dirty = True
            return vals

        if isinstance(snap_vals, list) and snap_vals:
            _VZIP_CACHE[cache_key] = (now_m, snap_vals)
            return snap_vals
        return []

    probe_sid = int(sport_id) if int(sport_id) > 0 else 1
    first_batch: List[Dict[str, Any]] = []
    for candidate in bases:
        vals = _fetch_sport(probe_sid, candidate)
        if vals:
            active_base = candidate
            first_batch = vals
            break

    if not active_base:
        if disk_dirty:
            _save_disk_cache(disk_snap)
        return None, [], [], {}

    fetched_at = now_utc_iso()
    target_count = max(1, min(int(count), 1000))

    if int(sport_id) == 0:
        per_sport_matches: Dict[int, List[NormalizedMatch]] = {}
        raw_values_all: List[Dict[str, Any]] = list(first_batch)

        dec1 = decode_vzip_payload(
            {"Value": first_batch},
            mode=mode,
            sport_id=1,
            method_id=method_id,
            method_name=method_name,
            source_mode=source_mode,
            fetched_at=fetched_at,
        )
        filt1, stats_total = filter_matches_for_request(
            dec1, mode, start_dt, end_dt, target_count
        )
        if filt1:
            per_sport_matches[1] = filt1

        for sid in ALL_SPORTS_QUERY_IDS:
            if sid == 1:
                continue
            vals = _fetch_sport(sid, active_base)
            if not vals:
                continue
            raw_values_all.extend(vals)
            dec = decode_vzip_payload(
                {"Value": vals},
                mode=mode,
                sport_id=sid,
                method_id=method_id,
                method_name=method_name,
                source_mode=source_mode,
                fetched_at=fetched_at,
            )
            filt, st = filter_matches_for_request(
                dec, mode, start_dt, end_dt, target_count
            )
            for k, v in st.items():
                stats_total[k] = stats_total.get(k, 0) + v
            if filt:
                per_sport_matches[sid] = filt

        if disk_dirty:
            _save_disk_cache(disk_snap)

        interleaved: List[NormalizedMatch] = []
        ordered_sids = [s for s in ALL_SPORTS_QUERY_IDS if s in per_sport_matches]
        if ordered_sids:
            max_len = max(len(per_sport_matches[s]) for s in ordered_sids)
            for idx in range(max_len):
                for s in ordered_sids:
                    lst = per_sport_matches[s]
                    if idx < len(lst) and len(interleaved) < target_count:
                        interleaved.append(lst[idx])

        selected_ids = {m.match_id for m in interleaved}
        raw_selected = [v for v in raw_values_all if str(v.get("I", "")) in selected_ids]
        return f"{active_base}{feed_path}", interleaved, raw_selected, stats_total

    # Single sport (sport_id > 0)
    if disk_dirty:
        _save_disk_cache(disk_snap)
    raw_values = list(first_batch)
    decoded = decode_vzip_payload(
        {"Value": raw_values},
        mode=mode,
        sport_id=sport_id,
        method_id=method_id,
        method_name=method_name,
        source_mode=source_mode,
        fetched_at=fetched_at,
    )
    filtered, stats = filter_matches_for_request(
        decoded, mode, start_dt, end_dt, target_count
    )
    selected_ids = {m.match_id for m in filtered}
    raw_selected = [v for v in raw_values if str(v.get("I", "")) in selected_ids]
    return f"{active_base}{feed_path}", filtered, raw_selected, stats


def fetch_internal_feed(
    mode: str = "prematch",
    sport_id: int = 1,
    count: int = 10,
    domain: str = DEFAULT_DOMAIN,
    proxy: Optional[str] = None,
    timeout: int = 8,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    tz_offset_minutes: Optional[int] = None,
    demo_mode: bool = False,
) -> Dict[str, Any]:
    """Fetch 1xBet/BetB2B LineFeed/LiveFeed JSON with real date-range filtering."""
    started = time.perf_counter()
    start_dt, end_dt = parse_date_window(date_from, date_to, tz_offset_minutes)
    fetched_at = now_utc_iso()

    endpoint_used, matches, raw_values, filter_stats = fetch_live_vzip_bundle(
        mode=mode,
        sport_id=sport_id,
        count=count,
        domain=domain,
        proxy=proxy,
        timeout=timeout,
        start_dt=start_dt,
        end_dt=end_dt,
        method_id=METHOD_ID,
        method_name=METHOD_NAME,
        source_mode="live (1xBet/BetB2B Feed)",
    )

    error_detail: Optional[str] = None
    is_demo = False

    if endpoint_used is not None:
        source_mode = "live (1xBet/BetB2B Feed)"
        raw_payload: Dict[str, Any] = {
            "Error": "",
            "ErrorCode": 0,
            "Guid": "",
            "Id": 0,
            "Success": True,
            "Value": raw_values,
        }
        if not matches:
            error_detail = (
                f"เชื่อมต่อสำเร็จ แต่ไม่พบคู่แข่งขันที่ยังไม่เริ่มในช่วงวันที่ {date_from} ถึง {date_to}"
            )
    elif demo_mode:
        is_demo = True
        source_mode = DEMO_SOURCE_MODE
        raw_payload = build_simulated_vzip_payload(
            mode=mode,
            count=count,
            sport_id=sport_id,
            date_from=date_from,
            date_to=date_to,
            tz_offset_minutes=tz_offset_minutes,
        )
        matches = decode_vzip_payload(
            raw_payload,
            mode=mode,
            sport_id=sport_id,
            source_mode=source_mode,
            fetched_at=fetched_at,
        )
        endpoint_used = f"{domain}/LineFeed/Get1x2_VZip"
    else:
        source_mode = UNAVAILABLE_SOURCE_MODE
        matches = []
        endpoint_used = f"{domain}/LineFeed/Get1x2_VZip"
        error_detail = "ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์ 1xBet/Mirror ได้ — ระบบไม่สร้างข้อมูลจำลองแทน"
        raw_payload = {"Success": False, "Error": error_detail, "Value": []}

    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    return {
        "method_id": METHOD_ID,
        "method_name": METHOD_NAME,
        "endpoint": endpoint_used,
        "mode": mode,
        "date_range": {
            "from": date_from,
            "to": date_to,
            "window_utc": [start_dt.isoformat(), end_dt.isoformat()],
        },
        "source_mode": source_mode,
        "is_live_data": endpoint_used is not None and not is_demo,
        "is_demo": is_demo,
        "latency_ms": elapsed_ms,
        "match_count": len(matches),
        "filter_stats": filter_stats,
        "error": error_detail,
        "fetched_at_utc": fetched_at,
        "matches": [m.to_dict() for m in matches],
        "raw_payload": raw_payload,
    }


if __name__ == "__main__":
    result = fetch_internal_feed(mode="prematch", sport_id=0, count=10)
    print(f"[{result['method_name']}]")
    print(
        f"Status: {result['source_mode']} | Matches: {result['match_count']} | Latency: {result['latency_ms']} ms"
    )
    if result["error"]:
        print(f"Notice: {result['error']}")
    for m in result["matches"][:10]:
        print(
            f" - [{m['sport']}] [{m['league']}] {m['home_team']} vs {m['away_team']} @ {m['start_time_local']} | "
            f"1X2: {m['odds_home']} / {m['odds_draw']} / {m['odds_away']}"
        )
    if "--json" in sys.argv:
        print(json.dumps(result["matches"], ensure_ascii=False, indent=2))
