#!/usr/bin/env python3
"""Antigravity Sidebar Session & LanguageServerService ConnectRPC helper.

Wraps `~/.gemini/antigravity/bin/agentapi` and the local ConnectRPC
`LanguageServerService` endpoints without printing CSRF tokens.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _app_data_dir() -> Path:
    env_dir = os.environ.get("ANTIGRAVITY_APP_DATA_DIR")
    if env_dir:
        return Path(env_dir)
    return Path.home() / ".gemini" / "antigravity"


def _discover_daemon() -> tuple[str, str]:
    addr = os.environ.get("ANTIGRAVITY_LS_ADDRESS", "").strip()
    csrf = os.environ.get("ANTIGRAVITY_CSRF_TOKEN", "").strip()
    if addr and csrf:
        return addr, csrf

    daemon_dir = _app_data_dir() / "daemon"
    candidates = sorted(
        glob.glob(str(daemon_dir / "hub_*.json")),
        key=lambda p: os.path.getmtime(p),
        reverse=True,
    )
    for path in candidates:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            port = data.get("httpPort")
            token = data.get("csrfToken")
            if port and token:
                return f"localhost:{port}", str(token)
        except Exception:
            continue
    raise RuntimeError(
        "Could not discover Antigravity daemon (ANTIGRAVITY_LS_ADDRESS / hub_*.json)."
    )


def _agentapi_cmd(extra_args: list[str]) -> list[str]:
    exe = os.environ.get("ANTIGRAVITY_AGENTAPI_EXE", "").strip()
    if exe and Path(exe).is_file():
        return [exe, "agentapi", *extra_args]
    shim = _app_data_dir() / "bin" / "agentapi"
    if shim.is_file():
        return [str(shim), *extra_args]
    mac_ls = Path(
        "/Applications/Antigravity.app/Contents/Resources/bin/language_server"
    )
    if mac_ls.is_file():
        return [str(mac_ls), "agentapi", *extra_args]
    return ["agentapi", *extra_args]


def call_rpc(method: str, payload: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
    addr, csrf = _discover_daemon()
    url = f"http://{addr}/exa.language_server_pb.LanguageServerService/{method}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload or {}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-codeium-csrf-token": csrf,
            "Connect-Protocol-Version": "1",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "ignore")
        raise RuntimeError(f"RPC {method} failed (HTTP {exc.code}): {body}") from exc


def list_projects() -> list[dict[str, Any]]:
    res = call_rpc("ListProjects", {})
    ids = res.get("projectIds", [])
    projects: list[dict[str, Any]] = []
    for pid in ids:
        if pid in ("default-cli-project", "outside-of-project"):
            projects.append({"id": pid, "name": pid, "folders": []})
            continue
        try:
            proj = call_rpc("ReadProject", {"id": pid}).get("project", {})
            resources = proj.get("projectResources", {}).get("resources", [])
            folders = [
                r.get("gitFolder", {}).get("folderUri", "")
                for r in resources
                if r.get("gitFolder")
            ]
            projects.append(
                {
                    "id": proj.get("id", pid),
                    "name": proj.get("name", ""),
                    "folders": folders,
                }
            )
        except Exception:
            projects.append({"id": pid, "name": "", "folders": []})
    return projects


def resolve_project_id(selector: str | None) -> str | None:
    if not selector:
        return os.environ.get("ANTIGRAVITY_PROJECT_ID")
    sel = selector.strip()
    projects = list_projects()
    for p in projects:
        if p["id"] == sel:
            return p["id"]
    for p in projects:
        if p["name"].lower() == sel.lower():
            return p["id"]
    for p in projects:
        for folder in p["folders"]:
            if folder.rstrip("/").endswith("/" + sel.strip("/")) or sel in folder:
                return p["id"]
    raise RuntimeError(
        f"Project '{selector}' not found. Run 'agy-session.py projects' to see valid IDs/names."
    )


def run_agentapi(args: list[str], project_id: str | None = None) -> dict[str, Any]:
    addr, csrf = _discover_daemon()
    env = dict(os.environ)
    env["ANTIGRAVITY_LS_ADDRESS"] = addr
    env["ANTIGRAVITY_CSRF_TOKEN"] = csrf
    if project_id:
        env["ANTIGRAVITY_PROJECT_ID"] = project_id
    cmd = _agentapi_cmd(args)
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
    out = proc.stdout.strip()
    if proc.returncode != 0 and not out:
        raise RuntimeError(proc.stderr.strip() or f"agentapi exited {proc.returncode}")
    try:
        return json.loads(out) if out else {}
    except json.JSONDecodeError:
        return {"raw": out, "stderr": proc.stderr.strip(), "returncode": proc.returncode}


def cmd_new(ns: argparse.Namespace) -> int:
    pid = resolve_project_id(ns.project)
    args = ["new-conversation"]
    if ns.title:
        args.append(f"--title={ns.title}")
    if ns.model:
        args.append(f"--model={ns.model}")
    if ns.profile:
        args.append(f"--profile={ns.profile}")
    args.append(ns.prompt)
    result = run_agentapi(args, project_id=pid)
    conv_id = (
        result.get("response", {})
        .get("newConversation", {})
        .get("conversationId")
    )
    payload = {
        "ok": bool(conv_id) and not result.get("error"),
        "conversationId": conv_id,
        "conversationLink": f"conversation://{conv_id}" if conv_id else None,
        "projectId": pid,
        "title": ns.title,
        "model": ns.model,
        "profile": ns.profile,
        "result": result,
    }
    print(json.dumps(payload, indent=2))
    return 0 if payload["ok"] else 1


def cmd_send(ns: argparse.Namespace) -> int:
    pid = resolve_project_id(ns.project) if ns.project else None
    args = ["send-message"]
    if ns.title:
        args.append(f"--title={ns.title}")
    args.extend([ns.conversation, ns.message])
    result = run_agentapi(args, project_id=pid)
    print(json.dumps(result, indent=2))
    return 0 if not result.get("error") else 1


def cmd_metadata(ns: argparse.Namespace) -> int:
    result = run_agentapi(["get-conversation-metadata", ns.conversation])
    print(json.dumps(result, indent=2))
    return 0 if not result.get("error") else 1


def cmd_projects(_ns: argparse.Namespace) -> int:
    print(json.dumps({"projects": list_projects()}, indent=2))
    return 0


def cmd_list(ns: argparse.Namespace) -> int:
    db_path = _app_data_dir() / "conversation_summaries.db"
    if not db_path.is_file():
        raise RuntimeError(f"Summaries DB not found at {db_path}")
    pid = resolve_project_id(ns.project) if ns.project else None
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    sql = (
        "SELECT conversation_id, title, status, project_id, workspace_uris, "
        "parent_conversation_id, nesting_depth, last_modified_time "
        "FROM conversation_summaries WHERE 1=1"
    )
    params: list[Any] = []
    if not ns.include_subagents:
        sql += " AND nesting_depth = 0 AND parent_conversation_id = ''"
    if pid:
        sql += " AND project_id = ?"
        params.append(pid)
    sql += " ORDER BY last_modified_time DESC LIMIT ?"
    params.append(ns.limit)
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    print(json.dumps({"conversations": rows}, indent=2))
    return 0


def cmd_export_md(ns: argparse.Namespace) -> int:
    res = call_rpc("ConvertTrajectoryToMarkdown", {"conversationId": ns.conversation})
    if ns.json:
        print(json.dumps(res, indent=2))
    else:
        print(res.get("markdown", ""))
    return 0


def cmd_fork(ns: argparse.Namespace) -> int:
    payload: dict[str, Any] = {"sourceCascadeId": ns.conversation}
    if ns.step_index is not None:
        payload["forkAtStepIndex"] = ns.step_index
    res = call_rpc("ForkConversation", payload)
    print(json.dumps(res, indent=2))
    return 0


def cmd_wait(ns: argparse.Namespace) -> int:
    payload: dict[str, Any] = {
        "cascadeId": ns.conversation,
        "timeoutSeconds": ns.timeout_seconds,
    }
    res = call_rpc("WaitForConversationFullyIdle", payload, timeout=ns.timeout_seconds + 10)
    print(json.dumps(res, indent=2))
    return 0


def cmd_stop(ns: argparse.Namespace) -> int:
    res = call_rpc("CancelCascadeInvocation", {"cascadeId": ns.conversation})
    print(json.dumps(res, indent=2))
    return 0


def cmd_models(_ns: argparse.Namespace) -> int:
    res = call_rpc("GetCascadeModelConfigData", {})
    print(json.dumps(res, indent=2))
    return 0


def cmd_quota(_ns: argparse.Namespace) -> int:
    res = call_rpc("RetrieveUserQuotaSummary", {})
    print(json.dumps(res, indent=2))
    return 0


def cmd_rpc(ns: argparse.Namespace) -> int:
    payload = json.loads(ns.payload) if ns.payload else {}
    res = call_rpc(ns.method, payload, timeout=ns.timeout)
    print(json.dumps(res, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    p_new = sub.add_parser("new", help="Start a new top-level sidebar conversation")
    p_new.add_argument("--project", help="Project name, folder basename, or UUID (defaults to current)")
    p_new.add_argument("--title", help="Sidebar title for the new conversation")
    p_new.add_argument("--model", help="Model tier (flash_lite|flash|pro) or exact model ID")
    p_new.add_argument("--profile", help="Agent profile name")
    p_new.add_argument("--prompt", required=True, help="Initial prompt for the new session")
    p_new.set_defaults(func=cmd_new)

    p_send = sub.add_parser("send", help="Send a message to any sidebar conversation")
    p_send.add_argument("--conversation", "-c", required=True, help="Recipient conversation UUID")
    p_send.add_argument("--title", help="Optional updated title")
    p_send.add_argument("--project", help="Optional project override")
    p_send.add_argument("--message", "-m", required=True, help="Message content")
    p_send.set_defaults(func=cmd_send)

    p_meta = sub.add_parser("metadata", help="Get live metadata for a conversation")
    p_meta.add_argument("conversation", help="Conversation UUID")
    p_meta.set_defaults(func=cmd_metadata)

    p_proj = sub.add_parser("projects", help="List all registered sidebar projects")
    p_proj.set_defaults(func=cmd_projects)

    p_list = sub.add_parser("list", help="List recent sidebar conversations from local SQLite")
    p_list.add_argument("--project", help="Filter by project name, folder, or UUID")
    p_list.add_argument("--limit", type=int, default=15, help="Max rows (default: 15)")
    p_list.add_argument("--include-subagents", action="store_true", help="Include nested subagents")
    p_list.set_defaults(func=cmd_list)

    p_exp = sub.add_parser("export-md", help="Export conversation trajectory as Markdown")
    p_exp.add_argument("conversation", help="Conversation UUID")
    p_exp.add_argument("--json", action="store_true", help="Emit JSON wrapper instead of raw Markdown")
    p_exp.set_defaults(func=cmd_export_md)

    p_fork = sub.add_parser("fork", help="Fork an existing conversation")
    p_fork.add_argument("conversation", help="Source conversation UUID")
    p_fork.add_argument("--step-index", type=int, help="Optional step index to fork at")
    p_fork.set_defaults(func=cmd_fork)

    p_wait = sub.add_parser("wait", help="Wait for a conversation to become fully idle")
    p_wait.add_argument("conversation", help="Conversation UUID")
    p_wait.add_argument("--timeout-seconds", type=int, default=120, help="Wait timeout in seconds")
    p_wait.set_defaults(func=cmd_wait)

    p_stop = sub.add_parser("stop", help="Cancel an active conversation invocation")
    p_stop.add_argument("conversation", help="Conversation UUID")
    p_stop.set_defaults(func=cmd_stop)

    p_models = sub.add_parser("models", help="List advertised models and per-model quota")
    p_models.set_defaults(func=cmd_models)

    p_quota = sub.add_parser("quota", help="Show user quota summary")
    p_quota.set_defaults(func=cmd_quota)

    p_rpc = sub.add_parser("rpc", help="Call any LanguageServerService ConnectRPC method")
    p_rpc.add_argument("method", help="RPC method name (e.g. ListBackgroundTasks)")
    p_rpc.add_argument("payload", nargs="?", default="{}", help="JSON request object")
    p_rpc.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds")
    p_rpc.set_defaults(func=cmd_rpc)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)
    return ns.func(ns)


if __name__ == "__main__":
    sys.exit(main())
