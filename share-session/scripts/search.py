#!/usr/bin/env python3
"""
Search Claude Code sessions for keywords.

Usage:
    python search.py QUERY [--scope SCOPE] [--after DATE] [--before DATE] [--limit N] [--json]

Examples:
    python search.py "authentication" --scope all --json
    python search.py "bug fix" --after yesterday
    python search.py "refactor" --scope project --limit 5
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Optional

# Add script directory to path for imports
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

from utils import (
    get_project_dir_for_scope,
    is_valid_session_file,
    get_session_quick_metadata,
    read_jsonl_file,
    parse_relative_date,
    parse_timestamp,
    truncate_text,
    json_output,
)


def extract_text_from_record(record: dict) -> str:
    """Extract searchable text from a record."""
    texts = []

    # Get message content
    message = record.get("message", {})
    content = message.get("content", "")

    if isinstance(content, str):
        texts.append(content)
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    texts.append(item.get("text", ""))
                elif item.get("type") == "tool_use":
                    # Include tool inputs in search
                    tool_input = item.get("input", {})
                    if isinstance(tool_input, dict):
                        for v in tool_input.values():
                            if isinstance(v, str):
                                texts.append(v)
                elif item.get("type") == "tool_result":
                    # Include tool results
                    result = item.get("content", "")
                    if isinstance(result, str):
                        texts.append(result)
                    elif isinstance(result, list):
                        for block in result:
                            if isinstance(block, dict) and block.get("type") == "text":
                                texts.append(block.get("text", ""))

    return " ".join(texts)


def search_session(filepath: Path, query: str, case_insensitive: bool = True) -> list[dict]:
    """
    Search a session file for the query.

    Returns list of matching context snippets with metadata.
    """
    records = read_jsonl_file(filepath)
    if not records:
        return []

    matches = []
    pattern = re.compile(re.escape(query), re.IGNORECASE if case_insensitive else 0)

    for record in records:
        record_type = record.get("type")
        if record_type not in ("user", "assistant"):
            continue

        text = extract_text_from_record(record)
        if not text:
            continue

        # Search for query
        match = pattern.search(text)
        if match:
            # Get context around match
            start = max(0, match.start() - 50)
            end = min(len(text), match.end() + 100)
            context = text[start:end]

            # Clean up context
            context = context.replace("\n", " ").strip()
            if start > 0:
                context = "..." + context
            if end < len(text):
                context = context + "..."

            matches.append({
                "type": record_type,
                "context": context,
                "timestamp": record.get("timestamp"),
            })

    return matches


def search_sessions(
    query: str,
    scope: str = "all",
    after_date: str = None,
    before_date: str = None,
    limit: int = 10,
    cwd: str = None,
) -> list[dict]:
    """
    Search sessions for a query string.

    Returns list of matching sessions with context snippets.
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

        for filepath in project_dir.glob("*.jsonl"):
            if is_valid_session_file(filepath):
                session_files.append(filepath)

    # Search each session
    results = []
    for filepath in session_files:
        # Get quick metadata for date filtering
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

        # Search the session
        matches = search_session(filepath, query)
        if matches:
            results.append({
                "session": metadata,
                "matches": matches[:5],  # Limit matches per session
                "match_count": len(matches),
            })

    # Sort by date (newest first)
    results.sort(key=lambda r: r["session"].get("date", ""), reverse=True)

    # Apply limit
    if limit > 0:
        results = results[:limit]

    return results


def format_search_results(results: list[dict], query: str) -> str:
    """Format search results as human-readable text."""
    if not results:
        return f"No sessions found matching '{query}'"

    lines = []
    lines.append(f"Found {len(results)} session(s) matching '{query}':\n")

    for i, result in enumerate(results, 1):
        session = result["session"]
        matches = result["matches"]

        lines.append(f"{i}. {session.get('date_formatted', 'Unknown')} - {session.get('project_short', 'unknown')}")
        lines.append(f"   Preview: {session.get('preview', '')}")
        lines.append(f"   Matches: {result['match_count']}")

        # Show first match context
        if matches:
            first_match = matches[0]
            context = truncate_text(first_match.get("context", ""), 100)
            lines.append(f"   Context: \"{context}\"")

        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Search Claude Code sessions for keywords"
    )
    parser.add_argument(
        "query",
        type=str,
        help="Search query",
    )
    parser.add_argument(
        "--scope",
        choices=["project", "parent", "children", "personal", "all"],
        default="all",
        help="Scope: project, parent, children (subdirs), personal, all (default: all)",
    )
    parser.add_argument(
        "--after",
        type=str,
        help="Only search sessions after this date",
    )
    parser.add_argument(
        "--before",
        type=str,
        help="Only search sessions before this date",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of matching sessions (default: 10)",
    )
    parser.add_argument(
        "--cwd",
        type=str,
        help="Working directory for scope resolution",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    args = parser.parse_args()

    results = search_sessions(
        query=args.query,
        scope=args.scope,
        after_date=args.after,
        before_date=args.before,
        limit=args.limit,
        cwd=args.cwd,
    )

    if args.json:
        print(json_output({
            "query": args.query,
            "results": results,
            "count": len(results),
        }))
    else:
        print(format_search_results(results, args.query))


if __name__ == "__main__":
    main()
