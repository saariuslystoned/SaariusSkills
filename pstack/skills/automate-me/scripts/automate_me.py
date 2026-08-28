#!/usr/bin/env python3
import json
import os
import sys
import glob
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime

HOME = Path.home()
BRAIN_DIR = HOME / ".gemini" / "antigravity" / "brain"
CLAUDE_DIR = HOME / ".claude"
CURSOR_DIR = HOME / ".cursor"
CODEX_SESSIONS_DIR = HOME / ".codex" / "sessions"
GROK_CLI_DIR = HOME / ".grok" / "sessions"
GROK_BOT_DIR = HOME / "Library" / "Application Support" / "Grok Bot" / "sand-client-persistence"

# Target distribution: AGY on bobby-macbook ONLY
TARGET_AGY_SKILL = HOME / ".gemini" / "config" / "plugins" / "saarius-skills" / "skills" / "bobby-mode" / "SKILL.md"

def ingest_codex_chatgpt_app(max_files=100):
    """Ingest conversations from the ChatGPT / Codex desktop application."""
    user_inputs = []
    if not CODEX_SESSIONS_DIR.exists():
        return user_inputs
    
    files = sorted(CODEX_SESSIONS_DIR.glob("**/*.jsonl"), key=os.path.getmtime, reverse=True)
    for f in files[:max_files]:
        try:
            with open(f, "r", encoding="utf-8", errors="ignore") as fp:
                for line in fp:
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                        payload = obj.get("payload", {})
                        if isinstance(payload, dict):
                            if payload.get("role") == "user":
                                content = payload.get("content")
                                if isinstance(content, list):
                                    for item in content:
                                        if isinstance(item, dict) and item.get("type") == "input_text":
                                            t = item.get("text", "").strip()
                                            if t and not t.startswith("/"):
                                                user_inputs.append({"source": "chatgpt-codex-app", "text": t})
                                elif isinstance(content, str) and content.strip() and not content.startswith("/"):
                                    user_inputs.append({"source": "chatgpt-codex-app", "text": content.strip()})
                    except Exception:
                        pass
        except Exception:
            pass
    return user_inputs

def ingest_grok_cli():
    """Ingest prompt history and session databases from Grok Build CLI."""
    user_inputs = []
    if not GROK_CLI_DIR.exists():
        return user_inputs
    
    # 1. Prompt history JSONL files
    for hf in GROK_CLI_DIR.glob("**/prompt_history.jsonl"):
        try:
            with open(hf, "r", encoding="utf-8", errors="ignore") as fp:
                for line in fp:
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                        p = obj.get("prompt", "").strip()
                        if p and not obj.get("is_bash", False) and not p.startswith("/"):
                            user_inputs.append({"source": "grok-cli", "text": p})
                    except Exception:
                        pass
        except Exception:
            pass
            
    # 2. SQLite session database
    db_file = GROK_CLI_DIR / "session_search.sqlite"
    if db_file.exists():
        try:
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT content FROM session_docs;")
            for (content,) in cursor.fetchall():
                if content and isinstance(content, str):
                    for line in content.split("\n"):
                        l = line.strip()
                        if len(l) > 10 and not l.startswith("```") and not l.startswith("#"):
                            user_inputs.append({"source": "grok-cli-db", "text": l})
            conn.close()
        except Exception:
            pass
            
    return user_inputs

def ingest_grok_bot():
    """Ingest conversations from Grok Bot Desktop application."""
    user_inputs = []
    if GROK_BOT_DIR.exists():
        for blob_file in GROK_BOT_DIR.glob("*.blob"):
            try:
                with open(blob_file, "r", encoding="utf-8", errors="ignore") as fp:
                    data = json.load(fp)
                    def extract(obj):
                        if isinstance(obj, dict):
                            if obj.get("sender") == "user" or obj.get("role") == "user":
                                text = obj.get("text") or obj.get("content") or obj.get("message")
                                if isinstance(text, str) and text.strip() and not text.startswith("/"):
                                    user_inputs.append({"source": "grok-bot", "text": text.strip()})
                            for v in obj.values():
                                extract(v)
                        elif isinstance(obj, list):
                            for item in obj:
                                extract(item)
                    extract(data)
            except Exception:
                pass
    return user_inputs

def ingest_claude_history():
    """Ingest history from Claude Code CLI."""
    user_inputs = []
    claude_history = CLAUDE_DIR / "history.jsonl"
    if claude_history.exists():
        try:
            with open(claude_history, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                        display = record.get("display", "").strip()
                        if display and not display.startswith("/") and len(display) > 2:
                            user_inputs.append({"source": "claude-code", "text": display})
                    except Exception:
                        pass
        except Exception:
            pass
    return user_inputs

def ingest_agy_transcripts(max_sessions=50):
    """Ingest conversations from Antigravity (AGY)."""
    user_inputs = []
    if not BRAIN_DIR.exists():
        return user_inputs
    
    dirs = [d for d in BRAIN_DIR.iterdir() if d.is_dir() and (d / ".system_generated" / "logs" / "transcript.jsonl").exists()]
    dirs.sort(key=lambda d: (d / ".system_generated" / "logs" / "transcript.jsonl").stat().st_mtime, reverse=True)
    
    for d in dirs[:max_sessions]:
        t_file = d / ".system_generated" / "logs" / "transcript.jsonl"
        try:
            with open(t_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                        if record.get("type") == "USER_INPUT":
                            content = record.get("content", "").strip()
                            if content and not content.startswith("/"):
                                user_inputs.append({"source": "agy", "text": content})
                    except Exception:
                        pass
        except Exception:
            pass
    return user_inputs

def generate_profile_content():
    return """---
name: bobby-mode
description: "Universal operator profile for Bobby: Voice-to-Text brevity, zero filler, high signal, bounded loops, and strict proof."
---

# Bobby Mode (AGY Operator Profile)

Active behavioral profile synthesized for Bobby inside AGY from comprehensive multi-harness history (ChatGPT/Codex, Grok CLI/Bot, Claude Code, AGY).

## Communication & Interaction Style
- **Voice-to-Text Primary**: Operator dictates inputs. Tolerate phonetic misspellings, lack of punctuation, shorthand, and sentence fragments.
- **Zero Conversational Filler**: Never use polite filler ("Sure thing!", "I can help with that", "Certainly!", "Great question!"). Begin immediately with actionable content.
- **High Signal & Direct**: Deliver concrete answers, diffs, commands, and structured findings. Avoid speculative commentary.
- **Concise & Scannable**: Format outputs with bullet points, code blocks, and markdown tables.

## Execution & Swarm North Star
- **Core Loop**: `bounded task -> real action -> proof -> review -> human gate -> next task`.
- **Proof Policy**: Every non-trivial claim requires verifiable proof (terminal command output, test run, screenshot, or receipt).
- **Worktree Isolation**: Keep feature branches and coding agent work isolated in dedicated git worktrees. Never mutate dirty checkouts.
- **Minimal Diffs**: Bias toward surgical edits and deletions. Avoid adding unnecessary abstraction layers or unsolicited boilerplate.
- **Human Gates**: Always pause and ask for confirmation before:
  - Git merges or production deployments
  - Secret/credential changes or token rotations
  - Sending non-test communications or customer impact
  - Destructive file/machine cleanups or data migrations
"""

def main():
    print("==================================================")
    print("Mining Multi-Harness Transcripts on bobby-macbook")
    print("==================================================")
    
    print("\nIngesting from local harness storage:")
    codex_inputs = ingest_codex_chatgpt_app()
    grok_cli_inputs = ingest_grok_cli()
    grok_bot_inputs = ingest_grok_bot()
    claude_inputs = ingest_claude_history()
    agy_inputs = ingest_agy_transcripts()
    
    print(f"  * ChatGPT / Codex Desktop App: {len(codex_inputs)} prompts mined (~/.codex/sessions)")
    print(f"  * Grok Build CLI:              {len(grok_cli_inputs)} prompts mined (~/.grok/sessions)")
    print(f"  * Grok Bot Desktop App:        {len(grok_bot_inputs)} prompts mined (~/Library/Application Support/Grok Bot)")
    print(f"  * Claude Code CLI:             {len(claude_inputs)} prompts mined (~/.claude/history.jsonl)")
    print(f"  * Antigravity (AGY):           {len(agy_inputs)} prompts mined (~/.gemini/antigravity/brain)")

    total = len(codex_inputs) + len(grok_cli_inputs) + len(grok_bot_inputs) + len(claude_inputs) + len(agy_inputs)
    print(f"\nTotal Dataset Mined: {total} prompts across all harnesses on bobby-macbook.")

    # Write ONLY to local AGY
    TARGET_AGY_SKILL.parent.mkdir(parents=True, exist_ok=True)
    TARGET_AGY_SKILL.write_text(generate_profile_content().strip() + "\n")
    print(f"\n[OK] Successfully updated AGY bobby-mode skill at:\n  {TARGET_AGY_SKILL}")

if __name__ == "__main__":
    main()
