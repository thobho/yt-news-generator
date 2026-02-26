from pathlib import Path

from fastapi import APIRouter, Query

router = APIRouter()

LOG_DIR = Path(__file__).resolve().parents[1] / "logs"


@router.get("/logs")
async def get_logs(
    file: str = Query("app", pattern="^(app|error)$"),
    lines: int = Query(500, ge=1, le=5000),
    search: str = Query(None),
):
    log_path = LOG_DIR / f"{file}.log"
    if not log_path.exists():
        return {"lines": [], "file": file, "total_lines": 0}

    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        all_lines = f.readlines()

    result = [ln.rstrip() for ln in all_lines if ln.strip()]

    if search:
        search_lower = search.lower()
        result = [ln for ln in result if search_lower in ln.lower()]

    return {
        "lines": result[-lines:],
        "file": file,
        "total_lines": len(result),
    }
