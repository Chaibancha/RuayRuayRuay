"""Web Dashboard Backend & Multi-Format Export Server for 1xBet 4-Method Fetchers."""

from __future__ import annotations

import csv
import html
import io
import json
import mimetypes
import os
import sys
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from fetchers import (
    METHODS_CATALOG,
    SPORTS_CATALOG,
    fetch_aggregator_odds,
    fetch_browser_intercept,
    fetch_internal_feed,
    fetch_oddspapi_odds,
)

ROOT_DIR = Path(__file__).resolve().parent
STATIC_DIR = ROOT_DIR / "static"
DATA_DIR = ROOT_DIR / "data"
LATEST_RESULTS_PATH = DATA_DIR / "latest_results.json"
SETTINGS_PATH = DATA_DIR / "settings.json"

def _default_date_range() -> tuple[str, str]:
    today = datetime.now(timezone.utc).date()
    return today.strftime("%Y-%m-%d"), (today + timedelta(days=3)).strftime("%Y-%m-%d")


def _parse_sport_id(val: Any) -> int:
    if val is None or val == "":
        return 1
    try:
        return int(val)
    except (TypeError, ValueError):
        return 1


_DEF_FROM, _DEF_TO = _default_date_range()
DEFAULT_SETTINGS = {
    "mode": "prematch",
    "sport_id": 1,
    "count": 6,
    "date_from": _DEF_FROM,
    "date_to": _DEF_TO,
    "domain": "https://1xbet.com",
    "proxy": "",
    "oddspapi_key": "",
    "live_browser": False,
}

CSV_COLUMNS = [
    ("method_id", "รหัสวิธี"),
    ("method_name", "วิธีการดึงข้อมูล"),
    ("source_mode", "สถานะแหล่งข้อมูล"),
    ("match_id", "Match ID"),
    ("sport", "กีฬา"),
    ("league", "ลีก / รายการ"),
    ("home_team", "ทีมเจ้าบ้าน"),
    ("away_team", "ทีมเยือน"),
    ("start_time_local", "เวลาแข่ง (เวลาไทย UTC+7)"),
    ("start_time_utc", "เวลาแข่ง (UTC)"),
    ("match_status", "สถานะแมตช์"),
    ("score", "สกอร์"),
    ("odds_home", "ราคาเจ้าบ้าน (1)"),
    ("odds_draw", "ราคาเสมอ (X)"),
    ("odds_away", "ราคาทีมเยือน (2)"),
    ("implied_prob_home", "โอกาสเจ้าบ้าน (%)"),
    ("implied_prob_draw", "โอกาสเสมอ (%)"),
    ("implied_prob_away", "โอกาสทีมเยือน (%)"),
    ("overround_pct", "ค่าน้ำ/Margin (%)"),
    ("handicap_line", "ราคาต่อ (HDP)"),
    ("handicap_home", "HDP เจ้าบ้าน"),
    ("handicap_away", "HDP ทีมเยือน"),
    ("total_line", "เส้นสูง/ต่ำ (O/U)"),
    ("odds_over", "ราคาสูง (Over)"),
    ("odds_under", "ราคาต่ำ (Under)"),
    ("market_active", "สถานะตลาด (Active)"),
    ("fetched_at_utc", "เวลาดึงข้อมูล (UTC)"),
]


class StateStore:
    """Thread-safe store for latest fetched results and saved parameters."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.results_by_method: Dict[str, Dict[str, Any]] = {}
        self.saved_settings: Dict[str, Any] = dict(DEFAULT_SETTINGS)
        self._load_persisted()

    def _load_persisted(self) -> None:
        if LATEST_RESULTS_PATH.exists():
            try:
                data = json.loads(LATEST_RESULTS_PATH.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self.results_by_method = data
            except Exception:
                self.results_by_method = {}
        if SETTINGS_PATH.exists():
            try:
                cfg = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                if isinstance(cfg, dict):
                    self.saved_settings = {**DEFAULT_SETTINGS, **cfg}
            except Exception:
                pass

    def update(self, new_results: Dict[str, Dict[str, Any]]) -> None:
        with self._lock:
            self.results_by_method.update(new_results)
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            LATEST_RESULTS_PATH.write_text(
                json.dumps(self.results_by_method, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def save_settings(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            def_from, def_to = _default_date_range()
            raw_count = cfg.get("count", 6)
            try:
                parsed_count = int(raw_count) if raw_count not in (None, "") else 6
            except (TypeError, ValueError):
                parsed_count = 6
            cleaned = {
                "mode": "live" if cfg.get("mode") == "live" else "prematch",
                "sport_id": _parse_sport_id(cfg.get("sport_id", 1)),
                "count": max(1, min(parsed_count, 1000)),
                "date_from": str(cfg.get("date_from") or def_from).strip()[:10],
                "date_to": str(cfg.get("date_to") or def_to).strip()[:10],
                "domain": str(cfg.get("domain") or "https://1xbet.com").strip(),
                "proxy": str(cfg.get("proxy") or "").strip(),
                "oddspapi_key": str(cfg.get("oddspapi_key") or "").strip(),
                "live_browser": bool(cfg.get("live_browser", False)),
            }
            self.saved_settings = cleaned
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            SETTINGS_PATH.write_text(
                json.dumps(cleaned, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return dict(cleaned)

    def get_settings(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self.saved_settings)

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return dict(self.results_by_method)


STORE = StateStore()


def run_single_method(method_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute one of the 4 fetching methods using validated parameters."""
    mode = "live" if params.get("mode") == "live" else "prematch"
    try:
        raw_c = params.get("count", 50)
        count = max(1, min(int(raw_c) if raw_c not in (None, "") else 50, 1000))
    except (TypeError, ValueError):
        count = 50
    sport_id = _parse_sport_id(params.get("sport_id", 1))
    def_from, def_to = _default_date_range()
    date_from = str(params.get("date_from") or def_from).strip()[:10]
    date_to = str(params.get("date_to") or def_to).strip()[:10]

    domain = str(params.get("domain") or "https://1xbet.com").strip()
    proxy = str(params.get("proxy") or "").strip() or None
    oddspapi_key = str(params.get("oddspapi_key") or "").strip() or None
    live_browser = bool(params.get("live_browser", False))

    sig = {
        "mode": mode,
        "sport_id": sport_id,
        "count": count,
        "date_from": date_from,
        "date_to": date_to,
    }
    if method_id == "1":
        res = fetch_internal_feed(
            mode=mode,
            sport_id=sport_id,
            count=count,
            domain=domain,
            proxy=proxy,
            date_from=date_from,
            date_to=date_to,
        )
    elif method_id == "2":
        res = fetch_browser_intercept(
            mode=mode,
            sport_id=sport_id,
            count=count,
            domain=domain,
            live_browser=live_browser,
            date_from=date_from,
            date_to=date_to,
        )
    elif method_id == "3":
        res = fetch_aggregator_odds(
            mode=mode,
            sport_id=sport_id,
            count=count,
            date_from=date_from,
            date_to=date_to,
        )
    elif method_id == "4":
        res = fetch_oddspapi_odds(
            mode=mode,
            sport_id=sport_id,
            count=count,
            api_key=oddspapi_key,
            date_from=date_from,
            date_to=date_to,
        )
    else:
        raise ValueError(f"Unknown method_id: {method_id}")
    res["params_signature"] = sig
    return res


def execute_fetch(target_method: str, params: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Run one method ('1'..'4') or all 4 in parallel ('all')."""
    method_ids = ["1", "2", "3", "4"] if target_method == "all" else [target_method]
    collected: Dict[str, Dict[str, Any]] = {}

    if len(method_ids) == 1:
        mid = method_ids[0]
        collected[mid] = run_single_method(mid, params)
    else:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(run_single_method, mid, params): mid for mid in method_ids
            }
            for fut in as_completed(futures):
                mid = futures[fut]
                collected[mid] = fut.result()

    ordered = {k: collected[k] for k in method_ids if k in collected}
    STORE.update(ordered)
    return ordered


def _expected_sig(cfg: Dict[str, Any]) -> Dict[str, Any]:
    def_from, def_to = _default_date_range()
    raw_c = cfg.get("count", 50)
    try:
        cnt = max(1, min(int(raw_c) if raw_c not in (None, "") else 50, 1000))
    except (TypeError, ValueError):
        cnt = 50
    return {
        "mode": "live" if cfg.get("mode") == "live" else "prematch",
        "sport_id": _parse_sport_id(cfg.get("sport_id", 1)),
        "count": cnt,
        "date_from": str(cfg.get("date_from") or def_from).strip()[:10],
        "date_to": str(cfg.get("date_to") or def_to).strip()[:10],
    }


def _collect_for_export(
    method_filter: str, snapshot: Dict[str, Dict[str, Any]]
) -> tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    """Filter stored results and ensure data matches current saved settings before export."""
    saved_cfg = STORE.get_settings()
    exp_sig = _expected_sig(saved_cfg)

    if not snapshot:
        execute_fetch("all", saved_cfg)
        snapshot = STORE.snapshot()

    if method_filter in ("1", "2", "3", "4"):
        cur = snapshot.get(method_filter)
        if not cur or cur.get("params_signature") != exp_sig:
            execute_fetch(method_filter, saved_cfg)
            snapshot = STORE.snapshot()
        selected = {method_filter: snapshot[method_filter]}
    else:
        stale = [
            k
            for k in ("1", "2", "3", "4")
            if k not in snapshot or snapshot[k].get("params_signature") != exp_sig
        ]
        if stale:
            execute_fetch("all", saved_cfg)
            snapshot = STORE.snapshot()
        selected = {k: snapshot[k] for k in ("1", "2", "3", "4") if k in snapshot}

    matches: List[Dict[str, Any]] = []
    for mid in sorted(selected.keys()):
        matches.extend(selected[mid].get("matches") or [])
    return selected, matches


def build_csv_bytes(matches: List[Dict[str, Any]]) -> bytes:
    """Render normalized matches as UTF-8 BOM CSV for Excel Thai compatibility."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([label for _, label in CSV_COLUMNS])
    for m in matches:
        writer.writerow([m.get(key, "") for key, _ in CSV_COLUMNS])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def build_normalized_json_bytes(
    selected: Dict[str, Dict[str, Any]], matches: List[Dict[str, Any]]
) -> bytes:
    """Render unified normalized JSON export."""
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "methods_included": list(selected.keys()),
        "total_matches": len(matches),
        "method_summaries": {
            mid: {
                "method_name": res.get("method_name"),
                "source_mode": res.get("source_mode"),
                "is_live_data": res.get("is_live_data"),
                "latency_ms": res.get("latency_ms"),
                "match_count": res.get("match_count"),
                "fetched_at_utc": res.get("fetched_at_utc"),
            }
            for mid, res in selected.items()
        },
        "matches": matches,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def build_raw_json_bytes(selected: Dict[str, Dict[str, Any]]) -> bytes:
    """Render raw payload JSON structure exactly as produced by each method."""
    if len(selected) == 1:
        only = next(iter(selected.values()))
        payload: Any = {
            "method_id": only.get("method_id"),
            "method_name": only.get("method_name"),
            "source_mode": only.get("source_mode"),
            "endpoint": only.get("endpoint"),
            "fetched_at_utc": only.get("fetched_at_utc"),
            "raw_payload": only.get("raw_payload"),
        }
    else:
        payload = {
            mid: {
                "method_name": res.get("method_name"),
                "source_mode": res.get("source_mode"),
                "endpoint": res.get("endpoint"),
                "fetched_at_utc": res.get("fetched_at_utc"),
                "raw_payload": res.get("raw_payload"),
            }
            for mid, res in selected.items()
        }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def build_xls_bytes(matches: List[Dict[str, Any]]) -> bytes:
    """Render an Excel-compatible styled HTML table (.xls) supporting Thai UTF-8."""
    head_cells = "".join(
        f"<th style='background:#0f172a;color:#f8fafc;padding:8px;border:1px solid #334155;'>"
        f"{html.escape(label)}</th>"
        for _, label in CSV_COLUMNS
    )
    body_rows = []
    for idx, m in enumerate(matches):
        bg = "#f8fafc" if idx % 2 == 0 else "#ffffff"
        cells = "".join(
            f"<td style='padding:6px;border:1px solid #cbd5e1;'>{html.escape(str(m.get(key, '') if m.get(key) is not None else ''))}</td>"
            for key, _ in CSV_COLUMNS
        )
        body_rows.append(f"<tr style='background:{bg};'>{cells}</tr>")

    doc = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>1xBet Odds Export</title></head><body>"
        "<table border='1' cellspacing='0' cellpadding='4' "
        "style='border-collapse:collapse;font-family:Segoe UI,Tahoma,sans-serif;font-size:12px;'>"
        f"<thead><tr>{head_cells}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table></body></html>"
    )
    return doc.encode("utf-8")


def build_bundle_zip_bytes(
    selected: Dict[str, Dict[str, Any]], matches: List[Dict[str, Any]]
) -> bytes:
    """Bundle all 4 Python scripts, shared schema, docs, and latest data into a ZIP."""
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in (
            "fetchers/__init__.py",
            "fetchers/schema.py",
            "fetchers/method1_internal_feed.py",
            "fetchers/method2_browser_intercept.py",
            "fetchers/method3_aggregator_scraper.py",
            "fetchers/method4_oddspapi.py",
            "requirements.txt",
            "README.md",
        ):
            fpath = ROOT_DIR / rel
            if fpath.exists():
                zf.write(fpath, arcname=rel)
        zf.writestr("data/latest_matches.csv", build_csv_bytes(matches))
        zf.writestr(
            "data/latest_normalized.json",
            build_normalized_json_bytes(selected, matches),
        )
        zf.writestr("data/latest_raw.json", build_raw_json_bytes(selected))
    return mem.getvalue()


class DashboardHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler serving Dashboard UI, Fetch API, and Downloads."""

    server_version = "1xBetFetcherDashboard/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        sys.stdout.write(
            f"[{datetime.now().strftime('%H:%M:%S')}] {self.address_string()} - {format % args}\n"
        )

    def _send_bytes(
        self,
        body: bytes,
        status: int = 200,
        content_type: str = "application/json; charset=utf-8",
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if extra_headers:
                for k, v in extra_headers.items():
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._send_bytes(body, status=status, content_type="application/json; charset=utf-8")

    def _serve_static(self, rel_path: str) -> None:
        safe_rel = rel_path.lstrip("/") or "index.html"
        target = (STATIC_DIR / safe_rel).resolve()
        if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.is_file():
            self._send_json({"error": "File not found"}, status=404)
            return
        ctype, _ = mimetypes.guess_type(str(target))
        if not ctype:
            ctype = "application/octet-stream"
        if ctype.startswith("text/") or ctype == "application/javascript":
            ctype = f"{ctype}; charset=utf-8"
        self._send_bytes(target.read_bytes(), status=200, content_type=ctype)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self._serve_static("index.html")
            return
        if path.startswith("/static/"):
            self._serve_static(path[len("/static/") :])
            return
        if path == "/api/methods":
            snap = STORE.snapshot()
            enriched = []
            for item in METHODS_CATALOG:
                mid = item["id"]
                last = snap.get(mid)
                enriched.append(
                    {
                        **item,
                        "last_run": (
                            {
                                "source_mode": last.get("source_mode"),
                                "is_live_data": last.get("is_live_data"),
                                "latency_ms": last.get("latency_ms"),
                                "match_count": last.get("match_count"),
                                "fetched_at_utc": last.get("fetched_at_utc"),
                                "error": last.get("error"),
                            }
                            if last
                            else None
                        ),
                    }
                )
            self._send_json(
                {
                    "methods": enriched,
                    "sports": SPORTS_CATALOG,
                    "settings": STORE.get_settings(),
                }
            )
            return
        if path == "/api/settings":
            self._send_json({"settings": STORE.get_settings()})
            return
        if path == "/api/results":
            snap = STORE.snapshot()
            if not snap:
                snap = execute_fetch("all", {})
            self._send_json({"results": snap})
            return
        if path == "/api/download":
            self._handle_download(parse_qs(parsed.query))
            return

        self._send_json({"error": "Not found"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path not in ("/api/fetch", "/api/settings"):
            self._send_json({"error": "Not found"}, status=404)
            return

        length = int(self.headers.get("Content-Length", "0") or 0)
        raw_body = self.rfile.read(length) if length > 0 else b"{}"
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except Exception:
            self._send_json({"error": "Invalid JSON request body"}, status=400)
            return

        if parsed.path == "/api/settings":
            try:
                saved = STORE.save_settings(body)
                self._send_json({"ok": True, "settings": saved})
            except Exception as exc:
                self._send_json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, status=400)
            return

        target_method = str(body.get("method", "all"))
        if target_method not in ("1", "2", "3", "4", "all"):
            self._send_json({"error": "method must be '1', '2', '3', '4', or 'all'"}, status=400)
            return

        merged_params = {**STORE.get_settings(), **body}
        try:
            results = execute_fetch(target_method, merged_params)
            self._send_json(
                {
                    "ok": True,
                    "executed": target_method,
                    "results": results,
                    "all_results": STORE.snapshot(),
                }
            )
        except Exception as exc:
            self._send_json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, status=500)

    def _handle_download(self, qs: Dict[str, List[str]]) -> None:
        fmt = (qs.get("format", ["csv"])[0] or "csv").lower()
        method_filter = (qs.get("method", ["all"])[0] or "all").lower()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = f"method{method_filter}" if method_filter in ("1", "2", "3", "4") else "all_4_methods"

        if fmt == "script":
            script_map = {m["id"]: m["script_filename"] for m in METHODS_CATALOG}
            if method_filter in script_map:
                fname = script_map[method_filter]
                fpath = ROOT_DIR / "fetchers" / fname
                self._send_bytes(
                    fpath.read_bytes(),
                    content_type="text/x-python; charset=utf-8",
                    extra_headers={
                        "Content-Disposition": f'attachment; filename="{fname}"'
                    },
                )
                return
            selected, matches = _collect_for_export("all", STORE.snapshot())
            zip_bytes = build_bundle_zip_bytes(selected, matches)
            self._send_bytes(
                zip_bytes,
                content_type="application/zip",
                extra_headers={
                    "Content-Disposition": f'attachment; filename="1xbet_4_methods_bundle_{stamp}.zip"'
                },
            )
            return

        selected, matches = _collect_for_export(method_filter, STORE.snapshot())

        if fmt == "csv":
            data = build_csv_bytes(matches)
            self._send_bytes(
                data,
                content_type="text/csv; charset=utf-8",
                extra_headers={
                    "Content-Disposition": f'attachment; filename="1xbet_odds_{suffix}_{stamp}.csv"'
                },
            )
            return
        if fmt == "json":
            data = build_normalized_json_bytes(selected, matches)
            self._send_bytes(
                data,
                content_type="application/json; charset=utf-8",
                extra_headers={
                    "Content-Disposition": f'attachment; filename="1xbet_normalized_{suffix}_{stamp}.json"'
                },
            )
            return
        if fmt == "raw_json":
            data = build_raw_json_bytes(selected)
            self._send_bytes(
                data,
                content_type="application/json; charset=utf-8",
                extra_headers={
                    "Content-Disposition": f'attachment; filename="1xbet_raw_{suffix}_{stamp}.json"'
                },
            )
            return
        if fmt == "xls":
            data = build_xls_bytes(matches)
            self._send_bytes(
                data,
                content_type="application/vnd.ms-excel; charset=utf-8",
                extra_headers={
                    "Content-Disposition": f'attachment; filename="1xbet_odds_{suffix}_{stamp}.xls"'
                },
            )
            return

        self._send_json({"error": f"Unsupported download format: {fmt}"}, status=400)


class ExclusiveThreadingHTTPServer(ThreadingHTTPServer):
    """Prevent multiple processes from binding the same port on Windows."""

    allow_reuse_address = False


def main() -> None:
    port = int(os.getenv("PORT", "8000"))
    for idx, arg in enumerate(sys.argv[1:]):
        if arg == "--port" and idx + 2 < len(sys.argv):
            port = int(sys.argv[idx + 2])

    # Pre-warm initial dataset if empty so Dashboard has immediate data on load
    if not STORE.snapshot():
        execute_fetch("all", STORE.get_settings())

    server = ExclusiveThreadingHTTPServer(("127.0.0.1", port), DashboardHandler)
    print(f"1xBet 4-Method Dashboard running at http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.server_close()


if __name__ == "__main__":
    main()
