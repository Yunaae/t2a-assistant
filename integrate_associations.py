"""
Integrate validated frequent associations into the CCAM SQLite database.
Creates a new table 'frequent_associations' separate from the official ATIH 'associations' table.
"""

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "ccam.db"
VALIDATED_PATH = Path(__file__).parent / "data" / "validated_associations.json"


def integrate():
    print("Loading validated associations...")
    with open(VALIDATED_PATH, "r", encoding="utf-8") as f:
        validated = json.load(f)

    total_codes = len(validated)
    total_pairs = sum(len(v) for v in validated.values())
    print(f"  {total_codes} codes, {total_pairs} association pairs")

    print("Updating database...")
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    # Drop and recreate the frequent_associations table
    c.execute("DROP TABLE IF EXISTS frequent_associations")
    c.execute("""
        CREATE TABLE frequent_associations (
            code TEXT NOT NULL,
            associated_code TEXT NOT NULL,
            label TEXT,
            icr_public REAL,
            confidence TEXT NOT NULL,
            rank INTEGER NOT NULL,
            PRIMARY KEY (code, associated_code)
        )
    """)

    # Create index for fast lookups
    c.execute("CREATE INDEX idx_freq_assoc_code ON frequent_associations(code)")

    # Insert all validated associations
    inserted = 0
    for source_code, assoc_list in validated.items():
        for rank, assoc in enumerate(assoc_list, 1):
            c.execute("""
                INSERT OR IGNORE INTO frequent_associations
                (code, associated_code, label, icr_public, confidence, rank)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                source_code,
                assoc["code"],
                assoc.get("label"),
                assoc.get("icr_public"),
                assoc["confidence"],
                rank,
            ))
            inserted += 1

    conn.commit()

    # Verify
    c.execute("SELECT COUNT(*) FROM frequent_associations")
    db_count = c.fetchone()[0]

    c.execute("SELECT COUNT(DISTINCT code) FROM frequent_associations")
    db_codes = c.fetchone()[0]

    c.execute("SELECT confidence, COUNT(*) FROM frequent_associations GROUP BY confidence")
    by_confidence = c.fetchall()

    conn.close()

    print(f"\nIntegration complete:")
    print(f"  Inserted: {inserted} rows")
    print(f"  In DB: {db_count} rows, {db_codes} codes")
    print(f"  By confidence:")
    for conf, count in by_confidence:
        print(f"    {conf}: {count}")


if __name__ == "__main__":
    integrate()
