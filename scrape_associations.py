"""
Scrape aideaucodage.fr for frequently associated CCAM codes.
Extracts the "Actes CCAM frequemment associes" section for each active code.
Rate-limited to ~1 request per second to be respectful.
"""

import json
import time
import sqlite3
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

DB_PATH = Path(__file__).parent / "data" / "ccam.db"
OUTPUT_PATH = Path(__file__).parent / "data" / "frequent_associations.json"
PROGRESS_PATH = Path(__file__).parent / "data" / "scrape_progress.json"

BASE_URL = "https://www.aideaucodage.fr/ccam-"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
DELAY = 1.0  # seconds between requests


def get_active_codes():
    """Get all active CCAM codes from our database."""
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("SELECT code FROM ccam_codes WHERE date_end IS NULL ORDER BY code")
    codes = [r[0] for r in c.fetchall()]
    conn.close()
    return codes


def scrape_code(code):
    """Scrape aideaucodage.fr for a single CCAM code.
    Returns list of frequently associated codes with labels.
    """
    url = f"{BASE_URL}{code}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return {"code": code, "status": resp.status_code, "associations": []}

        soup = BeautifulSoup(resp.text, "html.parser")

        # Find "Actes CCAM frequemment associes" section
        frequent = []
        for h2 in soup.find_all("h2"):
            text = h2.get_text()
            if "quemment associ" in text:
                table = h2.find_next_sibling("table")
                if table:
                    for row in table.find_all("tr"):
                        cols = row.find_all("td")
                        if len(cols) >= 2:
                            link = cols[0].find("a")
                            assoc_code = link.get_text(strip=True).upper() if link else cols[0].get_text(strip=True).upper()
                            label = cols[1].get_text(strip=True)
                            if assoc_code and len(assoc_code) == 7:
                                frequent.append({
                                    "code": assoc_code,
                                    "label": label
                                })
                break

        # Also grab the official associations from aideaucodage
        official = []
        for h3 in soup.find_all("h3"):
            text = h3.get_text()
            if "activit" in text.lower() and "associ" in text.lower():
                table = h3.find_next_sibling("table")
                if table:
                    for row in table.find_all("tr"):
                        cols = row.find_all("td")
                        if len(cols) >= 2:
                            # Parse the complex format: CODE (activity) ASSOC_CODE(activity) label
                            for a_tag in row.find_all("a"):
                                href = a_tag.get("href", "")
                                if href.startswith("ccam-") and a_tag.get_text(strip=True).upper() != code:
                                    assoc_code = a_tag.get_text(strip=True).upper()
                                    if len(assoc_code) == 7:
                                        official.append(assoc_code)
                break

        return {
            "code": code,
            "status": 200,
            "frequent_count": len(frequent),
            "frequent": frequent,
            "official_codes": list(set(official))
        }

    except Exception as e:
        return {"code": code, "status": "error", "error": str(e), "associations": []}


def load_progress():
    """Load progress from previous run."""
    if PROGRESS_PATH.exists():
        with open(PROGRESS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"scraped": {}, "last_index": 0}


def save_progress(progress):
    """Save progress for resume capability."""
    with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False)


def main():
    codes = get_active_codes()
    total = len(codes)
    print(f"Total active codes: {total}")

    progress = load_progress()
    scraped = progress["scraped"]
    start_idx = progress["last_index"]

    print(f"Resuming from index {start_idx} ({len(scraped)} already scraped)")

    errors = 0
    empty = 0

    for i in range(start_idx, total):
        code = codes[i]

        if code in scraped:
            continue

        result = scrape_code(code)
        scraped[code] = result

        freq_count = result.get("frequent_count", 0)
        if result.get("status") != 200:
            errors += 1
            status_char = "X"
        elif freq_count == 0:
            empty += 1
            status_char = "-"
        else:
            status_char = "+"

        # Progress output every code
        done = len(scraped)
        pct = done / total * 100
        if done % 50 == 0 or i == total - 1:
            print(f"[{pct:5.1f}%] {done}/{total} | {status_char} {code} freq={freq_count} | errors={errors} empty={empty}")

        # Save progress every 100 codes
        if done % 100 == 0:
            progress["scraped"] = scraped
            progress["last_index"] = i + 1
            save_progress(progress)

        time.sleep(DELAY)

    # Final save
    progress["scraped"] = scraped
    progress["last_index"] = total
    save_progress(progress)

    # Also save clean output
    output = {}
    total_assoc = 0
    codes_with_assoc = 0
    for code, data in scraped.items():
        freq = data.get("frequent", [])
        if freq:
            output[code] = freq
            total_assoc += len(freq)
            codes_with_assoc += 1

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=1)

    print(f"\nDone!")
    print(f"Total scraped: {len(scraped)}")
    print(f"Codes with frequent associations: {codes_with_assoc}")
    print(f"Total frequent associations: {total_assoc}")
    print(f"Errors: {errors}")
    print(f"Output: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
