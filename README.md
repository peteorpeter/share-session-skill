# Share Session (Claude Code Skill)

A structured `/share-session` wizard for creating shareable summaries of Claude Code sessions. It helps you find a session, draft a human-friendly summary focused on how to work effectively with AI agents, and export a polished Markdown
report.

## Features

- 4-step wizard: Find → Select → Draft → Output
- Session discovery across projects (`personal`, `project`, `children`, etc.)
- Keyword search with context snippets
- Structured summary with icon tags for learning moments and doc updates
- Markdown export with usage stats and cost estimates

## Installation

### Option A: Direct ZIP download (no git)

1. Download the ZIP from GitHub:
   https://codeload.github.com/peteorpeter/share-session-skill/zip/refs/heads/main

2. Unzip into your Claude skills directory:

```bash
unzip ~/Downloads/share-session-skill.zip -d ~/.claude/skills/
```

> Note: GitHub usually names the folder share-session-skill-main/. If you want it to be share-session/, rename it after unzip.

### Option B: Clone

```bash
git clone https://github.com/peteorpeter/share-session-skill.git
mkdir -p ~/.claude/skills/share-session
cp -R share-session-skill/* ~/.claude/skills/share-session/
```

## Usage

In Claude Code, run:

/share-session

Follow the prompts to select a session and generate a Markdown summary.

## Scripts (Optional CLI)

The skill includes helper scripts if you want to run them directly:

# List recent sessions
python3 ~/.claude/skills/share-session/scripts/discover.py --scope personal --limit 10

# Search for a keyword
python3 ~/.claude/skills/share-session/scripts/search.py "auth bug" --scope all

# Parse a session into structured JSON
python3 ~/.claude/skills/share-session/scripts/parse.py /path/to/session.jsonl --json

## Output Format

The exported Markdown includes:

- Overview sentence
- Key actions and decisions
- Tagged moments (🚧 💡 🤖 📄 📝)
- Concise conversation summary
- Usage stats and token cost estimates

## Privacy

This skill reads local Claude Code session files under ~/.claude/projects and saves markdown files locally. It does not send data anywhere by itself.
