#!/usr/bin/env python3
"""
ACP Minimal v1.0.6 - Full Spec Compliance

Endpoints: whoami, status, history, running, activity/{id}, action, start, complete,
           stop, resume, clear_history, reset, reset_session, shutdown, restart,
           nudge (GET+POST), nudge/ack,
           notes, notes/add, notes/clear,
           todos, todos/add, todos/update, todos/toggle, todos/clear,
           shell, shell/add, shell/clear,
           summary, summary/export,
           stats/duration, activity/batch,
           session, session/refresh, csrf-token,
           files/list, files/view, files/download, files/stats (read-only)
           
NEW in 1.0.6:
           contextId auto-created when SendMessage called without contextId
           Agent Card URL dynamically set from request headers
           All files synchronized to v1.0.6
           
NEW in 1.0.5:
           primary_agent in /api/whoami response
           Nudges delivered only to primary agent
           
NEW in 1.0.4:
           agents (GET), agents/register (POST), agents/unregister (POST), agents/{name} (GET)
           a2a/send (POST), a2a/history (GET)
           .well-known/agent-card.json (GET)
           jsonrpc, a2a, api/jsonrpc (POST) - JSON-RPC 2.0 endpoints
           
A2A Compliance: JSON-RPC 2.0, Agent Card, contextId support
"""

import json, os, sys, base64, time, signal, threading, uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs

# --- CONFIG ---
PORT            = int(os.environ.get("ACP_PORT", "8766"))
AUTH_USER       = os.environ.get("ACP_USER", "admin")
AUTH_PASS       = os.environ.get("ACP_PASS", "secret")
DATA_FILE       = os.environ.get("ACP_DATA_FILE", "acp_data.json")
SUMMARY_FILE    = os.environ.get("ACP_SUMMARY_FILE", "acp_session_summary.md")
CONTEXT_WINDOW  = int(os.environ.get("ACP_CONTEXT_WINDOW", "200000"))
SESSION_TIMEOUT = int(os.environ.get("ACP_SESSION_TIMEOUT", "86400"))
ORPHAN_TIMEOUT  = int(os.environ.get("ACP_ORPHAN_TIMEOUT", "300"))

SESSION_START = time.time()

def sanitize_path(base_dir, rel_path):
    """Prevent path traversal attacks. Returns resolved path or None if outside base_dir."""
    abs_base = os.path.realpath(base_dir)
    if not rel_path:
        return abs_base
    target = os.path.realpath(os.path.join(base_dir, rel_path))
    if not target.startswith(abs_base + os.sep) and target != abs_base:
        return None
    return target

# --- JSON-RPC 2.0 Error Codes ---
JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603
JSONRPC_TASK_NOT_FOUND = -32001
JSONRPC_TASK_NOT_RUNNING = -32002

# --- ACP Agent Card (1.0.4) ---
ACP_AGENT_CARD = {
    "name": "ACP Server",
    "description": "Agent Control Panel - Monitoring and observability server for AI agents",
    "url": "",
    "version": "1.0.6",
    "capabilities": {
        "streaming": False,
        "pushNotifications": False
    },
    "defaultInputModes": ["text/plain", "application/json"],
    "defaultOutputModes": ["text/plain", "application/json"],
    "skills": [
        {
            "id": "activity_tracking",
            "name": "Activity Tracking",
            "description": "Log and monitor agent activities with token estimation",
            "tags": ["monitoring", "observability", "tokens"],
            "examples": ["Log a file read", "Track a bash command"]
        },
        {
            "id": "a2a_messaging",
            "name": "A2A Messaging",
            "description": "Inter-agent communication via message queue",
            "tags": ["messaging", "multi-agent", "coordination"],
            "examples": ["Send message to another agent", "Check inbox"]
        }
    ],
    "authentication": {
        "schemes": ["Basic"]
    }
}

# --- DATA ---

def load_data():
    defaults = {
        "running": [],
        "history": [],
        "stop_flag": False,
        "stop_reason": None,
        "tokens": 0,
        "startup_tokens": 0,
        "files_read": [],
        "files_read_tokens": {},
        "nudge": None,
        "primary_agent": None,
        "last_agent": "Unknown",
        "last_model": "Unknown",
        "todos": [],
        "notes": [],
        "summary": "Session Reset.",
        "session_start": SESSION_START,
        "agent_tokens": {},
        "shell_history": [],
        "errors": [],
        # NEW 1.0.4 fields
        "agents": {},           # Agent Registry
        "a2a_messages": [],     # A2A Message Queue
        "contexts": {},         # contextId -> session mapping
        "agent_skills": {}      # AgentSkill objects per agent
    }
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                d = json.load(f)
                merged = {**defaults, **d}
                # Migrate notes from old string format to structured array
                if isinstance(merged.get("notes"), str):
                    old = merged["notes"].strip()
                    merged["notes"] = []
                    if old:
                        for line in old.splitlines():
                            line = line.strip()
                            if line:
                                merged["notes"].append({
                                    "id": make_activity_id(),
                                    "timestamp": datetime.now().isoformat(),
                                    "category": "context",
                                    "content": line,
                                    "importance": "normal"
                                })
                return merged
        except:
            pass
    return defaults

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

# --- HELPERS ---

def make_activity_id():
    return datetime.now().strftime("%H%M%S-") + str(int(time.time() * 100) % 100)

def make_context_id():
    return "ctx-" + uuid.uuid4().hex[:12]

def estimate_tokens(text_list, content_size=0):
    return int((len("".join(map(str, text_list))) + content_size) / 3.5)

def get_session_info():
    now = time.time()
    elapsed = now - SESSION_START
    return {
        "session_start": SESSION_START,
        "last_activity": now,
        "elapsed_seconds": int(elapsed),
        "idle_seconds": 0,
        "timeout_seconds": SESSION_TIMEOUT,
        "remaining_seconds": max(0, SESSION_TIMEOUT - int(elapsed)),
        "is_expired": elapsed > SESSION_TIMEOUT,
        "expires_at": datetime.fromtimestamp(SESSION_START + SESSION_TIMEOUT).isoformat()
    }

def check_orphans(data):
    now = time.time()
    orphans = []
    for a in data.get("running", []):
        started = a.get("started_ts", now)
        if now - started > ORPHAN_TIMEOUT:
            orphans.append({
                "id": a["id"],
                "action": a["action"],
                "target": a["target"],
                "duration": int(now - started)
            })
    return orphans if orphans else None

def get_a2a_hints(data, agent_name):
    """Get A2A hints for an agent (pending messages). 1.0.4"""
    if not agent_name:
        return {}
    hints = {}
    messages_for_agent = []
    now_ts = time.time()
    
    for msg in data.get("a2a_messages", []):
        if msg.get("to_agent") == agent_name:
            try:
                expires = datetime.fromisoformat(msg["expires_at"]).timestamp()
                if expires > now_ts:
                    messages_for_agent.append(msg)
            except:
                pass
    
    if messages_for_agent:
        hints["pending_count"] = len(messages_for_agent)
        hints["senders"] = list(set(m.get("from_agent") for m in messages_for_agent if m.get("from_agent")))
        if messages_for_agent:
            latest = messages_for_agent[0]
            hints["preview"] = {
                "from": latest.get("from_agent"),
                "action": latest.get("action"),
                "msg_id": latest.get("id")
            }
    return {"a2a": hints} if hints else {}

def get_hints(data, target, agent_name=None):
    hints = {
        "modified_this_session": False,
        "modification_count": 0,
        "last_action": None,
        "recent_errors": 0,
        "last_error": None,
        "related_todos": [],
        "loop_detected": False,
        "loop_count": 0,
        "suggestion": None,
        "active_todos": len([t for t in data.get("todos", []) if t.get("status") == "in_progress"])
    }
    for a in data.get("history", []):
        if a.get("target") == target:
            hints["modified_this_session"] = True
            hints["modification_count"] += 1
            hints["last_action"] = a.get("action")
    recent = data.get("history", [])[:10]
    loop_count = sum(1 for a in recent if a.get("target") == target)
    if loop_count >= 3:
        hints["loop_detected"] = True
        hints["loop_count"] = loop_count
        hints["suggestion"] = f"Target '{target}' accessed {loop_count} times recently. Consider caching or alternative approach."
    for t in data.get("todos", []):
        if target and target.lower() in t.get("content", "").lower():
            hints["related_todos"].append({
                "id": t["id"],
                "content": t["content"],
                "status": t.get("status")
            })
    hints["recent_errors"] = len(data.get("errors", [])[-5:])
    if data.get("errors"):
        hints["last_error"] = data["errors"][-1].get("message")
    
    # Add A2A hints if agent_name provided (1.0.4)
    if agent_name:
        a2a_hints = get_a2a_hints(data, agent_name)
        if a2a_hints:
            hints["a2a"] = a2a_hints.get("a2a", {})
    
    return hints

def format_duration(ms):
    if not ms:
        return "0ms"
    if ms < 1000:
        return f"{ms}ms"
    if ms < 60000:
        return f"{ms/1000:.1f}s"
    return f"{ms/60000:.1f}m"

def calc_duration_stats(data):
    by_action = {}
    slow_activities = []
    total_duration = 0
    count = 0
    trend = []

    for a in data.get("history", []):
        dur = a.get("duration_ms", 0)
        if not dur:
            continue
        action = a.get("action", "UNKNOWN")
        if action not in by_action:
            by_action[action] = {
                "count": 0, "total_ms": 0,
                "average_ms": 0, "average_str": "0ms",
                "min_ms": dur, "max_ms": dur
            }
        by_action[action]["count"] += 1
        by_action[action]["total_ms"] += dur
        by_action[action]["min_ms"] = min(by_action[action]["min_ms"], dur)
        by_action[action]["max_ms"] = max(by_action[action]["max_ms"], dur)
        avg = by_action[action]["total_ms"] // by_action[action]["count"]
        by_action[action]["average_ms"] = avg
        by_action[action]["average_str"] = format_duration(avg)
        total_duration += dur
        count += 1
        if dur > 30000:
            slow_activities.append({
                "id": a["id"],
                "action": action,
                "target": a.get("target"),
                "duration_ms": dur,
                "duration_str": format_duration(dur)
            })
        trend.append({
            "action": action,
            "duration_ms": dur,
            "timestamp": a.get("started", "")
        })

    return {
        "by_action": by_action,
        "slow_activities": slow_activities[:10],
        "total_duration_ms": total_duration,
        "activities_with_duration": count,
        "average_duration_ms": total_duration // max(1, count),
        "slow_threshold_ms": 30000,
        "trend": trend[-20:]
    }

def get_token_summary(data):
    """Compute spec-compliant token fields. session_tokens = primary agent only."""
    primary = data.get("primary_agent")
    agent_tokens = data.get("agent_tokens", {})
    session_tokens = data.get("tokens", 0)
    startup_tokens = data.get("startup_tokens", 0)
    activity_tokens = max(0, session_tokens - startup_tokens)
    tokens_remaining = CONTEXT_WINDOW - session_tokens
    tokens_percent = round(session_tokens / CONTEXT_WINDOW * 100, 2)
    other_agents_tokens = sum(v for k, v in agent_tokens.items() if k != primary)
    overflow_warning = "Context window over 90% full" if tokens_percent > 90 else None
    return {
        "session_tokens": session_tokens,
        "startup_tokens": startup_tokens,
        "activity_tokens": activity_tokens,
        "tokens_remaining": tokens_remaining,
        "tokens_percent": tokens_percent,
        "overflow_warning": overflow_warning,
        "other_agents_tokens": other_agents_tokens,
        "tunnel_url": None,
    }

def build_summary_struct(data):
    """Build structured summary object per spec §4.6."""
    session = get_session_info()
    tok = get_token_summary(data)
    history = data.get("history", [])
    breakdown = {}
    for a in history:
        act = a.get("action", "UNKNOWN")
        breakdown[act] = breakdown.get(act, 0) + 1
    files_read    = list({a["target"] for a in history if a.get("action") == "READ"})
    files_written = list({a["target"] for a in history if a.get("action") == "WRITE"})
    files_edited  = list({a["target"] for a in history if a.get("action") == "EDIT"})
    return {
        "session_overview": {
            "duration": format_duration(session["elapsed_seconds"] * 1000),
            "duration_seconds": session["elapsed_seconds"],
            "total_activities": len(history),
            "activity_breakdown": breakdown,
            "currently_running": len(data.get("running", [])),
            "stop_flag": data.get("stop_flag", False),
            "stop_reason": data.get("stop_reason"),
            "primary_agent": data.get("primary_agent"),
        },
        "token_usage": {
            "session_tokens": tok["session_tokens"],
            "tokens_percent": tok["tokens_percent"],
            "context_window": CONTEXT_WINDOW,
            "tokens_remaining": tok["tokens_remaining"],
        },
        "file_interactions": {
            "files_read": files_read,
            "files_written": files_written,
            "files_edited": files_edited,
        },
        "ai_notes": data.get("notes", []),
        "todos": data.get("todos", []),
        "recent_activities": history[:20],
    }

def write_summary_file(data):
    """Write summary to persistent markdown file. Returns (filepath, content)."""
    s = build_summary_struct(data)
    ov = s["session_overview"]
    tu = s["token_usage"]
    lines = [
        "# ACP Session Summary",
        f"\n**Generated:** {datetime.now().isoformat()}",
        "\n## Session Info",
        f"- **Duration:** {ov['duration']}",
        f"- **Total Activities:** {ov['total_activities']}",
        f"- **Primary Agent:** {ov.get('primary_agent') or 'Unknown'}",
        f"- **Tokens Used:** {tu['session_tokens']:,}",
        f"- **Context Usage:** {tu['tokens_percent']}%",
        "\n## Agent Tokens",
    ]
    for name, tokens in data.get("agent_tokens", {}).items():
        badge = " (primary)" if name == data.get("primary_agent") else ""
        lines.append(f"- {name}{badge}: {tokens} tokens")
    lines.append("\n## Todos")
    for t in data.get("todos", []):
        icon = "✅" if t.get("status") == "completed" else "⬜"
        lines.append(f"- {icon} [{t.get('priority', 'med')}] {t.get('content', '')}")
    lines.append("\n## Activity History (last 20)")
    for a in data.get("history", [])[:20]:
        lines.append(f"- [{a.get('action')}] {a.get('target')}: {a.get('result', a.get('details', 'N/A'))}")
    notes = data.get("notes", [])
    if notes:
        lines.append("\n## Notes")
        for n in notes:
            lines.append(f"- [{n.get('category', 'note')}] {n.get('content', '')}")
    content = "\n".join(lines) + "\n"
    filepath = os.path.abspath(SUMMARY_FILE)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    return filepath, content

def reset_state():
    return {
        "running": [],
        "history": [],
        "stop_flag": False,
        "stop_reason": None,
        "tokens": 0,
        "startup_tokens": 0,
        "files_read": [],
        "files_read_tokens": {},
        "nudge": None,
        "primary_agent": None,
        "last_agent": "Unknown",
        "last_model": "---",
        "todos": [],
        "notes": [],
        "summary": "Session Reset.",
        "session_start": time.time(),
        "agent_tokens": {},
        "shell_history": [],
        "errors": [],
        # 1.0.4 fields
        "agents": {},
        "a2a_messages": [],
        "contexts": {},
        "agent_skills": {}
    }

# --- A2A Helpers ---

def create_a2a_message(from_agent, to_agent, msg_type, action=None, payload=None, priority="normal", ttl=3600, reply_to=None):
    """Create an A2A message object."""
    now = datetime.now()
    return {
        "id": make_activity_id(),
        "from_agent": from_agent,
        "to_agent": to_agent,
        "type": msg_type,  # request | response | notification
        "action": action,
        "payload": payload or {},
        "priority": priority,
        "reply_to": reply_to,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=ttl)).isoformat(),
        "ttl": ttl
    }

def get_agent_status(data, agent_name):
    """Get agent status with online/offline computation."""
    agents = data.get("agents", {})
    if agent_name not in agents:
        return None
    agent = agents[agent_name].copy()
    try:
        last_seen = datetime.fromisoformat(agent.get("last_seen", "")).timestamp()
        agent["online"] = (time.time() - last_seen) < 60
        agent["status"] = "online" if agent["online"] else "offline"
    except:
        agent["online"] = False
        agent["status"] = "offline"
    return agent

# --- UI ---
_UI = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>ACP Minimal v1.0.6</title>
    <style>
        :root { --bg:#0d1117; --card:#161b22; --border:#30363d; --text:#c9d1d9; --primary:#ff6b35; --success:#238636; --danger:#da3633; --warning:#d29922; --info:#58a6ff; }
        body { font-family:'Segoe UI',system-ui,sans-serif; background:var(--bg); color:var(--text); margin:0; padding:20px; }
        .container { max-width:1200px; margin:0 auto; }
        .header { display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--border); padding-bottom:15px; margin-bottom:20px; }
        .sys-controls { display:flex; gap:8px; flex-wrap:wrap; }
        .btn { padding:8px 14px; border-radius:6px; cursor:pointer; border:1px solid var(--border); font-weight:600; font-size:0.85rem; color:white; transition:0.2s; }
        .btn:hover { opacity:0.8; }
        .btn-stop { background:var(--danger); border:none; }
        .btn-resume { background:var(--success); border:none; }
        .btn-restart { background:#21262d; }
        .btn-shutdown { background:#484f58; }
        .btn-nudge { background:var(--primary); border:none; }
        .btn-export { background:var(--info); border:none; }
        .stop-banner { background:rgba(218,54,51,0.12); border:1px solid var(--danger); color:var(--danger); padding:12px 16px; border-radius:8px; margin-bottom:16px; display:flex; justify-content:space-between; align-items:center; font-weight:600; }
        .stats-bar { display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); gap:10px; margin-bottom:20px; }
        .stat-card { background:var(--card); border:1px solid var(--border); padding:12px; border-radius:8px; text-align:center; }
        .stat-label { font-size:0.62rem; color:#8b949e; text-transform:uppercase; letter-spacing:0.5px; }
        .stat-val { display:block; font-size:0.95rem; font-family:monospace; color:var(--primary); margin-top:4px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .stat-val.warn { color:var(--warning); } .stat-val.danger { color:var(--danger); }
        .grid { display:grid; grid-template-columns:1fr 300px; gap:20px; }
        @media (max-width:900px) { .grid { grid-template-columns:1fr; } }
        .panel { background:var(--card); border:1px solid var(--border); border-radius:8px; margin-bottom:15px; overflow:hidden; animation:fadeIn 0.3s ease-out; }
        @keyframes fadeIn { from { opacity:0; transform:translateY(5px); } to { opacity:1; transform:translateY(0); } }
        .panel-header { background:rgba(255,255,255,0.03); padding:10px 15px; display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--border); }
        .panel-title { font-weight:600; font-size:0.9rem; }
        .panel-body { padding:12px; max-height:400px; overflow-y:auto; }
        .panel-footer { background:rgba(0,0,0,0.2); padding:8px 15px; font-size:0.75rem; color:#8b949e; display:flex; gap:15px; border-top:1px solid var(--border); flex-wrap:wrap; }
        .status-pill { font-size:0.65rem; padding:2px 8px; border-radius:10px; font-weight:bold; text-transform:uppercase; }
        .status-running { background:rgba(56,139,253,0.15); color:#58a6ff; border:1px solid #58a6ff; }
        .status-completed { background:rgba(63,185,80,0.15); color:#3fb950; border:1px solid #3fb950; }
        .status-error,.status-cancelled { background:rgba(248,81,73,0.15); color:#f85149; border:1px solid #f85149; }
        .tag { font-family:monospace; font-size:0.7rem; color:#8b949e; }
        pre { background:#07090e; padding:10px; border-radius:6px; font-size:0.8rem; overflow-x:auto; border:1px solid #21262d; margin-top:8px; color:#88ee88; white-space:pre-wrap; word-break:break-all; }
        .nudge-banner { background:rgba(255,107,53,0.1); border:1px solid var(--primary); color:var(--primary); padding:12px; border-radius:8px; margin-bottom:16px; display:flex; justify-content:space-between; align-items:center; }
        .orphan-banner { background:rgba(210,153,34,0.1); border:1px solid var(--warning); color:var(--warning); padding:12px; border-radius:8px; margin-bottom:16px; }
        .activity-item { border:1px solid var(--border); border-radius:6px; margin-bottom:10px; overflow:hidden; }
        .activity-header { background:rgba(255,255,255,0.02); padding:8px 12px; display:flex; justify-content:space-between; align-items:center; gap:8px; }
        .activity-body { padding:10px 12px; font-size:0.85rem; }
        .activity-target { font-family:monospace; color:var(--info); margin-bottom:4px; word-break:break-all; }
        .todo-item { display:flex; align-items:center; gap:10px; padding:8px; border-bottom:1px solid var(--border); }
        .todo-item:last-child { border-bottom:none; }
        .todo-checkbox { width:16px; height:16px; cursor:pointer; }
        .todo-content { flex:1; font-size:0.85rem; }
        .todo-priority { font-size:0.65rem; padding:2px 6px; border-radius:4px; flex-shrink:0; }
        .priority-high { background:rgba(248,81,73,0.2); color:#f85149; }
        .priority-medium { background:rgba(210,153,34,0.2); color:#d29922; }
        .priority-low { background:rgba(56,139,253,0.2); color:#58a6ff; }
        .shell-item { font-family:monospace; font-size:0.75rem; padding:6px 10px; border-bottom:1px solid var(--border); display:flex; justify-content:space-between; gap:8px; }
        .shell-cmd { color:var(--info); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .agent-badge { display:inline-block; padding:2px 8px; border-radius:4px; font-size:0.7rem; }
        .agent-primary { background:rgba(255,107,53,0.2); color:var(--primary); border:1px solid rgba(255,107,53,0.4); }
        .agent-other { background:rgba(88,166,255,0.2); color:var(--info); }
        .progress-bar { height:4px; background:var(--border); border-radius:2px; margin-top:6px; overflow:hidden; }
        .progress-fill { height:100%; background:var(--primary); transition:width 0.3s; }
        .progress-fill.warn { background:var(--warning); } .progress-fill.danger { background:var(--danger); }
        .a2a-badge { background:rgba(136,238,136,0.2); color:#88ee88; border:1px solid #88ee88; }
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <div>
            <h2 style="margin:0;color:var(--primary)">&#x1F916; ACP Minimal <small style="color:#6e7681;font-size:0.8rem">v1.0.6</small></h2>
            <div id="timer" style="font-family:monospace;font-size:0.8rem;color:#8b949e;margin-top:4px">Sync in 2.0s</div>
        </div>
        <div class="sys-controls">
            <button class="btn btn-nudge" onclick="sendNudge()">&#x1F4E2; NUDGE</button>
            <button class="btn btn-export" onclick="exportSummary()">&#x1F4C4; EXPORT</button>
            <button class="btn btn-stop" onclick="doStop()">&#x26D4; STOP</button>
            <button class="btn btn-resume" onclick="doResume()" id="btn-resume" style="display:none">&#x25B6;&#xFE0F; RESUME</button>
            <button class="btn btn-restart" onclick="sys('reset')">&#x1F504; RESET</button>
            <button class="btn btn-shutdown" onclick="sys('shutdown')">&#x1F480; KILL</button>
        </div>
    </div>
    <div id="stop-area"></div>
    <div id="nudge-area"></div>
    <div id="orphan-area"></div>
    <div class="stats-bar">
        <div class="stat-card"><span class="stat-label">Tokens</span><span id="stat-tokens" class="stat-val">0</span><div class="progress-bar"><div id="token-bar" class="progress-fill" style="width:0%"></div></div></div>
        <div class="stat-card"><span class="stat-label">Context</span><span id="stat-pc" class="stat-val">0%</span></div>
        <div class="stat-card"><span class="stat-label">Running</span><span id="stat-running" class="stat-val">0</span></div>
        <div class="stat-card"><span class="stat-label">Completed</span><span id="stat-completed" class="stat-val">0</span></div>
        <div class="stat-card"><span class="stat-label">Primary Agent</span><span id="stat-primary-agent" class="stat-val">---</span></div>
        <div class="stat-card"><span class="stat-label">Last Agent</span><span id="stat-last-agent" class="stat-val">---</span></div>
        <div class="stat-card"><span class="stat-label">Session</span><span id="stat-session" class="stat-val">0m</span></div>
        <div class="stat-card"><span class="stat-label">Todos</span><span id="stat-todos" class="stat-val">0</span></div>
        <div class="stat-card"><span class="stat-label">Errors</span><span id="stat-errors" class="stat-val">0</span></div>
        <div class="stat-card"><span class="stat-label">A2A Pending</span><span id="stat-a2a" class="stat-val">0</span></div>
    </div>
    <div class="grid">
        <div id="main-content">
            <div id="running-section"></div>
            <div id="history-section"></div>
        </div>
        <div id="sidebar">
            <div id="todos-panel"></div>
            <div id="agents-panel"></div>
            <div id="shell-panel"></div>
            <div id="hints-panel"></div>
        </div>
    </div>
</div>
<script>
    const AUTH = btoa('__USER__:__PASS__');
    let timeLeft = 2.0, lastData = null;

    async function api(path, opts={}) {
        try {
            const r = await fetch(path, {...opts, headers:{'Authorization':'Basic '+AUTH,'Content-Type':'application/json'}});
            return r.json();
        } catch(e) { return {error:true}; }
    }

    async function sys(type) {
        if(!confirm('Confirm '+type.toUpperCase()+'?')) return;
        const r = await api('/api/'+type, {method:'POST'});
        if(type==='shutdown') { document.body.innerHTML='<h1 style="color:#da3633;font-family:monospace;padding:40px">Server offline.</h1>'; return; }
        timeLeft = 0.1;
    }

    async function doStop() {
        const reason = prompt('Reason for STOP ALL (optional):') ?? '';
        await api('/api/stop', {method:'POST', body:JSON.stringify({reason: reason||'User requested'})});
        timeLeft = 0.1;
    }

    async function doResume() {
        await api('/api/resume', {method:'POST'});
        timeLeft = 0.1;
    }

    async function sendNudge() {
        const m = prompt('Enter guidance message:');
        if(m) { await api('/api/nudge', {method:'POST', body:JSON.stringify({message:m})}); timeLeft = 0.1; }
    }

    async function exportSummary() {
        const r = await api('/api/summary/export');
        if(r.summary) {
            const blob = new Blob([r.summary], {type:'text/markdown'});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href=url; a.download='acp-session-summary.md'; a.click();
            URL.revokeObjectURL(url);
        }
    }

    async function toggleTodo(id) {
        await api('/api/todos/toggle', {method:'POST', body:JSON.stringify({id})});
        timeLeft = 0.1;
    }

    function dur(ms) {
        if(!ms) return '---';
        if(ms<1000) return ms+'ms';
        if(ms<60000) return (ms/1000).toFixed(1)+'s';
        return (ms/60000).toFixed(1)+'m';
    }

    function sess(s) {
        if(s<60) return s+'s';
        if(s<3600) return Math.floor(s/60)+'m';
        return Math.floor(s/3600)+'h '+Math.floor((s%3600)/60)+'m';
    }

    function esc(s) {
        return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }

    async function refresh() {
        const d = await api('/api/all');
        if(d.error) return;
        lastData = d;

        const pct = d.tokens_percent || 0;
        document.getElementById('stat-tokens').innerText = (d.session_tokens||0).toLocaleString();
        document.getElementById('stat-pc').innerText = pct.toFixed(1)+'%';
        document.getElementById('stat-pc').className = 'stat-val'+(pct>80?' danger':pct>50?' warn':'');
        document.getElementById('stat-running').innerText = (d.running||[]).length;
        document.getElementById('stat-completed').innerText = (d.history||[]).length;
        document.getElementById('stat-primary-agent').innerText = d.primary_agent || '---';
        document.getElementById('stat-last-agent').innerText = d.last_agent || '---';
        document.getElementById('stat-session').innerText = sess(d.session?.elapsed_seconds||0);
        document.getElementById('stat-todos').innerText = (d.todos||[]).length;
        document.getElementById('stat-errors').innerText = (d.errors||[]).length;
        
        // A2A pending count
        const a2aPending = d.hints?.a2a?.pending_count || 0;
        document.getElementById('stat-a2a').innerText = a2aPending;
        document.getElementById('stat-a2a').className = 'stat-val'+(a2aPending>0?' a2a-badge':'');

        const bar = document.getElementById('token-bar');
        bar.style.width = Math.min(100,pct)+'%';
        bar.className = 'progress-fill'+(pct>80?' danger':pct>50?' warn':'');

        // STOP banner + resume button
        const stopArea = document.getElementById('stop-area');
        const resumeBtn = document.getElementById('btn-resume');
        if(d.stop_flag) {
            stopArea.innerHTML = '<div class="stop-banner">&#x26D4; STOP ALL ACTIVE'+(d.stop_reason?' &mdash; '+esc(d.stop_reason):'')+'&nbsp;<span style="font-size:0.8rem;font-weight:normal">All agent operations halted.</span></div>';
            resumeBtn.style.display = '';
        } else {
            stopArea.innerHTML = '';
            resumeBtn.style.display = 'none';
        }

        document.getElementById('nudge-area').innerHTML = d.nudge
            ? '<div class="nudge-banner"><span><strong>&#x1F4E2; NUDGE:</strong> '+esc(d.nudge.message)+'</span><small>'+esc(d.nudge.timestamp||'')+'</small></div>'
            : '';

        document.getElementById('orphan-area').innerHTML = d.orphan_warning
            ? '<div class="orphan-banner"><strong>&#x26A0;&#xFE0F; ORPHAN WARNING:</strong> '+d.orphan_warning.count+' activit'+(d.orphan_warning.count===1?'y':'ies')+' running > 5min</div>'
            : '';

        function patchPanel(container, title, bodyHTML, bodyStyle) {
            const existing = container.querySelector('.panel');
            if (!existing) {
                const style = bodyStyle ? ' style="'+bodyStyle+'"' : '';
                container.innerHTML = '<div class="panel"><div class="panel-header"><span class="panel-title">'+title+'</span></div><div class="panel-body"'+style+'>'+bodyHTML+'</div></div>';
                return;
            }
            existing.querySelector('.panel-title').innerHTML = title;
            const pb = existing.querySelector('.panel-body');
            if (bodyStyle) pb.setAttribute('style', bodyStyle);
            const saved = pb.scrollTop;
            pb.innerHTML = bodyHTML;
            pb.scrollTop = saved;
        }

        // Running
        const rs = document.getElementById('running-section');
        if (d.running && d.running.length) {
            const runBody = d.running.map(a => {
                const m=a.metadata||{};
                return '<div class="activity-item"><div class="activity-header"><span class="status-pill status-running">'+a.status+'</span><strong>'+esc(a.action)+'</strong><span class="tag">#'+a.id+'</span></div>'
                    +'<div class="activity-body"><div class="activity-target">'+esc(a.target||'N/A')+'</div><div>'+esc(a.details||'')+'</div></div>'
                    +'<div class="panel-footer"><span>&#x1F464; '+esc(m.agent_name||'---')+(m.model_name?' &middot; '+esc(m.model_name):'')+'</span><span>&#x1F552; '+esc(a.started||'---')+'</span></div></div>';
            }).join('');
            patchPanel(rs, '&#x1F504; Running ('+d.running.length+')', runBody, '');
        } else {
            rs.innerHTML = '';
        }

        // History
        const hs = document.getElementById('history-section');
        if (d.history && d.history.length) {
            const histBody = d.history.slice(0,25).map(a => {
                const m=a.metadata||{};
                const sc = a.status==='error'||a.status==='cancelled'?'error':'completed';
                return '<div class="activity-item"><div class="activity-header"><span class="status-pill status-'+sc+'">'+a.status+'</span><strong>'+esc(a.action)+'</strong><span class="tag">#'+a.id+'</span></div>'
                    +'<div class="activity-body"><div class="activity-target">'+esc(a.target||'N/A')+'</div><div>'+esc(a.details||'')+'</div>'+(a.result?'<pre>'+esc(a.result)+'</pre>':'')+'</div>'
                    +'<div class="panel-footer"><span>&#x1F464; '+esc(m.agent_name||'---')+(m.model_name?' &middot; '+esc(m.model_name):'')+'</span><span>&#x1F552; '+esc(a.started||'---')+'</span><span>&#x23F1;&#xFE0F; '+dur(a.duration_ms)+'</span></div></div>';
            }).join('');
            patchPanel(hs, '&#x1F4DC; History ('+d.history.length+')', histBody, '');
        } else {
            hs.innerHTML = '<div style="text-align:center;padding:40px;color:#6e7681">No activity logged yet.</div>';
        }

        // Todos
        const tp = document.getElementById('todos-panel');
        if (d.todos && d.todos.length) {
            const todoBody = d.todos.map(t => '<div class="todo-item"><input type="checkbox" class="todo-checkbox" data-id="'+t.id+'" '+(t.status==='completed'?'checked':'')+' onchange="toggleTodo(event.target.dataset.id)"><span class="todo-content" style="'+(t.status==='completed'?'text-decoration:line-through;opacity:0.6':'')+'">'+esc(t.content)+'</span><span class="todo-priority priority-'+(t.priority||'medium')+'">'+(t.priority||'med')+'</span></div>').join('');
            patchPanel(tp, '&#x1F4CB; Todos ('+d.todos.length+')', todoBody, 'padding:0');
        } else { tp.innerHTML = ''; }

        // Agents — primary_agent gets orange star badge
        const ap = document.getElementById('agents-panel');
        const agents = d.agents || {};
        const agentTokens = d.agent_tokens || {};
        const allAgentNames = new Set([...Object.keys(agents), ...Object.keys(agentTokens)]);
        if (allAgentNames.size) {
            const agentBody = Array.from(allAgentNames).map(n => {
                const ag = agents[n] || {};
                const tok = agentTokens[n] || 0;
                const isPrimary = n === d.primary_agent;
                const status = ag.status || (isPrimary ? 'online' : 'offline');
                const statusClass = status === 'online' ? 'status-running' : 'status-error';
                return '<div style="display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid var(--border)"><span class="agent-badge '+(isPrimary?'agent-primary':'agent-other')+'">'+esc(n)+(isPrimary?' &#x2605;':'')+'</span><span><span class="status-pill '+statusClass+'" style="font-size:0.6rem">'+status+'</span> <span class="tag">'+tok+' tok</span></span></div>';
            }).join('');
            patchPanel(ap, '&#x1F916; Agents ('+allAgentNames.size+')', agentBody, '');
        } else { ap.innerHTML = ''; }

        // Shell
        const sp = document.getElementById('shell-panel');
        if (d.shell_history && d.shell_history.length) {
            const shellBody = d.shell_history.slice(0,10).map(s => '<div class="shell-item"><span class="shell-cmd" title="'+esc(s.command||'')+'">'+esc(s.command||'---')+'</span><span class="shell-status '+(s.status==='error'?'status-error':'status-completed')+'">'+s.status+'</span></div>').join('');
            patchPanel(sp, '&#x1F4BB; Shell ('+d.shell_history.length+')', shellBody, 'padding:0');
        } else { sp.innerHTML = ''; }

        // Hints
        const hp = document.getElementById('hints-panel');
        if (d.hints && (d.hints.loop_detected || d.hints.active_todos > 0 || (d.hints.a2a && d.hints.a2a.pending_count > 0))) {
            const hintsBody = (d.hints.loop_detected?'<div style="color:var(--warning);margin-bottom:8px">&#x26A0;&#xFE0F; Loop detected: '+d.hints.loop_count+' repetitions</div>':'')
                + (d.hints.suggestion?'<div style="color:var(--info)">'+esc(d.hints.suggestion)+'</div>':'')
                + (d.hints.active_todos>0?'<div class="tag">&#x1F4CC; '+d.hints.active_todos+' active todos</div>':'')
                + (d.hints.a2a && d.hints.a2a.pending_count>0?'<div class="tag" style="color:#88ee88">&#x1F4E7; '+d.hints.a2a.pending_count+' A2A messages from: '+esc(d.hints.a2a.senders?.join(', ')||'unknown')+'</div>':'');
            patchPanel(hp, '&#x1F4A1; Hints', hintsBody, '');
        } else { hp.innerHTML = ''; }
    }

    setInterval(() => {
        timeLeft -= 0.1;
        if(timeLeft <= 0) { timeLeft = 2.0; refresh(); }
        document.getElementById('timer').innerText = 'Sync in '+Math.max(0,timeLeft).toFixed(1)+'s';
    }, 100);
    refresh();
</script>
</body>
</html>
"""

def build_ui():
    return _UI.replace('__USER__', AUTH_USER).replace('__PASS__', AUTH_PASS)

UI_HTML = build_ui()


# --- HANDLER ---
class ACPMinimalHandler(BaseHTTPRequestHandler):

    def send_json(self, data, status=200):
        body = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def check_auth(self):
        auth = self.headers.get('Authorization', '')
        if auth.startswith('Basic '):
            try:
                u, p = base64.decodebytes(auth[6:].encode()).decode().split(':', 1)
                if u == AUTH_USER and p == AUTH_PASS:
                    return True
            except:
                pass
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="ACP"')
        self.end_headers()
        return False

    def log_message(self, format, *args):
        pass

    def read_body(self):
        """Read and parse JSON body from request."""
        try:
            length = int(self.headers.get('Content-Length', 0))
            if length > 0:
                return json.loads(self.rfile.read(length))
        except:
            pass
        return {}

    # ============================================================
    # OPTIONS (CORS preflight)
    # ============================================================
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')
        self.send_header('Content-Length', '0')
        self.end_headers()

    # ============================================================
    # GET
    # ============================================================
    def do_GET(self):
        if not self.check_auth():
            return

        # UI
        if self.path in ['/', '/api']:
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(UI_HTML.encode('utf-8'))

        # /.well-known/agent-card.json — 1.0.4 A2A Discovery
        elif self.path == '/.well-known/agent-card.json':
            # Dynamic URL from request headers
            host = self.headers.get('Host', f'localhost:{PORT}')
            scheme = 'https' if self.headers.get('X-Forwarded-Proto', '').lower() == 'https' else 'http'
            card = dict(ACP_AGENT_CARD)
            card["url"] = f"{scheme}://{host}"
            self.send_json(card)

        # /api/whoami — spec §4.10: returns identity context for agent bootstrap
        elif self.path == '/api/whoami':
            d = load_data()
            self.send_json({
                "success": True,
                "identity": {
                    "hint": "You are an AI agent. Identify yourself by name (e.g., 'Super Z', 'Claude', 'GPT-4').",
                    "suggestion": "Use the 'agent_name' field in activity metadata to attribute your actions.",
                    "example": {"metadata": {"agent_name": "Super Z", "source": "user_request"}},
                    "purpose": "Attribution helps track which agent/subagent performed each action."
                },
                "session": get_session_info(),
                "primary_agent": d.get("primary_agent"),
                "last_agent": d.get("last_agent", "Unknown"),
                "agent_tokens": d.get("agent_tokens", {})
            })

        # /api/status — spec §4.3
        elif self.path == '/api/status':
            d = load_data()
            tok = get_token_summary(d)
            orphans = check_orphans(d)
            self.send_json({
                "success": True,
                "stop_flag": d["stop_flag"],
                "stop_reason": d.get("stop_reason"),
                "running_count": len(d["running"]),
                "running": d["running"],
                "session_tokens": tok["session_tokens"],
                "startup_tokens": tok["startup_tokens"],
                "activity_tokens": tok["activity_tokens"],
                "context_window": CONTEXT_WINDOW,
                "tokens_remaining": tok["tokens_remaining"],
                "tokens_percent": tok["tokens_percent"],
                "overflow_warning": tok["overflow_warning"],
                "primary_agent": d.get("primary_agent"),
                "last_agent": d.get("last_agent", "Unknown"),
                "agent_tokens": d.get("agent_tokens", {}),
                "other_agents_tokens": tok["other_agents_tokens"],
                "tunnel_url": tok["tunnel_url"],
                "nudge": d["nudge"],
                "session": get_session_info(),
                "orphan_warning": {"count": len(orphans), "tasks": orphans} if orphans else None,
                "errors": d.get("errors", [])[-5:],
                "agents": d.get("agents", {})
            })

        # /api/all — combined convenience endpoint, spec §4.3
        elif self.path == '/api/all':
            d = load_data()
            tok = get_token_summary(d)
            orphans = check_orphans(d)
            # Get hints with A2A info for primary agent
            hints = get_hints(d, "", d.get("primary_agent"))
            base_dir = os.environ.get("ACP_BASE_DIR", ".")
            current_files = []
            try:
                for item in sorted(os.listdir(base_dir))[:20]:
                    ip = os.path.join(base_dir, item)
                    current_files.append({
                        "name": item,
                        "is_dir": os.path.isdir(ip),
                        "size": os.path.getsize(ip) if os.path.isfile(ip) else 0
                    })
            except:
                pass
            self.send_json({
                "success": True,
                "stop_flag": d["stop_flag"],
                "stop_reason": d.get("stop_reason"),
                "running": d["running"],
                "history": d["history"][:25],
                "session_tokens": tok["session_tokens"],
                "startup_tokens": tok["startup_tokens"],
                "context_window": CONTEXT_WINDOW,
                "tokens_remaining": tok["tokens_remaining"],
                "tokens_percent": tok["tokens_percent"],
                "overflow_warning": tok["overflow_warning"],
                "primary_agent": d.get("primary_agent"),
                "last_agent": d.get("last_agent", "Unknown"),
                "agent_tokens": d.get("agent_tokens", {}),
                "other_agents_tokens": tok["other_agents_tokens"],
                "tunnel_url": tok["tunnel_url"],
                "nudge": d["nudge"],
                "session": get_session_info(),
                "todos": d.get("todos", []),
                "shell_history": d.get("shell_history", [])[-10:],
                "errors": d.get("errors", []),
                "orphan_warning": {"count": len(orphans), "tasks": orphans} if orphans else None,
                "current_files": current_files,
                "base_dir": os.path.abspath(base_dir),
                "hints": hints,
                "agents": d.get("agents", {})
            })

        # /api/running — spec §4.3
        elif self.path == '/api/running':
            d = load_data()
            self.send_json({"success": True, "running": d["running"]})

        # /api/history — spec §4.3
        elif self.path == '/api/history':
            d = load_data()
            self.send_json({"success": True, "history": d["history"]})

        # /api/activity/{id} — spec §4.3
        elif self.path.startswith('/api/activity/') and '/batch' not in self.path:
            aid = self.path.split('/')[-1]
            d = load_data()
            for a in d["running"] + d["history"]:
                if a["id"] == aid:
                    return self.send_json({"success": True, "activity": a})
            self.send_json({"success": False, "error": "Activity not found"}, 404)

        # /api/todos — spec §4.4
        elif self.path == '/api/todos':
            d = load_data()
            self.send_json({"success": True, "todos": d.get("todos", [])})

        # /api/notes — spec §4.6 (structured array)
        elif self.path == '/api/notes':
            d = load_data()
            self.send_json({"success": True, "notes": d.get("notes", [])})

        # /api/shell — spec §4.5
        elif self.path == '/api/shell':
            d = load_data()
            self.send_json({"success": True, "shell_history": d.get("shell_history", [])})

        # /api/summary — spec §4.6 (structured response)
        elif self.path == '/api/summary':
            d = load_data()
            self.send_json({"success": True, "summary": build_summary_struct(d)})

        # /api/summary/export — spec §4.6 (writes persistent .md file)
        elif self.path == '/api/summary/export':
            d = load_data()
            try:
                filepath, content = write_summary_file(d)
                self.send_json({
                    "success": True,
                    "message": "Summary exported to persistent file",
                    "filepath": filepath,
                    "note": "Share this file with new AI sessions for context recovery",
                    "summary": content
                })
            except Exception as e:
                self.send_json({"success": False, "error": str(e)}, 500)

        # /api/stats/duration — spec §4.3
        elif self.path == '/api/stats/duration':
            d = load_data()
            self.send_json({"success": True, "stats": calc_duration_stats(d)})

        # /api/session — spec §4.3
        elif self.path == '/api/session':
            self.send_json({"success": True, "session": get_session_info()})

        # /api/nudge — spec §3.9: check pending nudge (GET)
        elif self.path == '/api/nudge':
            d = load_data()
            nudge = d.get("nudge")
            self.send_json({
                "success": True,
                "nudge": nudge,
                "has_pending": nudge is not None
            })

        # /api/csrf-token — spec §4.2
        elif self.path == '/api/csrf-token':
            self.send_json({
                "success": True,
                "csrf_enabled": False,
                "message": "CSRF protection is disabled by default"
            })

        # /api/agents — 1.0.4: List all registered agents
        elif self.path == '/api/agents':
            d = load_data()
            agents = d.get("agents", {})
            agent_list = []
            for name in agents:
                agent = get_agent_status(d, name)
                if agent:
                    agent_list.append(agent)
            self.send_json({
                "success": True,
                "agents": agent_list,
                "count": len(agent_list),
                "primary_agent": d.get("primary_agent")
            })

        # /api/agents/{name} — 1.0.4: Get specific agent
        elif self.path.startswith('/api/agents/') and self.path.count('/') == 3:
            name = self.path.split('/')[-1]
            if name in ['register', 'unregister']:
                # Let POST handle these
                self.send_json({"success": False, "error": "Use POST method"}, 405)
                return
            d = load_data()
            agent = get_agent_status(d, name)
            if agent:
                self.send_json({"success": True, "agent": agent})
            else:
                self.send_json({"success": False, "error": f"Agent '{name}' not found"}, 404)

        # /api/a2a/history — 1.0.4: Get A2A message history
        elif self.path.startswith('/api/a2a/history'):
            d = load_data()
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            
            messages = d.get("a2a_messages", [])
            to_agent = params.get('to', [None])[0]
            from_agent = params.get('from', [None])[0]
            msg_type = params.get('type', [None])[0]
            
            # Filter messages
            if to_agent:
                messages = [m for m in messages if m.get("to_agent") == to_agent]
            if from_agent:
                messages = [m for m in messages if m.get("from_agent") == from_agent]
            if msg_type:
                messages = [m for m in messages if m.get("type") == msg_type]
            
            # Filter out expired messages
            now_ts = time.time()
            valid_messages = []
            for m in messages:
                try:
                    expires = datetime.fromisoformat(m["expires_at"]).timestamp()
                    if expires > now_ts:
                        valid_messages.append(m)
                except:
                    pass
            
            self.send_json({
                "success": True,
                "messages": valid_messages,
                "count": len(valid_messages)
            })

        # File manager endpoints (read-only)
        elif self.path.startswith('/api/files/'):
            base_dir = os.environ.get("ACP_BASE_DIR", ".")
            parts = self.path[len('/api/files/'):].split('/')
            action = parts[0]
            
            if action == 'list':
                try:
                    rel = '/'.join(parts[1:]) if len(parts) > 1 else ''
                    path = sanitize_path(base_dir, rel)
                    if path is None:
                        self.send_json({"success": False, "error": "Path traversal denied"}, 403)
                        return
                    items = []
                    for item in sorted(os.listdir(path))[:50]:
                        ip = os.path.join(path, item)
                        items.append({
                            "name": item,
                            "is_dir": os.path.isdir(ip),
                            "size": os.path.getsize(ip) if os.path.isfile(ip) else 0,
                            "modified": datetime.fromtimestamp(os.path.getmtime(ip)).isoformat()
                        })
                    self.send_json({"success": True, "files": items, "path": os.path.abspath(path)})
                except Exception as e:
                    self.send_json({"success": False, "error": str(e)}, 500)
            
            elif action == 'view':
                try:
                    rel_path = '/'.join(parts[1:])
                    path = sanitize_path(base_dir, rel_path)
                    if path is None:
                        self.send_json({"success": False, "error": "Path traversal denied"}, 403)
                        return
                    if os.path.isfile(path):
                        with open(path, 'r', encoding='utf-8') as f:
                            content = f.read(100000)  # 100KB limit
                        self.send_json({"success": True, "content": content, "path": path})
                    else:
                        self.send_json({"success": False, "error": "Not a file"}, 400)
                except Exception as e:
                    self.send_json({"success": False, "error": str(e)}, 500)
            
            elif action == 'download':
                try:
                    rel_path = '/'.join(parts[1:])
                    path = sanitize_path(base_dir, rel_path)
                    if path is None:
                        self.send_json({"success": False, "error": "Path traversal denied"}, 403)
                        return
                    if os.path.isfile(path):
                        with open(path, 'rb') as f:
                            content = f.read()
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/octet-stream')
                        self.send_header('Content-Disposition', f'attachment; filename="{os.path.basename(path)}"')
                        self.send_header('Content-Length', str(len(content)))
                        self.end_headers()
                        self.wfile.write(content)
                    else:
                        self.send_json({"success": False, "error": "Not a file"}, 400)
                except Exception as e:
                    self.send_json({"success": False, "error": str(e)}, 500)
            
            elif action == 'stats':
                try:
                    rel_path = '/'.join(parts[1:])
                    path = sanitize_path(base_dir, rel_path)
                    if path is None:
                        self.send_json({"success": False, "error": "Path traversal denied"}, 403)
                        return
                    if os.path.exists(path):
                        self.send_json({
                            "success": True,
                            "path": path,
                            "is_dir": os.path.isdir(path),
                            "size": os.path.getsize(path) if os.path.isfile(path) else 0,
                            "modified": datetime.fromtimestamp(os.path.getmtime(path)).isoformat()
                        })
                    else:
                        self.send_json({"success": False, "error": "Not found"}, 404)
                except Exception as e:
                    self.send_json({"success": False, "error": str(e)}, 500)
            
            else:
                self.send_json({"success": False, "error": "Unknown files action"}, 400)

        else:
            self.send_json({"success": False, "error": "Not found"}, 404)

    # ============================================================
    # POST
    # ============================================================
    def do_POST(self):
        if not self.check_auth():
            return
        
        body = self.read_body()

        # JSON-RPC 2.0 endpoints (1.0.4)
        if self.path in ['/jsonrpc', '/a2a', '/api/jsonrpc']:
            self._handle_jsonrpc(body)
            return

        # /api/action — combined endpoint
        elif self.path == '/api/action':
            d = load_data()
            if d["stop_flag"]:
                self.send_json({"success": False, "error": "Stop requested"}, 403)
                return

            # Complete previous if provided
            if body.get("complete_id"):
                for i, a in enumerate(d["running"]):
                    if a["id"] == body["complete_id"]:
                        a["status"] = "error" if body.get("error") else "completed"
                        a["completed"] = datetime.now().isoformat()
                        a["result"] = (body.get("result") or "")[:500]
                        a["error"] = str(body.get("error", ""))[:200] if body.get("error") else None
                        output_tokens = estimate_tokens([a.get("result", ""), str(body.get("error", ""))])
                        if body.get("complete_content_size"):
                            output_tokens += int(body["complete_content_size"] / 3.5)
                        a["tokens_out"] = output_tokens
                        try:
                            started = datetime.fromisoformat(a["started"])
                            completed = datetime.fromisoformat(a["completed"])
                            a["duration_ms"] = int((completed - started).total_seconds() * 1000)
                        except:
                            pass
                        d["history"].insert(0, d["running"].pop(i))
                        if len(d["history"]) > 100:
                            d["history"] = d["history"][:100]
                        
                        # Update agent tokens
                        m = a.get("metadata", {})
                        agent_name = m.get("agent_name", "Unknown")
                        if agent_name not in d.get("agent_tokens", {}):
                            d["agent_tokens"][agent_name] = 0
                        d["agent_tokens"][agent_name] += output_tokens
                        if agent_name == d.get("primary_agent"):
                            d["tokens"] = d.get("tokens", 0) + output_tokens
                        break

            # Start new activity
            action = body.get("action", "UNKNOWN")
            target = body.get("target", "")
            details = body.get("details", "")
            content_size = body.get("content_size", 0)
            priority = body.get("priority", "medium")
            metadata = body.get("metadata", {})

            started_ts = time.time()
            started = datetime.now().isoformat()
            activity_id = make_activity_id()
            
            input_tokens = estimate_tokens([action, target, details], content_size)
            
            activity = {
                "id": activity_id,
                "action": action,
                "target": target,
                "details": details,
                "status": "running",
                "started": started,
                "started_ts": started_ts,
                "tokens_in": input_tokens,
                "priority": priority,
            }
            if metadata:
                activity["metadata"] = metadata

            d["running"].append(activity)
            
            # Update primary agent tracking
            agent_name = metadata.get("agent_name", "Unknown")
            if not d.get("primary_agent"):
                d["primary_agent"] = agent_name
            
            # Update agent_tokens
            if agent_name not in d.get("agent_tokens", {}):
                d["agent_tokens"][agent_name] = 0
            d["agent_tokens"][agent_name] += input_tokens
            d["tokens"] = d.get("tokens", 0) + input_tokens
            
            d["last_agent"] = agent_name
            if metadata.get("model_name"):
                d["last_model"] = metadata["model_name"]

            save_data(d)
            
            # Get hints with A2A info
            hints = get_hints(d, target, agent_name)
            orphans = check_orphans(d)
            
            # 1.0.5: Only deliver nudge to primary agent
            nudge = d.get("nudge")
            if agent_name and d.get("primary_agent") and agent_name != d.get("primary_agent"):
                nudge = None  # Secondary agents don't receive nudges
            
            self.send_json({
                "success": True,
                "activity_id": activity_id,
                "stop_flag": d["stop_flag"],
                "session_tokens": d["tokens"],
                "context_window": CONTEXT_WINDOW,
                "tokens_remaining": CONTEXT_WINDOW - d["tokens"],
                "tokens_percent": round(d["tokens"] / CONTEXT_WINDOW * 100, 2),
                "session": get_session_info(),
                "running_count": len(d["running"]),
                "hints": hints,
                "nudge": nudge,
                "orphan_warning": {"count": len(orphans), "tasks": orphans} if orphans else None
            })

        # /api/start
        elif self.path == '/api/start':
            d = load_data()
            if d["stop_flag"]:
                self.send_json({"success": False, "error": "Stop requested"}, 403)
                return

            action = body.get("action", "UNKNOWN")
            target = body.get("target", "")
            details = body.get("details", "")
            content_size = body.get("content_size", 0)
            priority = body.get("priority", "medium")
            metadata = body.get("metadata", {})

            started_ts = time.time()
            started = datetime.now().isoformat()
            activity_id = make_activity_id()
            input_tokens = estimate_tokens([action, target, details], content_size)

            activity = {
                "id": activity_id,
                "action": action,
                "target": target,
                "details": details,
                "status": "running",
                "started": started,
                "started_ts": started_ts,
                "tokens_in": input_tokens,
                "priority": priority,
            }
            if metadata:
                activity["metadata"] = metadata

            d["running"].append(activity)
            
            agent_name = metadata.get("agent_name", "Unknown")
            if not d.get("primary_agent"):
                d["primary_agent"] = agent_name
            
            if agent_name not in d.get("agent_tokens", {}):
                d["agent_tokens"][agent_name] = 0
            d["agent_tokens"][agent_name] += input_tokens
            d["tokens"] = d.get("tokens", 0) + input_tokens
            d["last_agent"] = agent_name
            if metadata.get("model_name"):
                d["last_model"] = metadata["model_name"]

            save_data(d)
            
            hints = get_hints(d, target, agent_name)
            self.send_json({
                "success": True,
                "activity_id": activity_id,
                "session_tokens": d["tokens"],
                "hints": hints
            })

        # /api/complete
        elif self.path == '/api/complete':
            d = load_data()
            aid = body.get("activity_id")
            result = body.get("result", "")
            error = body.get("error")
            content_size = body.get("content_size", 0)

            for i, a in enumerate(d["running"]):
                if a["id"] == aid:
                    a["status"] = "error" if error else "completed"
                    a["completed"] = datetime.now().isoformat()
                    a["result"] = result[:500]
                    a["error"] = str(error)[:200] if error else None
                    
                    output_tokens = estimate_tokens([result, str(error) if error else ""])
                    if content_size > 0:
                        output_tokens += int(content_size / 3.5)
                    a["tokens_out"] = output_tokens

                    try:
                        started = datetime.fromisoformat(a["started"])
                        completed = datetime.fromisoformat(a["completed"])
                        a["duration_ms"] = int((completed - started).total_seconds() * 1000)
                    except:
                        pass

                    d["history"].insert(0, d["running"].pop(i))
                    if len(d["history"]) > 100:
                        d["history"] = d["history"][:100]

                    # Update agent tokens
                    m = a.get("metadata", {})
                    agent_name = m.get("agent_name", "Unknown")
                    if agent_name not in d.get("agent_tokens", {}):
                        d["agent_tokens"][agent_name] = 0
                    d["agent_tokens"][agent_name] += output_tokens
                    if agent_name == d.get("primary_agent"):
                        d["tokens"] = d.get("tokens", 0) + output_tokens

                    save_data(d)
                    self.send_json({
                        "success": True,
                        "activity": a,
                        "session_tokens": d["tokens"],
                        "hints": get_hints(d, "", agent_name)
                    })
                    return

            self.send_json({"success": False, "error": "Activity not found"}, 404)

        # /api/activity/batch — v1.0.3
        elif self.path == '/api/activity/batch':
            d = load_data()
            ops = body.get("operations", [])[:50]  # Max 50
            results = []
            
            for op in ops:
                op_type = op.get("type")
                if op_type == "start":
                    if d["stop_flag"]:
                        results.append({"success": False, "error": "Stop requested"})
                        continue
                    action = op.get("action", "UNKNOWN")
                    target = op.get("target", "")
                    details = op.get("details", "")
                    content_size = op.get("content_size", 0)
                    metadata = op.get("metadata", {})
                    started_ts = time.time()
                    started = datetime.now().isoformat()
                    activity_id = make_activity_id()
                    input_tokens = estimate_tokens([action, target, details], content_size)
                    activity = {
                        "id": activity_id,
                        "action": action, "target": target, "details": details,
                        "status": "running", "started": started, "started_ts": started_ts,
                        "tokens_in": input_tokens, "priority": op.get("priority", "medium")
                    }
                    if metadata:
                        activity["metadata"] = metadata
                    d["running"].append(activity)
                    
                    agent_name = metadata.get("agent_name", "Unknown")
                    if not d.get("primary_agent"):
                        d["primary_agent"] = agent_name
                    if agent_name not in d.get("agent_tokens", {}):
                        d["agent_tokens"][agent_name] = 0
                    d["agent_tokens"][agent_name] += input_tokens
                    d["tokens"] = d.get("tokens", 0) + input_tokens
                    
                    results.append({"success": True, "activity_id": activity_id})
                
                elif op_type == "complete":
                    aid = op.get("activity_id")
                    for i, a in enumerate(d["running"]):
                        if a["id"] == aid:
                            a["status"] = "error" if op.get("error") else "completed"
                            a["completed"] = datetime.now().isoformat()
                            a["result"] = (op.get("result") or "")[:500]
                            a["error"] = str(op.get("error", ""))[:200] if op.get("error") else None
                            output_tokens = estimate_tokens([a.get("result", ""), str(op.get("error", ""))])
                            a["tokens_out"] = output_tokens
                            try:
                                started = datetime.fromisoformat(a["started"])
                                completed = datetime.fromisoformat(a["completed"])
                                a["duration_ms"] = int((completed - started).total_seconds() * 1000)
                            except:
                                pass
                            d["history"].insert(0, d["running"].pop(i))
                            
                            m = a.get("metadata", {})
                            agent_name = m.get("agent_name", "Unknown")
                            if agent_name not in d.get("agent_tokens", {}):
                                d["agent_tokens"][agent_name] = 0
                            d["agent_tokens"][agent_name] += output_tokens
                            if agent_name == d.get("primary_agent"):
                                d["tokens"] = d.get("tokens", 0) + output_tokens
                            
                            results.append({"success": True, "activity_id": aid})
                            break
                    else:
                        results.append({"success": False, "error": "Activity not found", "activity_id": aid})

            save_data(d)
            self.send_json({"success": True, "results": results, "session_tokens": d["tokens"]})

        # /api/stop
        elif self.path == '/api/stop':
            d = load_data()
            d["stop_flag"] = True
            d["stop_reason"] = body.get("reason", "User requested")
            # Mark all running as cancelled
            for a in d["running"]:
                a["status"] = "cancelled"
                a["completed"] = datetime.now().isoformat()
            d["history"] = d["running"] + d["history"]
            d["running"] = []
            save_data(d)
            self.send_json({"success": True, "message": "STOP ALL activated", "reason": d["stop_reason"]})

        # /api/resume
        elif self.path == '/api/resume':
            d = load_data()
            d["stop_flag"] = False
            d["stop_reason"] = None
            save_data(d)
            self.send_json({"success": True, "message": "Operations resumed"})

        # /api/shutdown
        elif self.path == '/api/shutdown':
            d = load_data()
            reason = body.get("reason", "Session ended by user")
            if body.get("export_summary", True):
                try:
                    filepath, _ = write_summary_file(d)
                except:
                    filepath = None
            else:
                filepath = None
            # Set shutdown nudge
            d["nudge"] = {
                "message": f"SESSION ENDING: {reason}. Wrap up any final thoughts.",
                "priority": "urgent",
                "requires_ack": True,
                "from": "system",
                "type": "shutdown",
                "timestamp": datetime.now().isoformat()
            }
            save_data(d)
            self.send_json({
                "success": True,
                "message": "Session ending",
                "summary_exported": bool(filepath),
                "summary_path": filepath,
                "note": "Server will stop shortly"
            })
            # Schedule shutdown
            def do_shutdown():
                time.sleep(2)
                os._exit(0)
            threading.Thread(target=do_shutdown, daemon=True).start()

        # /api/restart
        elif self.path == '/api/restart':
            save_data(load_data())
            self.send_json({"success": True, "message": "Restarting server..."})
            self.wfile.flush()
            os.execv(sys.executable, [sys.executable] + sys.argv)

        # /api/clear_history
        elif self.path == '/api/clear_history':
            d = load_data()
            cleared = len(d["history"])
            d["history"] = []
            save_data(d)
            self.send_json({"success": True, "message": f"Cleared {cleared} activities"})

        # /api/reset_session
        elif self.path == '/api/reset_session':
            d = load_data()
            old_tokens = d["tokens"]
            d["tokens"] = d.get("startup_tokens", 0)
            d["history"] = []
            d["running"] = []
            d["todos"] = []
            d["stop_flag"] = False
            d["stop_reason"] = None
            d["primary_agent"] = None
            d["agent_tokens"] = {}
            d["session_start"] = time.time()
            save_data(d)
            self.send_json({"success": True, "message": "Session reset", "tokens_cleared": old_tokens})

        # /api/reset — 1.0.4: Full reset including agents and A2A
        elif self.path == '/api/reset':
            d = load_data()
            stats = {
                "history_cleared": len(d.get("history", [])),
                "shell_cleared": len(d.get("shell_history", [])),
                "todos_cleared": len(d.get("todos", [])),
                "agents_cleared": len(d.get("agents", {})),
                "a2a_cleared": len(d.get("a2a_messages", [])),
                "tokens_reset": d.get("tokens", 0)
            }
            d.update(reset_state())
            save_data(d)
            self.send_json({
                "success": True,
                "message": "Session reset complete",
                "stats": stats
            })

        # /api/nudge
        elif self.path == '/api/nudge':
            d = load_data()
            d["nudge"] = {
                "message": body.get("message", ""),
                "priority": body.get("priority", "normal"),
                "requires_ack": body.get("requires_ack", False),
                "from": "human",
                "timestamp": datetime.now().isoformat()
            }
            save_data(d)
            self.send_json({"success": True, "message": "Nudge set", "nudge": d["nudge"]})

        # /api/nudge/ack
        elif self.path == '/api/nudge/ack':
            d = load_data()
            if d.get("nudge"):
                d["nudge"] = None
                save_data(d)
                self.send_json({"success": True, "message": "Nudge acknowledged and cleared"})
            else:
                self.send_json({"success": True, "message": "No nudge to acknowledge"})

        # /api/todos/update
        elif self.path == '/api/todos/update':
            d = load_data()
            todos = body.get("todos", [])
            for t in todos:
                if "id" not in t:
                    t["id"] = make_activity_id()
                if "created" not in t:
                    t["created"] = datetime.now().isoformat()
                if "status" not in t:
                    t["status"] = "pending"
                if "priority" not in t:
                    t["priority"] = "medium"
            d["todos"] = todos
            save_data(d)
            self.send_json({"success": True, "todos": d["todos"]})

        # /api/todos/add
        elif self.path == '/api/todos/add':
            d = load_data()
            todo = body.get("todo", {})
            todo["id"] = make_activity_id()
            todo["created"] = datetime.now().isoformat()
            todo.setdefault("status", "pending")
            todo.setdefault("priority", "medium")
            if body.get("agent_name") or body.get("tool") or body.get("skill"):
                todo["metadata"] = {
                    "agent_name": body.get("agent_name"),
                    "tool": body.get("tool"),
                    "skill": body.get("skill")
                }
            d["todos"].append(todo)
            save_data(d)
            self.send_json({"success": True, "todo": todo})

        # /api/todos/toggle
        elif self.path == '/api/todos/toggle':
            d = load_data()
            tid = body.get("id")
            for t in d["todos"]:
                if t["id"] == tid:
                    t["status"] = "completed" if t.get("status") != "completed" else "pending"
                    save_data(d)
                    self.send_json({"success": True, "todo": t})
                    return
            self.send_json({"success": False, "error": "Todo not found"}, 404)

        # /api/todos/clear
        elif self.path == '/api/todos/clear':
            d = load_data()
            before = len(d["todos"])
            d["todos"] = [t for t in d["todos"] if t.get("status") != "completed"]
            save_data(d)
            self.send_json({"success": True, "cleared": before - len(d["todos"])})

        # /api/notes/add
        elif self.path == '/api/notes/add':
            d = load_data()
            note = {
                "id": make_activity_id(),
                "timestamp": datetime.now().isoformat(),
                "category": body.get("category", "context"),
                "content": (body.get("content", ""))[:500],
                "importance": body.get("importance", "normal")
            }
            d["notes"].append(note)
            save_data(d)
            self.send_json({"success": True, "note": note})

        # /api/notes/clear
        elif self.path == '/api/notes/clear':
            d = load_data()
            cleared = len(d["notes"])
            d["notes"] = []
            save_data(d)
            self.send_json({"success": True, "cleared": cleared})

        # /api/shell/add
        elif self.path == '/api/shell/add':
            d = load_data()
            entry = {
                "id": make_activity_id(),
                "command": (body.get("command", ""))[:500],
                "timestamp": datetime.now().isoformat(),
                "status": body.get("status", "completed"),
                "output_preview": (body.get("output_preview", ""))[:200]
            }
            if body.get("agent_name") or body.get("tool"):
                entry["metadata"] = {"agent_name": body.get("agent_name"), "tool": body.get("tool")}
            if body.get("metadata"):
                entry["metadata"] = body["metadata"]
            d["shell_history"].append(entry)
            if len(d["shell_history"]) > 200:
                d["shell_history"] = d["shell_history"][-200:]
            save_data(d)
            self.send_json({"success": True, "entry": entry})

        # /api/shell/clear
        elif self.path == '/api/shell/clear':
            d = load_data()
            cleared = len(d["shell_history"])
            d["shell_history"] = []
            save_data(d)
            self.send_json({"success": True, "cleared": cleared})

        # /api/session/refresh
        elif self.path == '/api/session/refresh':
            d = load_data()
            d["session_start"] = time.time()
            save_data(d)
            self.send_json({"success": True, "session": get_session_info()})

        # /api/agents/register — 1.0.4
        elif self.path == '/api/agents/register':
            d = load_data()
            agent_name = body.get("agent_name", "Unknown")
            capabilities = body.get("capabilities", [])
            model_name = body.get("model_name")
            endpoint = body.get("endpoint")
            skills = body.get("skills", [])
            
            now = datetime.now().isoformat()
            
            if agent_name in d.get("agents", {}):
                # Update existing
                d["agents"][agent_name].update({
                    "capabilities": capabilities,
                    "model_name": model_name,
                    "endpoint": endpoint,
                    "last_seen": now,
                    "status": "online"
                })
            else:
                # Register new
                d.setdefault("agents", {})[agent_name] = {
                    "name": agent_name,
                    "capabilities": capabilities,
                    "model_name": model_name,
                    "endpoint": endpoint,
                    "registered_at": now,
                    "last_seen": now,
                    "status": "online",
                    "tokens_used": 0,
                    "skills": skills
                }
            
            # Update agent_skills
            if skills:
                d.setdefault("agent_skills", {})[agent_name] = skills
            
            # Update last_agent
            d["last_agent"] = agent_name
            if model_name:
                d["last_model"] = model_name
            
            save_data(d)
            self.send_json({
                "success": True,
                "agent": d["agents"][agent_name],
                "message": f"Agent '{agent_name}' registered"
            })

        # /api/agents/unregister — 1.0.4
        elif self.path == '/api/agents/unregister':
            d = load_data()
            agent_name = body.get("agent_name")
            
            if agent_name in d.get("agents", {}):
                del d["agents"][agent_name]
                if agent_name in d.get("agent_skills", {}):
                    del d["agent_skills"][agent_name]
                save_data(d)
                self.send_json({
                    "success": True,
                    "message": f"Agent '{agent_name}' unregistered"
                })
            else:
                self.send_json({
                    "success": False,
                    "error": f"Agent '{agent_name}' not found"
                }, 404)

        # /api/a2a/send — 1.0.4
        elif self.path == '/api/a2a/send':
            d = load_data()
            
            from_agent = body.get("from_agent", "Unknown")
            to_agent = body.get("to_agent")
            msg_type = body.get("type", "notification")
            action = body.get("action")
            payload = body.get("payload", {})
            priority = body.get("priority", "normal")
            ttl = body.get("ttl", 3600)
            reply_to = body.get("reply_to")
            
            if not to_agent:
                self.send_json({"success": False, "error": "'to_agent' is required"}, 400)
                return
            
            # Create message
            msg = create_a2a_message(
                from_agent=from_agent,
                to_agent=to_agent,
                msg_type=msg_type,
                action=action,
                payload=payload,
                priority=priority,
                ttl=ttl,
                reply_to=reply_to
            )
            
            # Add to queue
            d.setdefault("a2a_messages", []).insert(0, msg)
            
            # Update contexts mapping (auto-create per spec §3.8)
            context_id = body.get("contextId") or make_context_id()
            contexts = d.setdefault("contexts", {})
            if context_id not in contexts:
                contexts[context_id] = {
                    "contextId": context_id,
                    "created": time.time(),
                    "last_activity": time.time(),
                    "agents": list({from_agent, to_agent}),
                    "tasks": [msg["id"]]
                }
            else:
                ctx = contexts[context_id]
                ctx["last_activity"] = time.time()
                for agent_name in (from_agent, to_agent):
                    if agent_name and agent_name not in ctx["agents"]:
                        ctx["agents"].append(agent_name)
                if msg["id"] not in ctx["tasks"]:
                    ctx["tasks"].append(msg["id"])
            
            # Limit queue size
            if len(d["a2a_messages"]) > 500:
                d["a2a_messages"] = d["a2a_messages"][:500]
            
            # Create activity for A2A
            activity = {
                "id": msg["id"],
                "action": "A2A",
                "target": f"{from_agent} → {to_agent}",
                "details": f"{msg_type}: {action or 'N/A'}",
                "status": "completed",
                "started": msg["created_at"],
                "completed": msg["created_at"],
                "tokens_in": 0,
                "tokens_out": 0,
                "metadata": {
                    "from_agent": from_agent,
                    "to_agent": to_agent,
                    "msg_type": msg_type
                }
            }
            d["history"].insert(0, activity)
            if len(d["history"]) > 100:
                d["history"] = d["history"][:100]
            
            save_data(d)
            
            # Get A2A hints for recipient
            a2a_hints = get_a2a_hints(d, to_agent)
            
            self.send_json({
                "success": True,
                "message_id": msg["id"],
                "hints": a2a_hints
            })

        else:
            self.send_json({"success": False, "error": "Not found"}, 404)

    # ============================================================
    # JSON-RPC 2.0 Handler (1.0.4)
    # ============================================================
    def _handle_jsonrpc(self, body):
        """Handle JSON-RPC 2.0 requests."""
        req_id = body.get("id")
        method = body.get("method", "")
        params = body.get("params", {})
        
        def send_result(result):
            self.send_json({"jsonrpc": "2.0", "result": result, "id": req_id})
        
        def send_error(code, message):
            self.send_json({"jsonrpc": "2.0", "error": {"code": code, "message": message}, "id": req_id})
        
        d = load_data()
        
        # A2A Protocol Methods
        if method == "SendMessage":
            to_agent = params.get("to_agent")
            if not to_agent:
                return send_error(JSONRPC_INVALID_PARAMS, "'to_agent' is required")
            
            from_agent = params.get("from_agent", "Unknown")
            context_id = params.get("contextId") or make_context_id()
            
            msg = create_a2a_message(
                from_agent=from_agent,
                to_agent=to_agent,
                msg_type=params.get("type", "request"),
                action=params.get("action"),
                payload=params.get("payload", {}),
                priority=params.get("priority", "normal"),
                ttl=params.get("ttl", 3600),
                reply_to=params.get("reply_to")
            )
            
            d.setdefault("a2a_messages", []).insert(0, msg)
            
            # Update contexts mapping (auto-create per spec §3.8)
            contexts = d.setdefault("contexts", {})
            if context_id not in contexts:
                contexts[context_id] = {
                    "contextId": context_id,
                    "created": time.time(),
                    "last_activity": time.time(),
                    "agents": list({from_agent, to_agent}),
                    "tasks": [msg["id"]]
                }
            else:
                ctx = contexts[context_id]
                ctx["last_activity"] = time.time()
                for agent_name in (from_agent, to_agent):
                    if agent_name and agent_name not in ctx["agents"]:
                        ctx["agents"].append(agent_name)
                if msg["id"] not in ctx["tasks"]:
                    ctx["tasks"].append(msg["id"])
            
            save_data(d)
            
            # Return A2A Task format
            send_result({
                "id": msg["id"],
                "contextId": params.get("contextId"),
                "status": {"state": "COMPLETED", "timestamp": msg["created_at"]},
                "history": [],
                "artifacts": [],
                "metadata": {
                    "action": "A2A",
                    "target": f"{msg['from_agent']} → {msg['to_agent']}",
                    "tokens_in": 0,
                    "tokens_out": 0
                }
            })
        
        elif method == "GetTask":
            task_id = params.get("id")
            if not task_id:
                return send_error(JSONRPC_INVALID_PARAMS, "'id' is required")
            
            for a in d.get("running", []) + d.get("history", []):
                if a["id"] == task_id:
                    state = "RUNNING" if a["status"] == "running" else \
                           "COMPLETED" if a["status"] == "completed" else \
                           "FAILED" if a["status"] == "error" else "CANCELED"
                    return send_result({
                        "id": a["id"],
                        "status": {"state": state, "timestamp": a.get("started", "")},
                        "metadata": {
                            "action": a.get("action"),
                            "target": a.get("target"),
                            "tokens_in": a.get("tokens_in", 0),
                            "tokens_out": a.get("tokens_out", 0),
                            "duration_ms": a.get("duration_ms")
                        }
                    })
            send_error(JSONRPC_TASK_NOT_FOUND, "Task not found")
        
        elif method == "CancelTask":
            task_id = params.get("id")
            if not task_id:
                return send_error(JSONRPC_INVALID_PARAMS, "'id' is required")
            
            for a in d.get("running", []):
                if a["id"] == task_id:
                    a["status"] = "cancelled"
                    a["completed"] = datetime.now().isoformat()
                    d["history"].insert(0, a)
                    d["running"] = [x for x in d["running"] if x["id"] != task_id]
                    save_data(d)
                    return send_result({
                        "id": task_id,
                        "status": {"state": "CANCELED", "timestamp": a["completed"]}
                    })
            send_error(JSONRPC_TASK_NOT_RUNNING, "Task not running")
        
        elif method == "GetAgents":
            agents = d.get("agents", {})
            agent_list = []
            for name in agents:
                agent = get_agent_status(d, name)
                if agent:
                    agent_list.append(agent)
            send_result({"agents": agent_list, "count": len(agent_list), "primary_agent": d.get("primary_agent")})
        
        elif method == "RegisterAgent":
            agent_name = params.get("agent_name", "Unknown")
            now = datetime.now().isoformat()
            
            if agent_name in d.get("agents", {}):
                d["agents"][agent_name].update({
                    "capabilities": params.get("capabilities", []),
                    "model_name": params.get("model_name"),
                    "endpoint": params.get("endpoint"),
                    "last_seen": now,
                    "status": "online"
                })
            else:
                d.setdefault("agents", {})[agent_name] = {
                    "name": agent_name,
                    "capabilities": params.get("capabilities", []),
                    "model_name": params.get("model_name"),
                    "endpoint": params.get("endpoint"),
                    "registered_at": now,
                    "last_seen": now,
                    "status": "online",
                    "tokens_used": 0,
                    "skills": params.get("skills", [])
                }
            
            d["last_agent"] = agent_name
            if params.get("model_name"):
                d["last_model"] = params["model_name"]
            
            save_data(d)
            send_result({"agent": d["agents"][agent_name], "message": f"Agent '{agent_name}' registered"})
        
        # ACP-native Methods
        elif method == "activity/start":
            if d["stop_flag"]:
                return send_error(JSONRPC_TASK_NOT_FOUND, "Stop requested")
            
            action = params.get("action", "UNKNOWN")
            target = params.get("target", "")
            metadata = params.get("metadata", {})
            
            started_ts = time.time()
            started = datetime.now().isoformat()
            activity_id = make_activity_id()
            input_tokens = estimate_tokens([action, target, params.get("details", "")], params.get("content_size", 0))
            
            activity = {
                "id": activity_id,
                "action": action, "target": target,
                "details": params.get("details", ""),
                "status": "running", "started": started, "started_ts": started_ts,
                "tokens_in": input_tokens,
                "priority": params.get("priority", "medium"),
                "metadata": metadata
            }
            
            d["running"].append(activity)
            agent_name = metadata.get("agent_name", "Unknown")
            if not d.get("primary_agent"):
                d["primary_agent"] = agent_name
            if agent_name not in d.get("agent_tokens", {}):
                d["agent_tokens"][agent_name] = 0
            d["agent_tokens"][agent_name] += input_tokens
            d["tokens"] = d.get("tokens", 0) + input_tokens
            
            save_data(d)
            send_result({
                "activity_id": activity_id,
                "hints": get_hints(d, target, agent_name)
            })
        
        elif method == "activity/complete":
            activity_id = params.get("activity_id")
            if not activity_id:
                return send_error(JSONRPC_INVALID_PARAMS, "'activity_id' is required")
            
            for i, a in enumerate(d.get("running", [])):
                if a["id"] == activity_id:
                    a["status"] = "error" if params.get("error") else "completed"
                    a["completed"] = datetime.now().isoformat()
                    a["result"] = (params.get("result") or "")[:500]
                    a["error"] = str(params.get("error", ""))[:200] if params.get("error") else None
                    
                    output_tokens = estimate_tokens([a.get("result", ""), str(params.get("error", ""))])
                    a["tokens_out"] = output_tokens
                    
                    try:
                        started = datetime.fromisoformat(a["started"])
                        completed = datetime.fromisoformat(a["completed"])
                        a["duration_ms"] = int((completed - started).total_seconds() * 1000)
                    except:
                        pass
                    
                    d["history"].insert(0, d["running"].pop(i))
                    
                    m = a.get("metadata", {})
                    agent_name = m.get("agent_name", "Unknown")
                    if agent_name not in d.get("agent_tokens", {}):
                        d["agent_tokens"][agent_name] = 0
                    d["agent_tokens"][agent_name] += output_tokens
                    if agent_name == d.get("primary_agent"):
                        d["tokens"] = d.get("tokens", 0) + output_tokens
                    
                    save_data(d)
                    return send_result({"activity": a})
            
            send_error(JSONRPC_TASK_NOT_FOUND, "Activity not found")
        
        elif method == "todos/get":
            send_result({"todos": d.get("todos", [])})
        
        elif method == "todos/update":
            todos = params.get("todos", [])
            for t in todos:
                if "id" not in t:
                    t["id"] = make_activity_id()
                t.setdefault("created", datetime.now().isoformat())
                t.setdefault("status", "pending")
                t.setdefault("priority", "medium")
            d["todos"] = todos
            save_data(d)
            send_result({"success": True})
        
        elif method == "status/get":
            tok = get_token_summary(d)
            send_result({
                "success": True,
                "stop_flag": d["stop_flag"],
                "session_tokens": tok["session_tokens"],
                "context_window": CONTEXT_WINDOW,
                "tokens_remaining": tok["tokens_remaining"],
                "tokens_percent": tok["tokens_percent"],
                "primary_agent": d.get("primary_agent"),
                "agent_tokens": d.get("agent_tokens", {}),
                "session": get_session_info()
            })
        
        elif method == "nudge/set":
            d["nudge"] = {
                "message": params.get("message", ""),
                "priority": params.get("priority", "normal"),
                "requires_ack": params.get("requires_ack", False),
                "from": "system",
                "timestamp": datetime.now().isoformat()
            }
            save_data(d)
            send_result({"success": True, "message": "Nudge set"})
        
        elif method == "stop/set":
            d["stop_flag"] = True
            d["stop_reason"] = params.get("reason", "User requested")
            save_data(d)
            send_result({"success": True, "message": "Stop flag set"})
        
        elif method == "session/reset":
            stats = {
                "history_cleared": len(d.get("history", [])),
                "agents_cleared": len(d.get("agents", {})),
                "a2a_cleared": len(d.get("a2a_messages", [])),
                "tokens_reset": d.get("tokens", 0)
            }
            d.update(reset_state())
            save_data(d)
            send_result({"success": True, "message": "Session reset", "stats": stats})
        
        else:
            send_error(JSONRPC_METHOD_NOT_FOUND, f"Method not found: {method}")


# --- MAIN ---
if __name__ == "__main__":
    print(f"🤖 ACP Minimal v1.0.6 starting on port {PORT}")
    print(f"   Auth: {AUTH_USER} / {AUTH_PASS}")
    print(f"   Features: Activity Monitor + File Manager + A2A Messaging + JSON-RPC")
    server = HTTPServer(('0.0.0.0', PORT), ACPMinimalHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Server stopped")