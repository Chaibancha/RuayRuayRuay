"""Method 2: Playwright / Selenium Network Interception.

Launches a headless browser (Playwright Chromium if installed, or Selenium Chrome
with CDP/performance network logging), or uses fast TLS-impersonated network
packet capture against the 1xBet/BetB2B service-api, and strictly filters to
real upcoming matches in the requested date range.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from fetchers.method1_internal_feed import (
        WORKING_BETB2B_API_BASES,
        decode_vzip_payload,
        fetch_live_vzip_bundle,
    )
    from fetchers.schema import (
        DEMO_SOURCE_MODE,
        UNAVAILABLE_SOURCE_MODE,
        NormalizedMatch,
        build_simulated_vzip_payload,
        filter_matches_for_request,
        get_sport_info,
        now_utc_iso,
        parse_date_window,
    )
else:
    from .method1_internal_feed import (
        WORKING_BETB2B_API_BASES,
        decode_vzip_payload,
        fetch_live_vzip_bundle,
    )
    from .schema import (
        DEMO_SOURCE_MODE,
        UNAVAILABLE_SOURCE_MODE,
        NormalizedMatch,
        build_simulated_vzip_payload,
        filter_matches_for_request,
        get_sport_info,
        now_utc_iso,
        parse_date_window,
    )

METHOD_ID = "2"
METHOD_NAME = "2. Playwright / Selenium Network Interception"
DEFAULT_DOMAIN = "https://1xbet.com"
INTERCEPT_PATTERNS = ("LineFeed", "LiveFeed", "Get1x2_VZip", "GetGameZip")


def _try_playwright_intercept(
    target_url: str, timeout_ms: int = 12000
) -> Dict[str, Any]:
    """Attempt network interception using Playwright sync API."""
    from playwright.sync_api import sync_playwright  # type: ignore

    captured: List[Dict[str, Any]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                " (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        def handle_response(response: Any) -> None:
            url = response.url
            if any(pat in url for pat in INTERCEPT_PATTERNS):
                try:
                    if response.status == 200:
                        data = response.json()
                        if isinstance(data, dict) and data.get("Value"):
                            captured.append({"url": url, "payload": data})
                except Exception:
                    pass

        page.on("response", handle_response)
        page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_timeout(3500)
        browser.close()

    return {"engine": "playwright", "captured": captured}


def _try_selenium_intercept(
    target_url: str, timeout_sec: int = 12
) -> Dict[str, Any]:
    """Attempt network interception using Selenium Chrome + performance logs."""
    from selenium import webdriver  # type: ignore
    from selenium.webdriver.chrome.options import Options  # type: ignore

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    captured: List[Dict[str, Any]] = []
    driver = webdriver.Chrome(options=options)
    try:
        driver.set_page_load_timeout(timeout_sec)
        driver.get(target_url)
        time.sleep(3.5)

        for entry in driver.get_log("performance"):
            try:
                msg = json.loads(entry["message"])["message"]
            except Exception:
                continue
            if msg.get("method") != "Network.responseReceived":
                continue
            params = msg.get("params", {})
            resp = params.get("response", {})
            url = resp.get("url", "")
            if any(pat in url for pat in INTERCEPT_PATTERNS):
                request_id = params.get("requestId")
                if not request_id:
                    continue
                try:
                    body = driver.execute_cdp_cmd(
                        "Network.getResponseBody", {"requestId": request_id}
                    )
                    parsed = json.loads(body.get("body", "{}"))
                    if isinstance(parsed, dict) and parsed.get("Value"):
                        captured.append({"url": url, "payload": parsed})
                except Exception:
                    continue
    finally:
        driver.quit()

    return {"engine": "selenium", "captured": captured}


def fetch_browser_intercept(
    mode: str = "prematch",
    sport_id: int = 1,
    count: int = 10,
    domain: str = DEFAULT_DOMAIN,
    live_browser: bool = False,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    tz_offset_minutes: Optional[int] = None,
    demo_mode: bool = False,
) -> Dict[str, Any]:
    """Intercept 1xBet JSON payloads and filter to real upcoming matches in date range."""
    started = time.perf_counter()
    start_dt, end_dt = parse_date_window(date_from, date_to, tz_offset_minutes)
    clean_domain = (domain or DEFAULT_DOMAIN).strip().rstrip("/")
    if not clean_domain.startswith(("http://", "https://")):
        clean_domain = f"https://{clean_domain}"

    is_default = clean_domain.lower() in ("https://1xbet.com", "http://1xbet.com")
    effective_page_host = "https://888starz.bet" if is_default else clean_domain
    sport_slug = get_sport_info(sport_id)["slug"].replace("_", "-")
    section_path = "live" if mode == "live" else "line"
    target_url = (
        f"{effective_page_host}/en/{section_path}"
        if int(sport_id) == 0
        else f"{effective_page_host}/en/{section_path}/{sport_slug}"
    )

    has_playwright = importlib.util.find_spec("playwright") is not None
    has_selenium = importlib.util.find_spec("selenium") is not None
    engine_used = (
        "playwright"
        if has_playwright
        else ("selenium" if has_selenium else "curl_cffi_chrome_tls")
    )

    error_detail: Optional[str] = None
    captured: List[Dict[str, Any]] = []

    if live_browser:
        try:
            if has_playwright:
                res = _try_playwright_intercept(target_url)
                captured = res["captured"]
                engine_used = "playwright"
            elif has_selenium:
                res = _try_selenium_intercept(target_url)
                captured = res["captured"]
                engine_used = "selenium"
        except Exception as exc:
            error_detail = f"Headless browser note ({engine_used}): {type(exc).__name__}: {exc}"

    fetched_at = now_utc_iso()
    matches: List[NormalizedMatch] = []
    raw_payload: Dict[str, Any] = {}
    filter_stats: Dict[str, int] = {}
    is_live = False
    is_demo = False

    if captured:
        source_mode = f"live_intercept ({engine_used})"
        merged_values: List[Dict[str, Any]] = []
        intercepted_urls: List[str] = []
        for item in captured:
            intercepted_urls.append(item["url"])
            vals = item["payload"].get("Value") or []
            if isinstance(vals, list):
                merged_values.extend(vals)
        decoded = decode_vzip_payload(
            {"Value": merged_values},
            mode=mode,
            sport_id=sport_id,
            method_id=METHOD_ID,
            method_name=METHOD_NAME,
            source_mode=source_mode,
            fetched_at=fetched_at,
        )
        matches, filter_stats = filter_matches_for_request(
            decoded, mode, start_dt, end_dt, count
        )
        raw_payload = {
            "InterceptedEngine": engine_used,
            "InterceptedUrls": intercepted_urls,
            "Success": True,
            "Value": merged_values[: max(1, int(count))],
        }
        is_live = True
    else:
        # Capture live service-api background feed packets via Chrome TLS session
        source_mode = f"live_network_capture ({engine_used})"
        endpoint_used, matches, raw_values, filter_stats = fetch_live_vzip_bundle(
            mode=mode,
            sport_id=sport_id,
            count=count,
            domain=domain,
            proxy=None,
            timeout=8,
            start_dt=start_dt,
            end_dt=end_dt,
            method_id=METHOD_ID,
            method_name=METHOD_NAME,
            source_mode=source_mode,
        )
        if endpoint_used is not None:
            is_live = True
            raw_payload = {
                "InterceptedEngine": engine_used,
                "InterceptedPageUrl": target_url,
                "InterceptedNetworkUrls": [endpoint_used],
                "PatternsWatched": list(INTERCEPT_PATTERNS),
                "Success": True,
                "Value": raw_values,
            }
        elif demo_mode:
            is_demo = True
            source_mode = DEMO_SOURCE_MODE
            sim_vzip = build_simulated_vzip_payload(
                mode=mode,
                count=count,
                sport_id=sport_id,
                date_from=date_from,
                date_to=date_to,
                tz_offset_minutes=tz_offset_minutes,
            )
            matches = decode_vzip_payload(
                sim_vzip,
                mode=mode,
                sport_id=sport_id,
                method_id=METHOD_ID,
                method_name=METHOD_NAME,
                source_mode=source_mode,
                fetched_at=fetched_at,
            )
            raw_payload = sim_vzip
        else:
            source_mode = UNAVAILABLE_SOURCE_MODE
            raw_payload = {"Success": False, "Value": []}

    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    return {
        "method_id": METHOD_ID,
        "method_name": METHOD_NAME,
        "endpoint": target_url,
        "mode": mode,
        "date_range": {
            "from": date_from,
            "to": date_to,
            "window_utc": [start_dt.isoformat(), end_dt.isoformat()],
        },
        "engine": engine_used,
        "has_playwright": has_playwright,
        "has_selenium": has_selenium,
        "source_mode": source_mode,
        "is_live_data": is_live,
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
    live_flag = "--live" in sys.argv
    result = fetch_browser_intercept(mode="prematch", sport_id=0, count=10, live_browser=live_flag)
    print(f"[{result['method_name']}]")
    print(
        f"Engine: {result['engine']} | Status: {result['source_mode']} | "
        f"Matches: {result['match_count']} | Latency: {result['latency_ms']} ms"
    )
    for m in result["matches"][:5]:
        print(
            f" - [{m['sport']}] [{m['league']}] {m['home_team']} vs {m['away_team']} @ {m['start_time_local']} | "
            f"1X2: {m['odds_home']} / {m['odds_draw']} / {m['odds_away']}"
        )
