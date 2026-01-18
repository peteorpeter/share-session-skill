#!/usr/bin/env python3
"""
Shared utilities for session-explorer skill.
"""

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any

# Claude session storage location
CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"
HISTORY_FILE = CLAUDE_DIR / "history.jsonl"


def get_claude_dir() -> Path:
    """Get the Claude configuration directory."""
    return CLAUDE_DIR


def get_projects_dir() -> Path:
    """Get the projects directory where sessions are stored."""
    return PROJECTS_DIR


def cwd_to_project_path(cwd: str) -> Path:
    """
    Convert a working directory path to its Claude project directory path.

    Example: /Users/jonespx6/myproject -> ~/.claude/projects/-Users-jonespx6-myproject/
    """
    # Replace path separators with dashes, remove leading slash
    normalized = cwd.lstrip("/").replace("/", "-")
    return PROJECTS_DIR / f"-{normalized}"


def project_path_to_cwd(project_path: Path) -> str:
    """
    Convert a Claude project directory path back to the original working directory.

    Example: ~/.claude/projects/-Users-jonespx6-myproject/ -> /Users/jonespx6/myproject
    """
    name = project_path.name
    if name.startswith("-"):
        name = name[1:]
    # Replace dashes with slashes
    return "/" + name.replace("-", "/")


def get_project_dir_for_scope(scope: str, cwd: Optional[str] = None) -> list[Path]:
    """
    Get project directories for a given scope.

    Args:
        scope: One of 'project', 'parent', 'children', 'personal', 'all'
        cwd: Current working directory (required for project/parent/children scope)

    Returns:
        List of project directory paths to search
    """
    if scope == "personal" or scope == "all":
        # All project directories
        if PROJECTS_DIR.exists():
            return [d for d in PROJECTS_DIR.iterdir() if d.is_dir()]
        return []

    if not cwd:
        cwd = os.getcwd()

    dirs = []

    if scope == "project":
        project_dir = cwd_to_project_path(cwd)
        if project_dir.exists():
            dirs.append(project_dir)

    elif scope == "parent":
        parent = str(Path(cwd).parent)
        parent_dir = cwd_to_project_path(parent)
        if parent_dir.exists():
            dirs.append(parent_dir)

    elif scope == "children":
        # Find all project directories that are children of the current directory
        # e.g., if cwd is /Users/jonespx6, find -Users-jonespx6-* directories
        cwd_prefix = cwd_to_project_path(cwd).name  # e.g., "-Users-jonespx6"
        if PROJECTS_DIR.exists():
            for d in PROJECTS_DIR.iterdir():
                if d.is_dir() and d.name.startswith(cwd_prefix + "-"):
                    dirs.append(d)

    return dirs


def is_valid_session_file(filepath: Path) -> bool:
    """
    Check if a file is a valid user session (not an agent, warmup, etc.)
    """
    name = filepath.name

    # Must be a JSONL file
    if not name.endswith(".jsonl"):
        return False

    # Exclude agent sub-sessions
    if name.startswith("agent-"):
        return False

    # Exclude warmup sessions
    if "warmup" in name.lower():
        return False

    # Check file size (exclude tiny files < 1KB)
    try:
        if filepath.stat().st_size < 1024:
            return False
    except OSError:
        return False

    return True


def parse_timestamp(ts: str) -> Optional[datetime]:
    """Parse an ISO 8601 timestamp string."""
    try:
        # Handle various ISO formats
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def format_timestamp(dt: datetime) -> str:
    """Format a datetime for display."""
    return dt.strftime("%b %d, %Y, %-I:%M %p")


def format_duration(seconds: float) -> str:
    """Format a duration in seconds to human-readable string."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes}m"
    else:
        hours = int(seconds / 3600)
        minutes = int((seconds % 3600) / 60)
        if minutes > 0:
            return f"{hours}h {minutes}m"
        return f"{hours}h"


def parse_relative_date(date_str: str) -> Optional[datetime]:
    """
    Parse a relative date string like 'yesterday', 'last week', '3 days ago'.
    Returns the start of that day.
    """
    date_str = date_str.lower().strip()
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if date_str == "today":
        return today
    elif date_str == "yesterday":
        return today - timedelta(days=1)
    elif date_str == "last week":
        return today - timedelta(weeks=1)
    elif date_str == "last month":
        return today - timedelta(days=30)
    elif "days ago" in date_str:
        match = re.match(r"(\d+)\s*days?\s*ago", date_str)
        if match:
            days = int(match.group(1))
            return today - timedelta(days=days)
    elif "weeks ago" in date_str:
        match = re.match(r"(\d+)\s*weeks?\s*ago", date_str)
        if match:
            weeks = int(match.group(1))
            return today - timedelta(weeks=weeks)

    # Try parsing as absolute date
    for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%m/%d", "%b %d", "%B %d"]:
        try:
            parsed = datetime.strptime(date_str, fmt)
            # If year not specified, use current year
            if parsed.year == 1900:
                parsed = parsed.replace(year=now.year)
            return parsed
        except ValueError:
            continue

    return None


def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text to max_length, adding ellipsis if needed."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3].rstrip() + "..."


def json_output(data: Any) -> str:
    """Format data as JSON for script output."""
    return json.dumps(data, indent=2, default=str)


def read_jsonl_file(filepath: Path) -> list[dict]:
    """Read a JSONL file and return list of parsed objects."""
    records = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except (OSError, IOError):
        pass
    return records


def get_session_quick_metadata(filepath: Path) -> Optional[dict]:
    """
    Get quick metadata from a session file without full parsing.
    Reads just enough to get date, preview, and basic stats.
    """
    first_user_message = None
    first_timestamp = None
    last_timestamp = None
    message_count = 0
    project_cwd = ""

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)

                    # Track timestamps
                    ts = record.get("timestamp")
                    if ts:
                        parsed_ts = parse_timestamp(ts)
                        if parsed_ts:
                            if first_timestamp is None:
                                first_timestamp = parsed_ts
                            last_timestamp = parsed_ts

                    # Get cwd from user messages (where it's stored)
                    if not project_cwd and record.get("type") == "user":
                        project_cwd = record.get("cwd", "")

                    # Get first user message for preview (skip system/command tags)
                    if first_user_message is None:
                        if record.get("type") == "user":
                            msg = record.get("message", {})
                            content = msg.get("content", "")
                            text = ""
                            if isinstance(content, str):
                                text = content.strip()
                            elif isinstance(content, list):
                                for part in content:
                                    if isinstance(part, dict) and part.get("type") == "text":
                                        text = part.get("text", "").strip()
                                        break
                            # Skip messages that are just system tags or commands
                            if text and not text.startswith("<") and not text.startswith("/"):
                                first_user_message = text

                    # Count messages
                    if record.get("type") in ("user", "assistant"):
                        message_count += 1

                except json.JSONDecodeError:
                    continue
    except (OSError, IOError):
        return None

    # Validate we have minimum data
    if first_timestamp is None or first_timestamp.year < 2020:
        return None

    # Calculate duration
    duration_seconds = 0
    if first_timestamp and last_timestamp:
        duration_seconds = (last_timestamp - first_timestamp).total_seconds()

    return {
        "path": str(filepath),
        "date": first_timestamp.isoformat() if first_timestamp else None,
        "date_formatted": format_timestamp(first_timestamp) if first_timestamp else "Unknown",
        "duration_seconds": duration_seconds,
        "duration_formatted": format_duration(duration_seconds),
        "preview": truncate_text(first_user_message or "(no preview)", 80),
        "message_count": message_count,
        "project_cwd": project_cwd,
        "project_short": Path(project_cwd).name if project_cwd else "unknown",
    }
