"""
T2A Assistant — Web API
FastAPI backend for CCAM search + compatibility check.
"""

from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from ccam_search import CCAMSearch

app = FastAPI(title="T2A Assistant", version="0.1.0")
search = CCAMSearch()

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/api/search")
def api_search(q: str = Query(..., min_length=1), limit: int = Query(15, ge=1, le=50)):
    """Search CCAM codes by description."""
    results = search.search(q, limit=limit)
    return {"query": q, "count": len(results), "results": results}


@app.get("/api/code/{code}")
def api_code(code: str):
    """Get full details for a CCAM code."""
    result = search.get_code(code)
    if not result:
        return {"error": f"Code {code} non trouve"}
    return result


@app.get("/api/associations/{code}")
def api_associations(code: str):
    """Get associations for a CCAM code."""
    assocs = search.get_associations(code)
    return {"code": code, "count": len(assocs), "associations": assocs}


@app.get("/api/check")
def api_check(codes: str = Query(..., description="Comma-separated CCAM codes")):
    """Check compatibility between CCAM codes."""
    code_list = [c.strip().upper() for c in codes.split(",") if c.strip()]
    if len(code_list) < 2:
        return {"error": "Au moins 2 codes requis"}
    issues = search.check_compatibility(code_list)
    return {"codes": code_list, "issues": issues}


@app.get("/api/billing-plan/{code}")
def api_billing_plan(code: str):
    """Get billing optimization plan for a CCAM code.
    Returns the main code + all complementary gestures and anesthesia codes.
    """
    plan = search.get_billing_plan(code)
    if not plan:
        return {"error": f"Code {code.upper()} non trouve dans la base CCAM"}
    return plan


@app.get("/api/stats")
def api_stats():
    """Get database statistics."""
    c = search.conn.cursor()
    c.execute("SELECT COUNT(*) FROM ccam_codes WHERE date_end IS NULL")
    active = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM associations")
    assocs = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM frequent_associations")
    freq = c.fetchone()[0]
    return {"active_codes": active, "associations": assocs, "frequent_associations": freq, "version": "CCAM 2025 v4"}


# Serve static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))
