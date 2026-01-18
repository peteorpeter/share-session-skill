---
name: share-session
description: |
  Generate shareable summaries of Claude Code sessions. A structured wizard that helps you find a session, draft a summary, and export to markdown. Use when you want to share what you worked on with colleagues, create documentation of completed work, or export session history. Focused on teaching humans how to work effectively with AI coding agents.
---

# Share Session

A structured wizard for creating shareable session summaries.

## Flow

This skill follows a **4-step wizard** flow. Execute each step in order, waiting for user input between steps.

```
Step 1: FIND      →  Step 2: SELECT   →  Step 3: DRAFT    →  Step 4: OUTPUT
(how to find)        (pick session)      (review/edit)       (export file)
```

## Step 1: Choose How to Find Sessions

Ask how to find sessions.

**Use AskUserQuestion** with options:

```
## How would you like to find a session?

( ) Browse recent sessions (recommended)
( ) Find a specific session (describe what you're looking for)
```

### Path A: Browse Recent Sessions

If user selects "Browse recent", ask for scope:

**Use AskUserQuestion**:
```
( ) All projects
( ) Current project only
( ) Browse child directories
```

**Scope options:**
- **personal** - All sessions in ~/.claude/projects (default, most common)
- **project** - Sessions from current working directory only
- **children** - Sessions from subdirectories (e.g., if in ~/ and want ~/myproject sessions)

If user selects "children", run discover to find available project directories:

```bash
python3 ~/.claude/skills/share-session/scripts/discover.py --scope children --limit 20 --json
```

Then present unique projects for selection.

### Path B: Find a Specific Session

If user selects "Find a specific session", ask them to describe what they're looking for:

```
Describe the session you're looking for:
(e.g., "the one where we fixed the auth bug last week" or "when I was setting up the database")
```

**Use the Task tool with `model: haiku`** to search intelligently:

```
Task(
  subagent_type: "general-purpose",
  model: "haiku",
  prompt: "Help find Claude Code sessions matching this description: '[USER'S DESCRIPTION]'

    You have these search tools available:
    - python3 ~/.claude/skills/share-session/scripts/search.py 'QUERY' --scope personal --json
    - python3 ~/.claude/skills/share-session/scripts/search.py 'QUERY' --after 'DATE' --json
    - python3 ~/.claude/skills/share-session/scripts/discover.py --scope personal --after 'DATE' --json

    Steps:
    1. Extract keywords and date references from the description
    2. Run 1-3 targeted searches (try different keywords if needed)
    3. For promising matches, look at the session previews and match contexts
    4. Return the top 3-5 most relevant sessions with a brief explanation of why each matches

    Return a JSON object:
    {
      'sessions': [
        {'path': '...', 'date': '...', 'project': '...', 'why': 'Matches because...'},
        ...
      ],
      'search_summary': 'Searched for X, Y, Z and found N matches'
    }
  "
)
```

The agent will:
- Parse date references ("last week", "yesterday", "in December")
- Try multiple keyword variations
- Read session previews to understand context
- Rank results by relevance

Present the curated results:

```
## Found Sessions

Based on your description, here are the best matches:

| # | Date | Project | Why it matches |
|---|------|---------|----------------|
| 1 | Jan 10 | ~/myproject | Fixed JWT auth bug, added refresh tokens |
| 2 | Jan 8 | ~/myproject | Initial auth implementation session |

Select a session number:
```

After selection, continue to Step 3 (Draft).

## Step 2: Select Session

Discover sessions using the selected scope (start with offset 0):

```bash
python3 ~/.claude/skills/share-session/scripts/discover.py --scope [SCOPE] --limit 10 --offset [OFFSET] --json
```

Present sessions in a numbered list:

```
## Select Session (showing 1-10)

Which session would you like to share?

| # | Date | Project | Preview | Duration |
|---|------|---------|---------|----------|
| 1 | Jan 17, 2:30 PM | ~/myproject | "Help me refactor..." | 1h 15m |
| 2 | Jan 17, 10:00 AM | ~/other | "Create a new..." | 45m |
| 3 | Jan 16, 3:00 PM | ~/myproject | "Fix the auth bug..." | 30m |
...
```

**Use AskUserQuestion** with options including pagination:
- Session number options (show 3-4 notable sessions)
- "View older sessions" - increment offset by 10 and re-run discover
- "Custom selection" - let user type a specific number

If user selects "View older sessions":
1. Increment offset by 10
2. Re-run discover with new offset
3. Show next page of sessions (numbered 11-20, etc.)
4. Include "View older" and "Back to newer" options as appropriate

**Use AskUserQuestion** to let user select by number. Default to the most recent session if they just want one.

## Step 3: Draft Summary

Parse the selected session to get the raw data:

```bash
python3 ~/.claude/skills/share-session/scripts/parse.py "SESSION_PATH" --json
```

### Use Haiku for drafting

**Use the Task tool with `model: haiku`** to analyze the parsed session and draft the summary. This is faster and cheaper than using the main model for straightforward summarization.

```
Task(
  subagent_type: "general-purpose",
  model: "haiku",
  prompt: "Analyze this session data and draft a summary for someone learning how to work with AI coding agents.

    1. One sentence describing the overall work
    2. 3-5 bullet points covering key actions and decisions
    3. Tag special moments with these icons:

    ICONS:
    - 🚧 Struggles/roadblocks - things that didn't go well or required rework
    - 💡 Human learning - when the USER learned something about working with agents
    - 🤖 Agent learning - when the agent adapted, was corrected, or learned from feedback
    - 📄 Doc updates - when AGENTS.md, CLAUDE.md, or instruction files were updated
    - 📝 Doc opportunity - suggest improvements that SHOULD be documented based on what happened

    Focus on what's useful for teaching humans to work effectively with AI agents.
    Look for:
    - Moments where the user course-corrected the agent
    - Patterns that worked well (or didn't)
    - Changes made to agent instruction files
    - Things that should probably be added to documentation but weren't

    Session data: [paste parsed JSON metadata and first few turns]

    Return ONLY the summary, no explanation."
)
```

Present the draft returned by haiku:

```
## Draft Summary

**"Implemented user authentication with JWT tokens"**

• Added login/logout endpoints to the API
• Created JWT token generation and validation
• 🚧 Initial approach using cookies failed due to CORS issues - switched to header-based tokens
• 💡 User learned to specify auth approach upfront to avoid agent making assumptions
• 🤖 Agent was corrected on token storage approach - adapted to use httpOnly cookies
• 📄 Updated AGENTS.md with preferred authentication patterns for this project
• 📝 Should document: "always ask about session management strategy before implementing auth"

---

Look good? You can edit to add 💡 human learnings, 🤖 agent corrections, or 📝 doc suggestions.
```

**Use AskUserQuestion** with options:
- "Looks good" (continue)
- "Edit summary" (let them provide corrections, add highlights, or include takeaways)

## Step 4: Output

Confirm output location, then generate.

Generate a filename from the session date and summary title:

1. Take the session date: `2026-01-17`
2. Create a slug from the summary title (lowercase, hyphens, 2-4 words)
   - "Implemented /share-session wizard" → `share-session-wizard`
   - "Fixed Kendo chart legend display" → `kendo-legend-fix`
3. Combine: `2026-01-17-share-session-wizard.md`

**Use AskUserQuestion** to confirm the save location:

```
## Output

Save to: ~/Desktop/2026-01-17-share-session-wizard.md

Ready to generate?
```

### Generate Markdown

Write the markdown directly (don't use export.py). The final markdown should follow this template:

```markdown
# Session Summary: [Title from draft]

**Date**: [Session date]
**Duration**: [Duration]
**Project**: [Project path]

## Overview

[One sentence summary from Step 3]

## What Happened

[Bullets from Step 3 - actions, decisions, and tagged moments]

### Icon Key
- 🚧 Struggle/roadblock
- 💡 Human learned something
- 🤖 Agent was corrected/adapted
- 📄 Documentation was updated
- 📝 Documentation opportunity

## Conversation

[Concise transcript - see below]

## Usage Stats

| Metric | Value |
|--------|-------|
| Turns | [turn_count] |
| Tool Calls | [total_tool_calls] |
| Files Created | [count] |
| Files Edited | [count] |
| Commands Run | [count] |

### Token Usage & Estimated Cost

| Token Type | Count | Est. Cost |
|------------|------:|----------:|
| Input | [input] | $[cost] |
| Output | [output] | $[cost] |
| Cache Read | [cache_read] | $[cost] |
| **Total** | **[total]** | **$[total]** |

*[If cache savings > $1: "Prompt caching saved ~$X.XX (Y% reduction)"]*
*Cost estimate based on Claude Sonnet 4 pricing*

---
*Generated with Claude Code /share-session*
```

### Calculating Costs

Use this pricing (per million tokens) for cost estimates:

**Claude Sonnet 4** (default - most common model):
- Input: $3.00/MTok
- Output: $15.00/MTok
- Cache Read: $0.30/MTok
- Cache Write: $3.75/MTok

The token data comes from the parsed session's `stats.tokens` object:
- `input`, `output`, `cache_read`, `cache_create`

Calculate:
```
input_cost = (input / 1,000,000) * 3.00
output_cost = (output / 1,000,000) * 15.00
cache_read_cost = (cache_read / 1,000,000) * 0.30
total = input_cost + output_cost + cache_read_cost

# Cache savings (what it would have cost without caching)
no_cache_input = ((input + cache_read) / 1,000,000) * 3.00
savings = no_cache_input - input_cost - cache_read_cost
```

### Generating the Transcript

**Use the Task tool with `model: haiku`** to generate the transcript. This is the most token-heavy step but straightforward work - perfect for a fast, cheap model.

```
Task(
  subagent_type: "general-purpose",
  model: "haiku",
  prompt: "Generate a concise conversation transcript from this session data.

    For each turn:
    - **User**: Show the message (truncate to ~200 chars if long, add '...')
    - **Claude**: Summarize the response in 1-2 sentences focusing on actions taken and outcomes

    Skip repetitive exchanges, debugging loops, and minor clarifications.
    Aim for 5-15 key exchanges that tell the story.

    Format each exchange as:
    **User**: [message]
    > **Claude**: [summary]
    ---

    Session turns: [paste turns array from parsed JSON]

    Return ONLY the formatted transcript."
)
```

The transcript should be a **concise, readable summary** of the back-and-forth, not a raw dump. For each turn:

1. **User**: Show the user's message (truncate to ~200 chars if very long, add "...")
2. **Claude**: Summarize the response in 1-2 sentences. Focus on:
   - What action was taken (e.g., "Searched for authentication files")
   - Key output or decision (e.g., "Found 3 matching files")
   - Skip tool call details unless they're the main point

Format as a clean conversation:

```markdown
## Conversation

**User**: I'd like to work on the session-explorer skill some more. Can you summarize where we stand with that?

> **Claude**: Searched for session-explorer files and found the existing skill at `~/.claude/skills/session-explorer/`. Summarized the current state: 6 working Python scripts for discovering, searching, parsing, summarizing, exporting sessions, and generating reports.

---

**User**: Could we make this an overt command like `/share-session` in Claude?

> **Claude**: Researched slash command creation in Claude Code and explored OpenCode's session format for multi-CLI support. Proposed a new architecture with two skills: `/explore-sessions` for discovery and `/share-session` for export.

---

**User**: Let's proceed with a minimal /share-session wizard

> **Claude**: Created the skill at `~/.claude/skills/share-session/SKILL.md` with a 4-step wizard flow: Find → Select → Draft → Output.
```

Keep it to **key exchanges only** - skip repetitive tool calls, debugging loops, or minor clarifications. Aim for 5-15 exchanges that tell the story of what happened.

## Final Confirmation

After generating, confirm success and end the wizard:

```
✓ Summary saved to ~/Desktop/2026-01-17-share-session-wizard.md
```

That's it - no follow-up questions. The user can run `/share-session` again if needed.

## Important Notes

- **Always wait for user input** between steps - this is a wizard, not autonomous
- **Keep it fast** - don't over-explain, use concise prompts
- **Respect defaults** - if user just hits enter, use sensible defaults
- **One thing at a time** - don't combine steps or skip ahead
- Scripts are in `~/.claude/skills/share-session/scripts/`

## Example Invocation

User: `/share-session`

Assistant proceeds through the 4 steps, pausing for input at each stage.
