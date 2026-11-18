"""1xBet 4-Method Odds Fetchers package."""

from .method1_internal_feed import fetch_internal_feed
from .method2_browser_intercept import fetch_browser_intercept
from .method3_aggregator_scraper import fetch_aggregator_odds
from .method4_oddspapi import fetch_oddspapi_odds
from .schema import SPORTS_CATALOG, NormalizedMatch

METHODS_CATALOG = [
    {
        "id": "1",
        "key": "internal_feed",
        "name": "1. ยิง Internal Feed ตรง (LineFeed / LiveFeed)",
        "short_name": "Internal Feed (VZip)",
        "cost": "ฟรี 100% (ไม่จำกัด)",
        "latency": "เร็วมาก (ระดับวินาที)",
        "difficulty": "ยาก (ต้องแกะรหัส JSON เอง และต้องจัดการเรื่อง Proxy/โดเมนโดนบล็อก)",
        "best_for": "ผู้ที่ต้องการข้อมูลสดความเร็วสูงและพร้อมดูแลระบบเลี่ยงบล็อกเอง",
        "endpoint_hint": "/LineFeed/Get1x2_VZip & /LiveFeed/Get1x2_VZip",
        "script_filename": "method1_internal_feed.py",
    },
    {
        "id": "2",
        "key": "browser_intercept",
        "name": "2. Playwright / Selenium Network Interception",
        "short_name": "Browser Interception",
        "cost": "ฟรี 100% (ไม่จำกัด)",
        "latency": "ปานกลาง (ช้ากว่ายิงตรงเล็กน้อย)",
        "difficulty": "ปานกลาง (เขียนง่ายกว่าแกะ Request แต่กิน RAM/CPU เครื่องสูง)",
        "best_for": "การดึงข้อมูลหลายตลาดพร้อมกันโดยไม่อยากปวดหัวเรื่องการสร้าง Cookie/Token",
        "endpoint_hint": "Headless Browser CDP / Network Response Listener",
        "script_filename": "method2_browser_intercept.py",
    },
    {
        "id": "3",
        "key": "aggregator_scrape",
        "name": "3. Scrape จากเว็บกลาง (OddsPortal / Flashscore)",
        "short_name": "Odds Aggregators",
        "cost": "ฟรี 100% (ไม่จำกัด)",
        "latency": "ช้า (ดีเลย์ 10–30 วินาที)",
        "difficulty": "ง่าย (มีโค้ด Open-Source บน GitHub ให้ศึกษาเยอะและไม่ติดบล็อกในไทย)",
        "best_for": "การเก็บข้อมูลสถิติย้อนหลัง (Backtest) หรือวิเคราะห์บอลล่วงหน้าก่อนแข่ง",
        "endpoint_hint": "Public Scoreboard / OddsPortal & Flashscore Feeds",
        "script_filename": "method3_aggregator_scraper.py",
    },
    {
        "id": "4",
        "key": "oddspapi",
        "name": "4. OddsPapi (Free Tier)",
        "short_name": "OddsPapi REST v4",
        "cost": "ฟรี (จำกัด 250 ครั้ง/เดือน)",
        "latency": "เร็ว (มีโครงสร้างมาตรฐาน)",
        "difficulty": "ง่ายที่สุด (มีเอกสารชัดเจน ข้อมูลสะอาดพร้อมใช้)",
        "best_for": "ช่วงเริ่มต้นเขียนโค้ดทดลองระบบ หรือดึงเฉพาะคู่ใหญ่ไม่กี่คู่ต่อวัน",
        "endpoint_hint": "GET /v4/fixtures -> GET /v4/odds?bookmaker=1xbet",
        "script_filename": "method4_oddspapi.py",
    },
]

__all__ = [
    "METHODS_CATALOG",
    "SPORTS_CATALOG",
    "NormalizedMatch",
    "fetch_internal_feed",
    "fetch_browser_intercept",
    "fetch_aggregator_odds",
    "fetch_oddspapi_odds",
]
