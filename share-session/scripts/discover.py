#!/usr/bin/env python3
"""
Discover and list Claude Code sessions.

Usage:
    python discover.py [--scope SCOPE] [--limit N] [--after DATE] [--before DATE] [--json]

Scopes:
    project  - Sessions from current working directory
    parent   - Sessions from parent directory
    children - Sessions from subdirectories of cwd (e.g., nested repos)
    personal - All sessions in ~/.claude/projects
    all      - All sessions (same as personal)

Examples:
    python discover.py --scope personal --limit 10
    python discover.py --scope project --json
    python discover.py --after yesterday --limit 5
"""

import argparse
import sys
from pathlib import Path

# Add script directory to path for imports
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

from utils import (
    get_project_dir_for_scope,
    is_valid_session_file,
    get_session_quick_metadata,
    parse_relative_date,
    parse_timestamp,
    json_output,
)


def discover_sessions(
    scope: str = "personal",
    limit: int = 20,
    offset: int = 0,
    after_date: str = None,
    before_date: str = None,
    cwd: str = None,
) -> list[dict]:
    """
    Discover sessions matching the given criteria.

    Returns list of session metadata dicts sorted by date (newest first).
    """
    # Get directories to search
    project_dirs = get_project_dir_for_scope(scope, cwd)

    if not project_dirs:
        return []

    # Parse date filters
    after_dt = parse_relative_date(after_date) if after_date else None
    before_dt = parse_relative_date(before_date) if before_date else None

    # Collect all session files
    session_files = []
    for project_dir in project_dirs:
        if not project_dir.exists():
            continue

        # Find JSONL files (non-recursive for main sessions)
        for filepath in project_dir.glob("*.jsonl"):
            if is_valid_session_file(filepath):
                session_files.append(filepath)

    # Get metadata for each session
    sessions = []
    for filepath in session_files:
        metadata = get_session_quick_metadata(filepath)
        if metadata is None:
            continue

        # Apply date filters
        if after_dt or before_dt:
            session_date = parse_timestamp(metadata.get("date", ""))
            if session_date:
                if after_dt and session_date < after_dt:
                    continue
                if before_dt and session_date > before_dt:
                    continue

        sessions.append(metadata)

    # Sort by date (newest first)
    sessions.sort(key=lambda s: s.get("date", ""), reverse=True)

    # Apply offset and limit
    if offset > 0:
        sessions = sessions[offset:]
    if limit > 0:
        sessions = sessions[:limit]

    return sessions


def format_sessions_table(sessions: list[dict]) -> str:
    """Format sessions as a human-readable table."""
    if not sessions:
        return "No sessions found."

    lines = []
    lines.append("| # | Date | Project | Preview | Duration |")
    lines.append("|---|------|---------|---------|----------|")

    for i, session in enumerate(sessions, 1):
        date = session.get("date_formatted", "Unknown")
        project = session.get("project_short", "unknown")
        preview = session.get("preview", "")
        duration = session.get("duration_formatted", "")

        # Truncate for table display
        if len(project) > 20:
            project = project[:17] + "..."
        if len(preview) > 40:
            preview = preview[:37] + "..."

        lines.append(f"| {i} | {date} | {project} | {preview} | {duration} |")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Discover and list Claude Code sessions"
    )
    parser.add_argument(
        "--scope",
        choices=["project", "parent", "children", "personal", "all"],
        default="personal",
        help="Scope: project, parent, children (subdirs), personal, all (default: personal)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of sessions to return (default: 20, 0 for all)",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Number of sessions to skip (for pagination)",
    )
    parser.add_argument(
        "--after",
        type=str,
        help="Only show sessions after this date (e.g., 'yesterday', '2024-01-01')",
    )
    parser.add_argument(
        "--before",
        type=str,
        help="Only show sessions before this date",
    )
    parser.add_argument(
        "--cwd",
        type=str,
        help="Working directory for project/parent scope (default: current directory)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    args = parser.parse_args()

    sessions = discover_sessions(
        scope=args.scope,
        limit=args.limit,
        offset=args.offset,
        after_date=args.after,
        before_date=args.before,
        cwd=args.cwd,
    )

    if args.json:
        print(json_output({"sessions": sessions, "count": len(sessions)}))
    else:
        print(format_sessions_table(sessions))
        print(f"\nFound {len(sessions)} session(s)")


if __name__ == "__main__":
    main()
