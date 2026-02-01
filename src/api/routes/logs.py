"""Logs API routes for viewing application logs."""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from src.logging import LogConfig

router = APIRouter(prefix="/api/logs", tags=["logs"])


class LogEntry(BaseModel):
    """Parsed log entry."""
    timestamp: str
    level: str
    event: str
    message: Optional[str] = None
    data: dict = {}


class LogResponse(BaseModel):
    """Response containing log entries."""
    logs: list[LogEntry]
    total: int
    has_more: bool


def parse_log_line(line: str) -> Optional[LogEntry]:
    """Parse a single log line into a LogEntry.

    Handles both JSON and text format logs.
    """
    line = line.strip()
    if not line:
        return None

    # Try JSON format first
    try:
        data = json.loads(line)
        return LogEntry(
            timestamp=data.get("timestamp", data.get("@timestamp", "")),
            level=data.get("level", "info").upper(),
            event=data.get("event", ""),
            message=data.get("message", data.get("event", "")),
            data={k: v for k, v in data.items()
                  if k not in ("timestamp", "@timestamp", "level", "event", "message")},
        )
    except json.JSONDecodeError:
        pass

    # Try text format: [LEVEL] timestamp - event: message
    text_pattern = r"\[(\w+)\]\s*(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[^\s]*)\s*-?\s*(.+)"
    match = re.match(text_pattern, line)
    if match:
        level, timestamp, rest = match.groups()
        return LogEntry(
            timestamp=timestamp,
            level=level.upper(),
            event=rest.split(":")[0] if ":" in rest else rest,
            message=rest,
            data={},
        )

    # Fallback: treat entire line as message
    return LogEntry(
        timestamp=datetime.now().isoformat(),
        level="INFO",
        event="log",
        message=line,
        data={},
    )


def read_log_file(
    file_path: Path,
    limit: int = 100,
    offset: int = 0,
    level_filter: Optional[str] = None,
    search: Optional[str] = None,
) -> tuple[list[LogEntry], int, bool]:
    """Read and parse log file with filtering.

    Returns:
        Tuple of (entries, total_count, has_more)
    """
    if not file_path.exists():
        return [], 0, False

    entries: list[LogEntry] = []
    total = 0

    # Read file in reverse order (newest first)
    with open(file_path, "r") as f:
        lines = f.readlines()

    # Process in reverse (newest first)
    for line in reversed(lines):
        entry = parse_log_line(line)
        if not entry:
            continue

        # Apply level filter
        if level_filter and entry.level.upper() != level_filter.upper():
            continue

        # Apply search filter
        if search:
            search_lower = search.lower()
            searchable = f"{entry.event} {entry.message} {json.dumps(entry.data)}".lower()
            if search_lower not in searchable:
                continue

        total += 1

        # Apply pagination
        if total <= offset:
            continue

        if len(entries) < limit:
            entries.append(entry)

    has_more = total > offset + limit
    return entries, total, has_more


@router.get("", response_model=LogResponse)
async def get_logs(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    level: Optional[str] = Query(None, description="Filter by log level (DEBUG, INFO, WARN, ERROR)"),
    search: Optional[str] = Query(None, description="Search in log messages"),
    file: str = Query("app", description="Log file to read (app or error)"),
):
    """Get application logs with filtering and pagination.

    Args:
        limit: Maximum number of entries to return
        offset: Number of entries to skip
        level: Filter by log level
        search: Search term to filter logs
        file: Which log file to read (app or error)

    Returns:
        Log entries with pagination info
    """
    log_dir = LogConfig.LOG_DIR

    if file == "error":
        log_path = log_dir / "error.log"
    else:
        log_path = log_dir / "app.log"

    entries, total, has_more = read_log_file(
        log_path,
        limit=limit,
        offset=offset,
        level_filter=level,
        search=search,
    )

    return LogResponse(
        logs=entries,
        total=total,
        has_more=has_more,
    )


@router.get("/stats")
async def get_log_stats():
    """Get log file statistics.

    Returns:
        Statistics about log files
    """
    log_dir = LogConfig.LOG_DIR

    stats = {
        "log_dir": str(log_dir),
        "files": [],
    }

    for log_file in ["app.log", "error.log"]:
        file_path = log_dir / log_file
        if file_path.exists():
            stat = file_path.stat()
            stats["files"].append({
                "name": log_file,
                "size_bytes": stat.st_size,
                "size_human": f"{stat.st_size / 1024:.1f} KB" if stat.st_size < 1024 * 1024
                              else f"{stat.st_size / 1024 / 1024:.1f} MB",
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })

    return stats
