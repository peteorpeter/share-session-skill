#!/usr/bin/env python3
"""
Parse a Claude Code session JSONL file into structured data.

Usage:
    python parse.py SESSION_PATH [--json] [--stats-only]

Examples:
    python parse.py /path/to/session.jsonl --json
    python parse.py /path/to/session.jsonl --stats-only
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

# Add script directory to path for imports
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

from utils import (
    read_jsonl_file,
    parse_timestamp,
    format_timestamp,
    format_duration,
    truncate_text,
    json_output,
)


def extract_tool_calls(content: list) -> list[dict]:
    """Extract tool calls from assistant message content."""
    tool_calls = []

    for item in content:
        if isinstance(item, dict) and item.get("type") == "tool_use":
            tool_call = {
                "id": item.get("id", ""),
                "name": item.get("name", ""),
                "input": item.get("input", {}),
            }
            tool_calls.append(tool_call)

    return tool_calls


def extract_tool_results(content: list) -> dict[str, str]:
    """Extract tool results mapped by tool_use_id."""
    results = {}

    for item in content:
        if isinstance(item, dict) and item.get("type") == "tool_result":
            tool_id = item.get("tool_use_id", "")
            result_content = item.get("content", "")

            if isinstance(result_content, list):
                # Extract text from content blocks
                texts = []
                for block in result_content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        texts.append(block.get("text", ""))
                result_content = "\n".join(texts)

            results[tool_id] = str(result_content)

    return results


def extract_text_content(content) -> str:
    """Extract text from message content (string or list)."""
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    texts.append(item.get("text", ""))
                elif item.get("type") == "thinking":
                    # Skip thinking blocks in output
                    pass
        return "\n".join(texts)

    return ""


def parse_session(session_path: str) -> Optional[dict]:
    """
    Parse a session JSONL file into structured data.

    Returns a dict with:
        - metadata: date, project, duration, version
        - turns: list of conversation turns
        - stats: tool call counts, token usage, files, commands
    """
    filepath = Path(session_path)
    if not filepath.exists():
        return None

    records = read_jsonl_file(filepath)
    if not records:
        return None

    # Extract basic metadata - look through records for user message with metadata
    metadata = {
        "session_id": "",
        "cwd": "",
        "version": "",
        "git_branch": "",
    }
    for record in records:
        if record.get("type") == "user":
            if not metadata["session_id"] and record.get("sessionId"):
                metadata["session_id"] = record.get("sessionId", "")
            if not metadata["cwd"] and record.get("cwd"):
                metadata["cwd"] = record.get("cwd", "")
            if not metadata["version"] and record.get("version"):
                metadata["version"] = record.get("version", "")
            if not metadata["git_branch"] and record.get("gitBranch"):
                metadata["git_branch"] = record.get("gitBranch", "")
            # Stop once we have all metadata
            if all(metadata.values()):
                break

    # Build turns from records
    turns = []
    current_turn = None
    tool_results = {}  # Map tool_use_id to results

    # Stats tracking
    total_input_tokens = 0
    total_output_tokens = 0
    total_cache_read = 0
    total_cache_create = 0
    tool_counts = {}
    files_read = set()
    files_edited = set()
    files_created = set()
    commands_run = []
    first_timestamp = None
    last_timestamp = None

    for record in records:
        record_type = record.get("type")
        timestamp_str = record.get("timestamp")

        if timestamp_str:
            ts = parse_timestamp(timestamp_str)
            if ts:
                if first_timestamp is None:
                    first_timestamp = ts
                last_timestamp = ts

        if record_type == "user":
            # Start a new turn
            if current_turn:
                turns.append(current_turn)

            message = record.get("message", {})
            content = message.get("content", "")

            # Extract any tool results from user message (they come as user messages)
            if isinstance(content, list):
                new_results = extract_tool_results(content)
                tool_results.update(new_results)

            user_text = extract_text_content(content)

            # Skip empty continuation messages
            if not user_text.strip():
                continue

            current_turn = {
                "user_message": user_text,
                "assistant_response": "",
                "tool_calls": [],
                "timestamp": timestamp_str,
                "duration_seconds": 0,
            }

        elif record_type == "assistant":
            if current_turn is None:
                continue

            message = record.get("message", {})
            content = message.get("content", [])

            # Extract assistant text
            assistant_text = extract_text_content(content)
            current_turn["assistant_response"] = assistant_text

            # Extract tool calls
            tool_calls = extract_tool_calls(content)
            for tc in tool_calls:
                tool_name = tc["name"]
                tool_input = tc["input"]
                tool_id = tc["id"]

                # Count tool usage
                tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1

                # Track specific tool effects
                if tool_name == "Read":
                    file_path = tool_input.get("file_path", "")
                    if file_path:
                        files_read.add(file_path)

                elif tool_name in ("Edit", "Write"):
                    file_path = tool_input.get("file_path", "")
                    if file_path:
                        if tool_name == "Write":
                            files_created.add(file_path)
                        else:
                            files_edited.add(file_path)

                elif tool_name == "Bash":
                    command = tool_input.get("command", "")
                    if command:
                        commands_run.append(command)

                # Add result if available
                tc["result"] = tool_results.get(tool_id, "")

            current_turn["tool_calls"].extend(tool_calls)

            # Extract token usage
            usage = message.get("usage", {})
            total_input_tokens += usage.get("input_tokens", 0)
            total_output_tokens += usage.get("output_tokens", 0)
            total_cache_read += usage.get("cache_read_input_tokens", 0)
            total_cache_create += usage.get("cache_creation_input_tokens", 0)

    # Don't forget the last turn
    if current_turn:
        turns.append(current_turn)

    # Calculate duration
    duration_seconds = 0
    if first_timestamp and last_timestamp:
        duration_seconds = (last_timestamp - first_timestamp).total_seconds()

    # Calculate turn durations (approximate)
    for i, turn in enumerate(turns):
        turn_ts = parse_timestamp(turn.get("timestamp", ""))
        if turn_ts and i + 1 < len(turns):
            next_ts = parse_timestamp(turns[i + 1].get("timestamp", ""))
            if next_ts:
                turn["duration_seconds"] = (next_ts - turn_ts).total_seconds()

    metadata["date"] = first_timestamp.isoformat() if first_timestamp else None
    metadata["date_formatted"] = format_timestamp(first_timestamp) if first_timestamp else "Unknown"
    metadata["duration_seconds"] = duration_seconds
    metadata["duration_formatted"] = format_duration(duration_seconds)

    stats = {
        "turn_count": len(turns),
        "tool_counts": tool_counts,
        "total_tool_calls": sum(tool_counts.values()),
        "tokens": {
            "input": total_input_tokens,
            "output": total_output_tokens,
            "cache_read": total_cache_read,
            "cache_create": total_cache_create,
        },
        "files_read": sorted(list(files_read)),
        "files_edited": sorted(list(files_edited)),
        "files_created": sorted(list(files_created)),
        "commands_run": commands_run,
        "unique_files_read": len(files_read),
        "unique_files_edited": len(files_edited),
        "unique_files_created": len(files_created),
        "commands_count": len(commands_run),
    }

    return {
        "metadata": metadata,
        "turns": turns,
        "stats": stats,
    }


def format_stats(stats: dict, metadata: dict) -> str:
    """Format session stats as human-readable text."""
    lines = []

    lines.append(f"Session: {metadata.get('date_formatted', 'Unknown')}")
    lines.append(f"Project: {metadata.get('cwd', 'Unknown')}")
    lines.append(f"Duration: {metadata.get('duration_formatted', 'Unknown')}")
    lines.append(f"Version: {metadata.get('version', 'Unknown')}")
    lines.append("")

    lines.append(f"Conversation turns: {stats['turn_count']}")
    lines.append(f"Total tool calls: {stats['total_tool_calls']}")
    lines.append("")

    if stats["tool_counts"]:
        lines.append("Tool usage:")
        for tool, count in sorted(stats["tool_counts"].items(), key=lambda x: -x[1]):
            lines.append(f"  {tool}: {count}")
        lines.append("")

    lines.append(f"Files read: {stats['unique_files_read']}")
    lines.append(f"Files edited: {stats['unique_files_edited']}")
    lines.append(f"Files created: {stats['unique_files_created']}")
    lines.append(f"Commands run: {stats['commands_count']}")
    lines.append("")

    tokens = stats["tokens"]
    lines.append("Token usage:")
    lines.append(f"  Input: {tokens['input']:,}")
    lines.append(f"  Output: {tokens['output']:,}")
    lines.append(f"  Cache read: {tokens['cache_read']:,}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Parse a Claude Code session JSONL file"
    )
    parser.add_argument(
        "session_path",
        type=str,
        help="Path to the session JSONL file",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="Only output statistics, not full turns",
    )

    args = parser.parse_args()

    result = parse_session(args.session_path)

    if result is None:
        print(f"Error: Could not parse session at {args.session_path}", file=sys.stderr)
        sys.exit(1)

    if args.stats_only:
        if args.json:
            output = {
                "metadata": result["metadata"],
                "stats": result["stats"],
            }
            print(json_output(output))
        else:
            print(format_stats(result["stats"], result["metadata"]))
    else:
        if args.json:
            print(json_output(result))
        else:
            # Human-readable output
            print(format_stats(result["stats"], result["metadata"]))
            print("\n" + "=" * 60 + "\n")
            for i, turn in enumerate(result["turns"], 1):
                print(f"Turn {i}:")
                print(f"User: {truncate_text(turn['user_message'], 200)}")
                print(f"Assistant: {truncate_text(turn['assistant_response'], 200)}")
                print(f"Tool calls: {len(turn['tool_calls'])}")
                print()


if __name__ == "__main__":
    main()
