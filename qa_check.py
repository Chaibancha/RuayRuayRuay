"""Automated QA test suite for the 1xBet 4-Method Fetcher & Dashboard."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone

from app import (
    STORE,
    _collect_for_export,
    build_bundle_zip_bytes,
    build_csv_bytes,
    build_normalized_json_bytes,
    build_raw_json_bytes,
    build_xls_bytes,
    execute_fetch,
)
from fetchers import SPORTS_CATALOG
from fetchers.schema import parse_date_window


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def run_qa() -> None:
    now_utc = datetime.now(timezone.utc)

    # 1. Catalog check (All Sports + 20 specific sports = 21 total)
    assert len(SPORTS_CATALOG) == 21, f"Expected 21 entries, got {len(SPORTS_CATALOG)}"
    assert SPORTS_CATALOG[0]["id"] == 0, "First catalog entry must be id=0 (All Sports)"

    # 2. Exact user scenario: Pre-match, All Sports (0), count=50, 2026-11-19 to 2026-11-20
    saved = STORE.save_settings(
        {
            "mode": "prematch",
            "sport_id": 0,
            "count": 50,
            "date_from": "2026-11-19",
            "date_to": "2026-11-20",
        }
    )
    assert saved["sport_id"] == 0
    assert saved["count"] == 50
    assert saved["date_from"] == "2026-11-19"
    assert saved["date_to"] == "2026-11-20"

    res_m1 = execute_fetch("1", saved)["1"]
    assert res_m1["is_live_data"] is True, f"Expected live data, got {res_m1['source_mode']}"
    assert "simulated" not in res_m1["source_mode"].lower()
    m1_matches = res_m1["matches"]
    assert len(m1_matches) == 50, f"Expected 50 matches, got {len(m1_matches)}"

    win_start, win_end = parse_date_window("2026-11-19", "2026-11-20")
    banned_fake_names = {"Rodtang Jitmuangnon", "Ilia Topuria", "Oleksandr Usyk", "Los Angeles Dodgers"}

    distinct_sports = {m["sport"] for m in m1_matches}
    assert len(distinct_sports) >= 5, f"Expected >=5 distinct sports, got {distinct_sports}"

    for m in m1_matches:
        dt = _parse_iso(m["start_time_utc"])
        assert dt > now_utc, f"Match {m['home_team']} vs {m['away_team']} is in the past ({dt} <= {now_utc})"
        assert win_start <= dt <= win_end, (
            f"Match {m['home_team']} timestamp {dt} outside local 2026-11-19..20 window [{win_start}, {win_end}]"
        )
        assert m["start_time_local"].startswith(("2026-11-19", "2026-11-20")), (
            f"Unexpected local time string: {m['start_time_local']}"
        )
        assert m["home_team"] not in banned_fake_names
        assert m["odds_home"] is not None and m["odds_away"] is not None, (
            f"Missing 1X2/Moneyline odds for {m['sport']} {m['home_team']} vs {m['away_team']}"
        )

    # 3. Verify all 4 methods with count=12 across 2026-11-19 to 2026-11-20
    STORE.save_settings(
        {
            "mode": "prematch",
            "sport_id": 0,
            "count": 12,
            "date_from": "2026-11-19",
            "date_to": "2026-11-20",
        }
    )
    res_all = execute_fetch("all", STORE.get_settings())
    for mid in ("1", "2", "3", "4"):
        matches = res_all[mid]["matches"]
        assert len(matches) == 12, f"Method {mid} expected 12 matches, got {len(matches)}"
        assert res_all[mid]["is_live_data"] is True
        for m in matches:
            dt = _parse_iso(m["start_time_utc"])
            assert dt > now_utc
            assert win_start <= dt <= win_end

    # 4. Verify max count up to 1000 and export auto-refresh when settings change before download
    saved_1000 = STORE.save_settings(
        {
            "mode": "prematch",
            "sport_id": 0,
            "count": 1000,
            "date_from": "2026-11-19",
            "date_to": "2026-11-20",
        }
    )
    assert saved_1000["count"] == 1000, f"Expected count=1000, got {saved_1000['count']}"
    STORE.save_settings(
        {
            "mode": "prematch",
            "sport_id": 0,
            "count": 50,
            "date_from": "2026-11-19",
            "date_to": "2026-11-20",
        }
    )
    selected, export_matches = _collect_for_export("1", STORE.snapshot())
    assert len(export_matches) == 50, f"Expected 50 exported matches after settings update, got {len(export_matches)}"

    csv_b = build_csv_bytes(export_matches)
    json_b = build_normalized_json_bytes(selected, export_matches)
    raw_b = build_raw_json_bytes(selected)
    xls_b = build_xls_bytes(export_matches)
    zip_b = build_bundle_zip_bytes(selected, export_matches)

    csv_text = csv_b.decode("utf-8-sig")
    assert "เวลาแข่ง (เวลาไทย UTC+7)" in csv_text
    assert "simulated_fallback" not in csv_text
    assert "Rodtang" not in csv_text
    assert len(csv_text.strip().splitlines()) == 51  # 1 header + 50 rows
    assert json.loads(json_b.decode("utf-8"))["total_matches"] == 50
    assert b"<table" in xls_b
    with zipfile.ZipFile(io.BytesIO(zip_b)) as zf:
        assert "data/latest_matches.csv" in zf.namelist()

    print("ALL QA CHECKS PASSED: 50 real upcoming matches in 2026-11-19..20 (UTC+7), 0 past/fake matches!")


if __name__ == "__main__":
    run_qa()
