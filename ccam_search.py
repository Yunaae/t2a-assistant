"""
T2A Assistant — CCAM Search Engine + CLI Demo
Search CCAM codes by natural language description and check compatibility.
"""

import sqlite3
import re
import sys
import unicodedata
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "ccam.db"


def strip_accents(text):
    """Remove accents for search normalization."""
    if not text:
        return ""
    nfkd = unicodedata.normalize('NFKD', str(text))
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_query(query):
    """Normalize a search query for FTS matching."""
    text = strip_accents(query.lower().strip())
    text = re.sub(r'[^\w\s]', ' ', text)
    tokens = text.split()
    # Remove very short words (articles, prepositions) unless it's the only word
    if len(tokens) > 1:
        tokens = [t for t in tokens if len(t) > 2]
    return tokens


class CCAMSearch:
    def __init__(self, db_path=DB_PATH):
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    def search(self, query, limit=10, active_only=True):
        """Search CCAM codes by natural language description.
        Uses FTS5 for fast full-text search with accent-insensitive matching.
        """
        tokens = normalize_query(query)
        if not tokens:
            return []

        # Build FTS query: all tokens must match (implicit AND)
        fts_query = " ".join(tokens)

        c = self.conn.cursor()

        active_filter = "AND cc.date_end IS NULL" if active_only else ""

        # Strategy 1: FTS on normalized label
        c.execute(f"""
            SELECT cc.code, cc.label, cc.icr_public, cc.icr_private,
                   cc.chapter_title, cc.subchapter_title, cc.paragraph_title,
                   cc.activity, cc.classant, cc.coding_instruction,
                   cc.gestures_text, cc.modifiers, cc.date_end, cc.tarif_base,
                   ccam_fts.rank as fts_rank
            FROM ccam_fts
            JOIN ccam_codes cc ON cc.rowid = ccam_fts.rowid
            WHERE ccam_fts.label_normalized MATCH ?
            {active_filter}
            ORDER BY ccam_fts.rank
            LIMIT ?
        """, (fts_query, limit))

        results = c.fetchall()

        # Strategy 2: If no results, try matching any token (OR)
        if not results and len(tokens) > 1:
            or_query = " OR ".join(tokens)
            c.execute(f"""
                SELECT cc.code, cc.label, cc.icr_public, cc.icr_private,
                       cc.chapter_title, cc.subchapter_title, cc.paragraph_title,
                       cc.activity, cc.classant, cc.coding_instruction,
                       cc.gestures_text, cc.modifiers, cc.date_end, cc.tarif_base,
                       ccam_fts.rank as fts_rank
                FROM ccam_fts
                JOIN ccam_codes cc ON cc.rowid = ccam_fts.rowid
                WHERE ccam_fts.label_normalized MATCH ?
                {active_filter}
                ORDER BY ccam_fts.rank
                LIMIT ?
            """, (or_query, limit))
            results = c.fetchall()

        # Strategy 3: LIKE fallback for partial matches
        if not results:
            like_pattern = "%" + "%".join(tokens) + "%"
            c.execute(f"""
                SELECT code, label, icr_public, icr_private,
                       chapter_title, subchapter_title, paragraph_title,
                       activity, classant, coding_instruction,
                       gestures_text, modifiers, date_end, tarif_base,
                       0 as fts_rank
                FROM ccam_codes
                WHERE label_normalized LIKE ?
                {active_filter}
                LIMIT ?
            """, (like_pattern, limit))
            results = c.fetchall()

        rows = [dict(r) for r in results]

        # Enrich with association counts (official + frequent)
        if rows:
            codes = [r["code"] for r in rows]
            placeholders = ",".join("?" for _ in codes)
            c.execute(f"""
                SELECT code, COUNT(*) as cnt
                FROM associations
                WHERE code IN ({placeholders})
                GROUP BY code
            """, codes)
            official_counts = {r[0]: r[1] for r in c.fetchall()}
            c.execute(f"""
                SELECT code, COUNT(*) as cnt
                FROM frequent_associations
                WHERE code IN ({placeholders})
                GROUP BY code
            """, codes)
            freq_counts = {r[0]: r[1] for r in c.fetchall()}
            for r in rows:
                r["assoc_count"] = official_counts.get(r["code"], 0) + freq_counts.get(r["code"], 0)

        return rows

    def get_code(self, code):
        """Get full details for a specific CCAM code."""
        c = self.conn.cursor()
        c.execute("SELECT * FROM ccam_codes WHERE code = ?", (code.upper(),))
        row = c.fetchone()
        return dict(row) if row else None

    def get_associations(self, code):
        """Get all associated codes (complementary gestures, anesthesia) for a code."""
        c = self.conn.cursor()
        c.execute("""
            SELECT a.associated_code, a.association_type, a.activity,
                   cc.label, cc.icr_public
            FROM associations a
            LEFT JOIN ccam_codes cc ON cc.code = a.associated_code
            WHERE a.code = ?
            ORDER BY a.association_type, a.associated_code
        """, (code.upper(),))
        return [dict(r) for r in c.fetchall()]

    def check_compatibility(self, codes):
        """Check if a set of CCAM codes are compatible with each other.
        Returns a list of issues found.
        """
        issues = []
        codes = [c.upper() for c in codes]

        cursor = self.conn.cursor()

        for i, code1 in enumerate(codes):
            # Verify code exists
            cursor.execute("SELECT code, label, date_end FROM ccam_codes WHERE code = ?", (code1,))
            row = cursor.fetchone()
            if not row:
                issues.append({
                    "type": "unknown_code",
                    "code": code1,
                    "message": f"Code {code1} non trouvé dans la base CCAM"
                })
                continue
            if row["date_end"]:
                issues.append({
                    "type": "expired_code",
                    "code": code1,
                    "message": f"Code {code1} expiré (fin de validité : {row['date_end']})"
                })

            # Check associations between codes
            for j, code2 in enumerate(codes):
                if i >= j:
                    continue

                # Check if code2 is in code1's complementary gestures
                cursor.execute("""
                    SELECT association_type, activity
                    FROM associations
                    WHERE code = ? AND associated_code = ?
                """, (code1, code2))
                assoc12 = cursor.fetchall()

                cursor.execute("""
                    SELECT association_type, activity
                    FROM associations
                    WHERE code = ? AND associated_code = ?
                """, (code2, code1))
                assoc21 = cursor.fetchall()

                if assoc12 or assoc21:
                    for a in assoc12:
                        issues.append({
                            "type": "has_association",
                            "codes": (code1, code2),
                            "association_type": a["association_type"],
                            "activity": a["activity"],
                            "message": f"{code1} → {code2} : geste complémentaire ({a['association_type']}, activité {a['activity']})"
                        })

        if not issues:
            issues.append({
                "type": "ok",
                "message": "Aucune incompatibilité détectée entre les codes sélectionnés"
            })

        return issues

    def get_billing_plan(self, code):
        """Get billing optimization plan for a CCAM code.
        Returns the main code + official ATIH associations + frequent PMSI associations.
        """
        code = code.upper()
        main = self.get_code(code)
        if not main:
            return None

        c = self.conn.cursor()

        # Official ATIH associations
        c.execute("""
            SELECT a.associated_code, a.association_type,
                   cc.label, cc.icr_public, cc.icr_private, cc.tarif_base,
                   cc.activity, cc.classant, cc.date_end,
                   cc.coding_instruction, cc.paragraph_title
            FROM associations a
            LEFT JOIN ccam_codes cc ON cc.code = a.associated_code
            WHERE a.code = ?
            ORDER BY
                CASE WHEN a.association_type = 'complementary_gesture' THEN 0 ELSE 1 END,
                COALESCE(cc.icr_public, 0) DESC
        """, (code,))

        gestures = []
        anesthesia = []
        official_codes = set()
        for row in c.fetchall():
            r = dict(row)
            official_codes.add(r["associated_code"])
            item = {
                "code": r["associated_code"],
                "label": r["label"],
                "icr_public": r["icr_public"],
                "icr_private": r["icr_private"],
                "tarif_base": r["tarif_base"],
                "activity": r["activity"],
                "classant": r["classant"],
                "date_end": r["date_end"],
                "coding_instruction": r["coding_instruction"],
                "paragraph_title": r["paragraph_title"],
                "expired": bool(r["date_end"]),
            }
            if r["association_type"] == "complementary_anesthesia":
                anesthesia.append(item)
            else:
                gestures.append(item)

        # Frequent associations from PMSI data (exclude already-listed official ones)
        c.execute("""
            SELECT fa.associated_code, fa.label, fa.icr_public, fa.confidence, fa.rank,
                   cc.tarif_base
            FROM frequent_associations fa
            LEFT JOIN ccam_codes cc ON cc.code = fa.associated_code
            WHERE fa.code = ?
            ORDER BY fa.rank
        """, (code,))

        frequent = []
        for row in c.fetchall():
            r = dict(row)
            if r["associated_code"] in official_codes:
                continue
            frequent.append({
                "code": r["associated_code"],
                "label": r["label"],
                "icr_public": r["icr_public"],
                "tarif_base": r["tarif_base"],
                "confidence": r["confidence"],
                "rank": r["rank"],
            })

        return {
            "main_code": main,
            "complementary_gestures": gestures,
            "anesthesia_codes": anesthesia,
            "frequent_associations": frequent,
        }

    def close(self):
        self.conn.close()


def format_result(result, index=None):
    """Format a search result for display."""
    prefix = f"  [{index}] " if index is not None else "  "
    code = result["code"]
    label = result["label"]
    icr = result.get("icr_public")
    chapter = result.get("paragraph_title") or result.get("subchapter_title") or result.get("chapter_title") or ""

    icr_str = f" | ICR={icr:.0f}" if icr else ""
    chap_str = f" | {chapter[:40]}" if chapter else ""

    return f"{prefix}{code}  {label[:65]}{icr_str}{chap_str}"


def cli():
    """Interactive CLI demo for CCAM search."""
    print("=" * 70)
    print("  T2A Assistant — Recherche CCAM (Prototype)")
    print("=" * 70)
    print()
    print("Commandes :")
    print("  Tapez une description pour chercher des codes CCAM")
    print("  /code XXXX001   -- Details d'un code")
    print("  /assoc XXXX001  -- Voir les gestes complementaires")
    print("  /check CODE1 CODE2 ...  -- Verifier la compatibilite")
    print("  /quit           -- Quitter")
    print()

    search = CCAMSearch()
    selected_codes = []

    while True:
        try:
            query = input("CCAM>").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not query:
            continue

        if query.lower() in ("/quit", "/q", "quit", "exit"):
            break

        # Command: code details
        if query.lower().startswith("/code "):
            code = query.split(maxsplit=1)[1].strip().upper()
            result = search.get_code(code)
            if result:
                print(f"\n  Code: {result['code']}")
                print(f"  Label: {result['label']}")
                print(f"  Chapitre: {result['chapter_title']}")
                print(f"  Sous-chapitre: {result['subchapter_title']}")
                print(f"  Paragraphe: {result['paragraph_title']}")
                print(f"  ICR public: {result['icr_public']}")
                print(f"  ICR privé: {result['icr_private']}")
                print(f"  Activité: {result['activity']} | Phase: {result['phase']}")
                print(f"  Classant: {result['classant']}")
                print(f"  Profil FG 2024: P0={result['fg2024_p0']} P1={result['fg2024_p1']} P2={result['fg2024_p2']} P3={result['fg2024_p3']}")
                if result['coding_instruction']:
                    print(f"  Consigne PMSI: {result['coding_instruction'][:200]}")
                if result['modifiers']:
                    print(f"  Modificateurs: {result['modifiers']}")
                if result['gestures_text']:
                    print(f"  Gestes complémentaires: {result['gestures_text']}")
                if result['date_end']:
                    print(f"  [WARN]EXPIRÉ (fin: {result['date_end']})")
                print()
            else:
                print(f"  Code {code} non trouvé.\n")
            continue

        # Command: associations
        if query.lower().startswith("/assoc "):
            code = query.split(maxsplit=1)[1].strip().upper()
            assocs = search.get_associations(code)
            if assocs:
                print(f"\n  Associations pour {code} :")
                for a in assocs:
                    label = a['label'][:50] if a['label'] else "?"
                    print(f"    {a['associated_code']}  {label}  ({a['association_type']}, act. {a['activity']})")
                print()
            else:
                print(f"  Aucune association trouvée pour {code}.\n")
            continue

        # Command: compatibility check
        if query.lower().startswith("/check "):
            codes = query.split()[1:]
            codes = [c.upper() for c in codes]
            print(f"\n  Vérification de compatibilité : {', '.join(codes)}")
            issues = search.check_compatibility(codes)
            for issue in issues:
                if issue["type"] == "ok":
                    print(f"  [OK]{issue['message']}")
                elif issue["type"] == "unknown_code":
                    print(f"  [ERR]{issue['message']}")
                elif issue["type"] == "expired_code":
                    print(f"  [WARN]{issue['message']}")
                elif issue["type"] == "has_association":
                    print(f"  [INFO]{issue['message']}")
            print()
            continue

        # Default: search
        results = search.search(query, limit=10)
        if results:
            print(f"\n  {len(results)} résultats pour '{query}' :\n")
            for i, r in enumerate(results, 1):
                print(format_result(r, i))
            print()
            print("  Tip: /code XXXX001 pour les détails, /check CODE1 CODE2 pour la compatibilité")
            print()
        else:
            print(f"  Aucun résultat pour '{query}'. Essayez des termes plus génériques.\n")

    search.close()
    print("\nÀ bientôt !")


if __name__ == "__main__":
    cli()
