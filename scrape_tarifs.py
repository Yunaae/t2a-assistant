"""
Scrape CCAM tariffs (base rate in euros, activity 1) from aideaucodage.fr.
Uses concurrent requests for speed (~15 min instead of 2.5h).
"""

import json
import time
import re
import sqlite3
import asyncio
from pathlib import Path

import aiohttp
from bs4 import BeautifulSoup

DB_PATH = Path(__file__).parent / "data" / "ccam.db"
OUTPUT_PATH = Path(__file__).parent / "data" / "tarifs.json"
PROGRESS_PATH = Path(__file__).parent / "data" / "tarif_progress.json"

BASE_URL = "https://www.aideaucodage.fr/ccam-"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
CONCURRENCY = 5  # parallel requests
DELAY = 0.3  # seconds between batches


def get_active_codes():
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("SELECT code FROM ccam_codes WHERE date_end IS NULL ORDER BY code")
    codes = [r[0] for r in c.fetchall()]
    conn.close()
    return codes


def parse_tarif(html, code):
    """Extract the base tariff (activity 1) from an aideaucodage page."""
    soup = BeautifulSoup(html, "html.parser")

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            # Row format: ['01/01/2025', '1', '349,61\xa0€']
            if len(cells) >= 3 and re.match(r"\d{2}/\d{2}/\d{4}", cells[0]) and cells[1] == "1":
                tarif_str = cells[2].replace("\xa0", "").replace("€", "").replace(",", ".").strip()
                try:
                    return float(tarif_str)
                except ValueError:
                    pass
    return None


async def fetch_tarif(session, code, semaphore):
    """Fetch tariff for a single code."""
    async with semaphore:
        url = f"{BASE_URL}{code}"
        try:
            async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return code, None, resp.status
                html = await resp.text()
                tarif = parse_tarif(html, code)
                return code, tarif, 200
        except Exception as e:
            return code, None, str(e)


async def main():
    codes = get_active_codes()
    total = len(codes)
    print(f"Total active codes: {total}")

    # Load progress
    progress = {}
    if PROGRESS_PATH.exists():
        with open(PROGRESS_PATH, "r", encoding="utf-8") as f:
            progress = json.load(f)

    remaining = [c for c in codes if c not in progress]
    print(f"Already done: {len(progress)}, remaining: {len(remaining)}")

    semaphore = asyncio.Semaphore(CONCURRENCY)

    async with aiohttp.ClientSession() as session:
        batch_size = CONCURRENCY * 2
        found = sum(1 for v in progress.values() if v is not None)
        errors = 0

        for i in range(0, len(remaining), batch_size):
            batch = remaining[i:i + batch_size]
            tasks = [fetch_tarif(session, code, semaphore) for code in batch]
            results = await asyncio.gather(*tasks)

            for code, tarif, status in results:
                progress[code] = tarif
                if tarif is not None:
                    found += 1
                elif status != 200:
                    errors += 1

            done = len(progress)
            pct = done / total * 100
            if done % 100 < batch_size or i + batch_size >= len(remaining):
                print(f"[{pct:5.1f}%] {done}/{total} | found={found} errors={errors}")

            # Save progress every 500
            if done % 500 < batch_size:
                with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
                    json.dump(progress, f)

            await asyncio.sleep(DELAY)

    # Final save
    with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
        json.dump(progress, f)

    # Clean output (only codes with tariffs)
    tarifs = {k: v for k, v in progress.items() if v is not None}
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(tarifs, f, indent=1)

    found = len(tarifs)
    missing = total - found
    print(f"\nDone! {found} tarifs found, {missing} missing")
    print(f"Output: {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
