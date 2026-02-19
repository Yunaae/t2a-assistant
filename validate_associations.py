"""
Validate scraped associations from aideaucodage.fr against ATIH CCAM data.

Validation rules:
1. Associated code must exist in our CCAM database
2. Associated code must be active (not expired)
3. If it's also an official ATIH association -> mark as "verified" (highest confidence)
4. If codes share the same chapter/anatomical region -> mark as "related" (high confidence)
5. Filter out self-references (code associated with itself)

Output: validated_associations.json with confidence levels
"""

import json
import sqlite3
from pathlib import Path
from collections import defaultdict

DB_PATH = Path(__file__).parent / "data" / "ccam.db"
INPUT_PATH = Path(__file__).parent / "data" / "frequent_associations.json"
OUTPUT_PATH = Path(__file__).parent / "data" / "validated_associations.json"
REPORT_PATH = Path(__file__).parent / "data" / "validation_report.txt"


def load_ccam_data():
    """Load all CCAM code data for validation."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # All codes (active and expired)
    c.execute("SELECT code, label, date_end, chapter_num, subchapter_num, icr_public FROM ccam_codes")
    codes = {}
    for r in c.fetchall():
        codes[r["code"]] = {
            "label": r["label"],
            "active": r["date_end"] is None,
            "chapter": r["chapter_num"],
            "subchapter": r["subchapter_num"],
            "icr_public": r["icr_public"],
        }

    # Official ATIH associations
    c.execute("SELECT code, associated_code FROM associations")
    official = defaultdict(set)
    for r in c.fetchall():
        official[r["code"]].add(r["associated_code"])

    conn.close()
    return codes, official


def validate():
    """Run validation on scraped associations."""
    print("Loading CCAM data...")
    codes, official = load_ccam_data()
    print(f"  {len(codes)} codes in DB, {len(official)} codes with official associations")

    print("Loading scraped associations...")
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        scraped = json.load(f)
    print(f"  {len(scraped)} codes with scraped associations")

    validated = {}
    stats = {
        "total_scraped_pairs": 0,
        "kept": 0,
        "removed_not_found": 0,
        "removed_expired": 0,
        "removed_self_ref": 0,
        "verified_atih": 0,
        "same_chapter": 0,
        "cross_chapter": 0,
    }

    report_lines = []

    for source_code, assoc_list in scraped.items():
        if source_code not in codes:
            continue

        source_info = codes[source_code]
        official_set = official.get(source_code, set())
        valid_assocs = []

        for assoc in assoc_list:
            assoc_code = assoc["code"]
            stats["total_scraped_pairs"] += 1

            # Rule 1: Self-reference
            if assoc_code == source_code:
                stats["removed_self_ref"] += 1
                continue

            # Rule 2: Code must exist
            if assoc_code not in codes:
                stats["removed_not_found"] += 1
                report_lines.append(f"NOT_FOUND: {source_code} -> {assoc_code}")
                continue

            assoc_info = codes[assoc_code]

            # Rule 3: Code must be active
            if not assoc_info["active"]:
                stats["removed_expired"] += 1
                report_lines.append(f"EXPIRED: {source_code} -> {assoc_code}")
                continue

            # Determine confidence level
            if assoc_code in official_set:
                confidence = "verified"
                stats["verified_atih"] += 1
            elif source_info["chapter"] and assoc_info["chapter"] and source_info["chapter"] == assoc_info["chapter"]:
                confidence = "same_chapter"
                stats["same_chapter"] += 1
            else:
                confidence = "cross_chapter"
                stats["cross_chapter"] += 1

            valid_assocs.append({
                "code": assoc_code,
                "label": assoc.get("label", assoc_info["label"]),
                "icr_public": assoc_info["icr_public"],
                "confidence": confidence,
            })

            stats["kept"] += 1

        if valid_assocs:
            # Sort: verified first, then same_chapter, then cross_chapter
            # Within each group, sort by ICR descending
            confidence_order = {"verified": 0, "same_chapter": 1, "cross_chapter": 2}
            valid_assocs.sort(key=lambda x: (confidence_order.get(x["confidence"], 9), -(x["icr_public"] or 0)))
            validated[source_code] = valid_assocs

    # Save validated output
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(validated, f, ensure_ascii=False, indent=1)

    # Save report
    report = [
        "VALIDATION REPORT",
        "=" * 50,
        f"",
        f"Input: {len(scraped)} codes with scraped associations",
        f"Output: {len(validated)} codes with validated associations",
        f"",
        f"Total scraped pairs: {stats['total_scraped_pairs']}",
        f"Kept: {stats['kept']}",
        f"  - Verified (also in ATIH official): {stats['verified_atih']}",
        f"  - Same chapter (anatomical region): {stats['same_chapter']}",
        f"  - Cross chapter: {stats['cross_chapter']}",
        f"",
        f"Removed: {stats['total_scraped_pairs'] - stats['kept']}",
        f"  - Code not found in DB: {stats['removed_not_found']}",
        f"  - Code expired: {stats['removed_expired']}",
        f"  - Self-reference: {stats['removed_self_ref']}",
        f"",
    ]

    if report_lines:
        report.append(f"Details ({len(report_lines)} removals):")
        for line in report_lines[:100]:
            report.append(f"  {line}")
        if len(report_lines) > 100:
            report.append(f"  ... and {len(report_lines) - 100} more")

    report_text = "\n".join(report)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report_text)

    print(report_text)
    print(f"\nOutput: {OUTPUT_PATH}")
    print(f"Report: {REPORT_PATH}")


if __name__ == "__main__":
    validate()
