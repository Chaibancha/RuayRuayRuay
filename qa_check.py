"""Automated QA test suite for the 1xBet 4-Method Fetcher & Dashboard."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone

from app import (
    STORE,
    build_bundle_zip_bytes,
    build_csv_bytes,
    build_normalized_json_bytes,
    build_raw_json_bytes,
    build_xls_bytes,
    execute_fetch,
)
from fetchers import SPORTS_CATALOG


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def run_qa() -> None:
    # 1. Catalog check (All Sports + 20 specific sports = 21 total)
    assert len(SPORTS_CATALOG) == 21, f"Expected 21 entries, got {len(SPORTS_CATALOG)}"
    assert SPORTS_CATALOG[0]["id"] == 0, "First catalog entry must be id=0 (All Sports)"

    # 2. Save settings preserves sport_id=0 and date_from/date_to
    saved = STORE.save_settings(
        {
            "mode": "prematch",
            "sport_id": 0,
            "count": 12,
            "date_from": "2026-11-18",
            "date_to": "2026-11-25",
        }
    )
    assert saved["sport_id"] == 0, f"Expected sport_id=0, got {saved['sport_id']}"
    assert saved["count"] == 12
    assert saved["date_from"] == "2026-11-18"
    assert saved["date_to"] == "2026-11-25"

    # 3. Fetch All Sports (sport_id=0) with count=12 & custom date range
    res_all = execute_fetch(
        "all",
        {
            "mode": "prematch",
            "sport_id": 0,
            "count": 12,
            "date_from": "2026-11-18",
            "date_to": "2026-11-25",
        },
    )
    win_start = datetime(2026, 11, 18, 0, 0, 0, tzinfo=timezone.utc)
    win_end = datetime(2026, 11, 25, 23, 59, 59, tzinfo=timezone.utc)

    for mid in ("1", "2", "3", "4"):
        matches = res_all[mid]["matches"]
        assert len(matches) == 12, f"Method {mid} expected 12 matches, got {len(matches)}"
        distinct_sports = {m["sport"] for m in matches}
        assert len(distinct_sports) >= 4, (
            f"Method {mid} All Sports should cover >=4 sports, got {distinct_sports}"
        )
        for m in matches:
            dt = _parse_iso(m["start_time_utc"])
            assert win_start <= dt <= win_end, (
                f"Method {mid} match {m['home_team']} timestamp {dt} outside [{win_start}, {win_end}]"
            )

    # 4. Individual sport + inverted date range & single-day check
    res_esports = execute_fetch(
        "all",
        {
            "mode": "live",
            "sport_id": 40,
            "count": 4,
            "date_from": "2026-11-22",
            "date_to": "2026-11-20",  # inverted intentionally
        },
    )
    es_start = datetime(2026, 11, 20, 0, 0, 0, tzinfo=timezone.utc)
    es_end = datetime(2026, 11, 22, 23, 59, 59, tzinfo=timezone.utc)
    for mid in ("1", "2", "3", "4"):
        matches = res_esports[mid]["matches"]
        assert len(matches) == 4
        for m in matches:
            assert "Esports" in m["sport"], f"Expected Esports, got {m['sport']}"
            dt = _parse_iso(m["start_time_utc"])
            assert es_start <= dt <= es_end

    # 5. Export formats check
    all_matches = [m for mid in ("1", "2", "3", "4") for m in res_all[mid]["matches"]]
    csv_b = build_csv_bytes(all_matches)
    json_b = build_normalized_json_bytes(res_all, all_matches)
    raw_b = build_raw_json_bytes(res_all)
    xls_b = build_xls_bytes(all_matches)
    zip_b = build_bundle_zip_bytes(res_all, all_matches)

    assert csv_b.startswith(b"\xef\xbb\xbf") and len(csv_b) > 1000
    assert json.loads(json_b.decode("utf-8"))["total_matches"] == 48
    assert len(json.loads(raw_b.decode("utf-8"))) == 4
    assert b"<table" in xls_b
    with zipfile.ZipFile(io.BytesIO(zip_b)) as zf:
        names = set(zf.namelist())
        assert "fetchers/schema.py" in names
        assert "data/latest_matches.csv" in names

    print("ALL QA CHECKS PASSED (48 multi-sport matches, date window & 5 export formats verified)")


if __name__ == "__main__":
    run_qa()
