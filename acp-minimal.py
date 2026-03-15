#!/usr/bin/env python3
"""
ACP Minimal v1.0.3 - Full Spec Compliance
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
"""

import json, os, base64, time, signal, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

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
        "shell_log": [],
        "errors": []
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

def get_hints(data, target):
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
        "shell_log": [],
        "errors": []
    }

# --- UI ---
_UI = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>ACP Minimal v1.0.3</title>
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
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <div>
            <h2 style="margin:0;color:var(--primary)">&#x1F916; ACP Minimal <small style="color:#6e7681;font-size:0.8rem">v1.0.3</small></h2>
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

        // Running
        const rs = document.getElementById('running-section');
        rs.innerHTML = d.running&&d.running.length ? '<div class="panel"><div class="panel-header"><span class="panel-title">&#x1F504; Running ('+d.running.length+')</span></div><div class="panel-body">'
            + d.running.map(a => {
                const m=a.metadata||{};
                return '<div class="activity-item"><div class="activity-header"><span class="status-pill status-running">'+a.status+'</span><strong>'+esc(a.action)+'</strong><span class="tag">#'+a.id+'</span></div>'
                    +'<div class="activity-body"><div class="activity-target">'+esc(a.target||'N/A')+'</div><div>'+esc(a.details||'')+'</div></div>'
                    +'<div class="panel-footer"><span>&#x1F464; '+esc(m.agent_name||'---')+(m.model_name?' &middot; '+esc(m.model_name):'')+'</span><span>&#x1F552; '+esc(a.started||'---')+'</span></div></div>';
            }).join('') + '</div></div>' : '';

        // History
        const hs = document.getElementById('history-section');
        hs.innerHTML = d.history&&d.history.length ? '<div class="panel"><div class="panel-header"><span class="panel-title">&#x1F4DC; History ('+d.history.length+')</span></div><div class="panel-body">'
            + d.history.slice(0,25).map(a => {
                const m=a.metadata||{};
                const sc = a.status==='error'||a.status==='cancelled'?'error':'completed';
                return '<div class="activity-item"><div class="activity-header"><span class="status-pill status-'+sc+'">'+a.status+'</span><strong>'+esc(a.action)+'</strong><span class="tag">#'+a.id+'</span></div>'
                    +'<div class="activity-body"><div class="activity-target">'+esc(a.target||'N/A')+'</div><div>'+esc(a.details||'')+'</div>'+(a.result?'<pre>'+esc(a.result)+'</pre>':'')+'</div>'
                    +'<div class="panel-footer"><span>&#x1F464; '+esc(m.agent_name||'---')+(m.model_name?' &middot; '+esc(m.model_name):'')+'</span><span>&#x1F552; '+esc(a.started||'---')+'</span><span>&#x23F1;&#xFE0F; '+dur(a.duration_ms)+'</span></div></div>';
            }).join('') + '</div></div>'
            : '<div style="text-align:center;padding:40px;color:#6e7681">No activity logged yet.</div>';

        // Todos
        const tp = document.getElementById('todos-panel');
        tp.innerHTML = d.todos&&d.todos.length ? '<div class="panel"><div class="panel-header"><span class="panel-title">&#x1F4CB; Todos ('+d.todos.length+')</span></div><div class="panel-body" style="padding:0">'
            + d.todos.map(t => '<div class="todo-item"><input type="checkbox" class="todo-checkbox" data-id="'+t.id+'" '+(t.status==='completed'?'checked':'')+' onchange="toggleTodo(event.target.dataset.id)"><span class="todo-content" style="'+(t.status==='completed'?'text-decoration:line-through;opacity:0.6':'')+'">'+esc(t.content)+'</span><span class="todo-priority priority-'+(t.priority||'medium')+'">'+(t.priority||'med')+'</span></div>').join('')
            + '</div></div>' : '';

        // Agents — primary_agent gets orange star badge
        const ap = document.getElementById('agents-panel');
        ap.innerHTML = d.agent_tokens&&Object.keys(d.agent_tokens).length ? '<div class="panel"><div class="panel-header"><span class="panel-title">&#x1F916; Agents</span></div><div class="panel-body">'
            + Object.entries(d.agent_tokens).map(([n,tok]) => '<div style="display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid var(--border)"><span class="agent-badge '+(n===d.primary_agent?'agent-primary':'agent-other')+'">'+esc(n)+(n===d.primary_agent?' &#x2605;':'')+'</span><span class="tag">'+tok+' tok</span></div>').join('')
            + '</div></div>' : '';

        // Shell
        const sp = document.getElementById('shell-panel');
        sp.innerHTML = d.shell_log&&d.shell_log.length ? '<div class="panel"><div class="panel-header"><span class="panel-title">&#x1F4BB; Shell ('+d.shell_log.length+')</span></div><div class="panel-body" style="padding:0">'
            + d.shell_log.slice(0,10).map(s => '<div class="shell-item"><span class="shell-cmd" title="'+esc(s.command||'')+'">'+esc(s.command||'---')+'</span><span class="shell-status '+(s.status==='error'?'status-error':'status-completed')+'">'+s.status+'</span></div>').join('')
            + '</div></div>' : '';

        // Hints
        const hp = document.getElementById('hints-panel');
        hp.innerHTML = d.hints&&(d.hints.loop_detected||d.hints.active_todos>0) ? '<div class="panel"><div class="panel-header"><span class="panel-title">&#x1F4A1; Hints</span></div><div class="panel-body">'
            + (d.hints.loop_detected?'<div style="color:var(--warning);margin-bottom:8px">&#x26A0;&#xFE0F; Loop detected: '+d.hints.loop_count+' repetitions</div>':'')
            + (d.hints.suggestion?'<div style="color:var(--info)">'+esc(d.hints.suggestion)+'</div>':'')
            + (d.hints.active_todos>0?'<div class="tag">&#x1F4CC; '+d.hints.active_todos+' active todos</div>':'')
            + '</div></div>' : '';
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
                "errors": d.get("errors", [])[-5:]
            })

        # /api/all — combined convenience endpoint, spec §4.3
        elif self.path == '/api/all':
            d = load_data()
            tok = get_token_summary(d)
            orphans = check_orphans(d)
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
                "shell_log": d.get("shell_log", [])[-10:],
                "errors": d.get("errors", []),
                "orphan_warning": {"count": len(orphans), "tasks": orphans} if orphans else None,
                "current_files": current_files,
                "base_dir": os.path.abspath(base_dir)
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
            self.send_json({"success": True, "shell": d.get("shell_log", [])})

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
                    "summary": content,
                    "note": "Share this file with new AI sessions for context recovery"
                })
            except Exception as e:
                self.send_json({"success": False, "error": str(e)}, 500)

        # /api/stats/duration — spec §4.8
        elif self.path == '/api/stats/duration':
            d = load_data()
            self.send_json({
                "success": True,
                "stats": calc_duration_stats(d),
                "slow_threshold_seconds": 30.0
            })

        # /api/session — spec §4.10
        elif self.path == '/api/session':
            self.send_json({"success": True, "session": get_session_info()})

        # /api/csrf-token — spec §4.10 (CSRF disabled by default)
        elif self.path == '/api/csrf-token':
            self.send_json({
                "success": True,
                "csrf_enabled": False,
                "csrf_token": None,
                "expires_in": None,
                "message": "CSRF protection is disabled. Token not required."
            })

        # /api/nudge GET — spec §4.11
        elif self.path == '/api/nudge':
            d = load_data()
            self.send_json({
                "success": True,
                "nudge": d.get("nudge"),
                "has_pending": d.get("nudge") is not None
            })

        # /api/files/list
        elif self.path.startswith('/api/files/list'):
            qs = self.path.split('?', 1)[1] if '?' in self.path else ''
            rel = qs.replace('path=', '') if 'path=' in qs else self.headers.get('X-Path', '')
            rel = rel.strip('/')
            base = os.environ.get("ACP_BASE_DIR", ".")
            full = os.path.join(base, rel) if rel else base
            if not os.path.abspath(full).startswith(os.path.abspath(base)):
                return self.send_json({"success": False, "error": "Access denied"}, 403)
            if not os.path.exists(full):
                return self.send_json({"success": False, "error": "Path not found"}, 404)
            if not os.path.isdir(full):
                return self.send_json({"success": False, "error": "Not a directory"}, 400)
            try:
                items = []
                sort_by = self.headers.get('X-Sort-By', 'name')
                for item in os.listdir(full):
                    ip = os.path.join(full, item)
                    st = os.stat(ip)
                    items.append({
                        "name": item,
                        "is_dir": os.path.isdir(ip),
                        "size": st.st_size if os.path.isfile(ip) else 0,
                        "modified": datetime.fromtimestamp(st.st_mtime).isoformat()
                    })
                items.sort(key=lambda x: x["name"])
                self.send_json({"success": True, "path": rel or "/", "items": items, "base_dir": base})
            except Exception as e:
                self.send_json({"success": False, "error": str(e)}, 500)

        # /api/files/view
        elif self.path.startswith('/api/files/view'):
            qs = self.path.split('?', 1)[1] if '?' in self.path else ''
            rel = qs.replace('path=', '') if 'path=' in qs else self.headers.get('X-Path', '')
            rel = rel.strip('/')
            base = os.environ.get("ACP_BASE_DIR", ".")
            full = os.path.join(base, rel)
            if not os.path.abspath(full).startswith(os.path.abspath(base)):
                return self.send_json({"success": False, "error": "Access denied"}, 403)
            if not os.path.exists(full):
                return self.send_json({"success": False, "error": "File not found"}, 404)
            if not os.path.isfile(full):
                return self.send_json({"success": False, "error": "Not a file"}, 400)
            if os.path.getsize(full) > 100000:
                return self.send_json({"success": False, "error": "File too large for viewing (max 100KB)"}, 400)
            try:
                with open(full, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                d = load_data()
                tokens = len(content) // 4
                self.send_json({
                    "success": True,
                    "path": rel,
                    "content": content,
                    "lines": content.count('\n') + 1,
                    "size": len(content),
                    "tokens": tokens,
                    "session_tokens": d["tokens"] + tokens
                })
            except Exception as e:
                self.send_json({"success": False, "error": str(e)}, 500)

        # /api/files/download
        elif self.path.startswith('/api/files/download'):
            qs = self.path.split('?', 1)[1] if '?' in self.path else ''
            rel = qs.replace('path=', '') if 'path=' in qs else ''
            rel = rel.strip('/')
            base = os.environ.get("ACP_BASE_DIR", ".")
            full = os.path.join(base, rel)
            if not os.path.abspath(full).startswith(os.path.abspath(base)):
                self.send_response(403); self.end_headers(); return
            if not os.path.exists(full) or not os.path.isfile(full):
                self.send_response(404); self.end_headers(); return
            try:
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Disposition', f'attachment; filename="{os.path.basename(full)}"')
                self.end_headers()
                with open(full, 'rb') as f:
                    self.wfile.write(f.read())
            except:
                self.send_response(500); self.end_headers()

        # /api/files/stats
        elif self.path == '/api/files/stats':
            base = os.environ.get("ACP_BASE_DIR", ".")
            try:
                tf = td = ts = 0
                for root, dirs, files in os.walk(base):
                    td += len(dirs)
                    tf += len(files)
                    for fn in files:
                        try: ts += os.path.getsize(os.path.join(root, fn))
                        except: pass
                self.send_json({
                    "success": True,
                    "base_dir": base,
                    "total_files": tf,
                    "total_directories": td,
                    "total_size_bytes": ts,
                    "total_size_mb": round(ts / (1024 * 1024), 2)
                })
            except Exception as e:
                self.send_json({"success": False, "error": str(e)}, 500)

        else:
            self.send_json({"success": False, "error": f"Unknown endpoint: {self.path}"}, 404)

    # ============================================================
    # POST
    # ============================================================
    def do_POST(self):
        if not self.check_auth():
            return
        length = int(self.headers.get('Content-Length', 0))
        req = json.loads(self.rfile.read(length).decode('utf-8')) if length else {}
        data = load_data()
        now = time.time()

        # /api/stop — spec §4.3
        if self.path == '/api/stop':
            data["stop_flag"] = True
            data["stop_reason"] = req.get('reason', 'User requested')
            for a in data["running"]:
                a["status"] = "cancelled"
                data["history"].insert(0, a)
            data["running"] = []
            save_data(data)
            return self.send_json({
                "success": True,
                "stop_flag": True,
                "stop_reason": data["stop_reason"]
            })

        # /api/resume — spec §4.3
        elif self.path == '/api/resume':
            data["stop_flag"] = False
            data["stop_reason"] = None
            save_data(data)
            return self.send_json({"success": True, "stop_flag": False})

        # /api/nudge POST — spec §4.11
        elif self.path == '/api/nudge':
            if not req.get('message'):
                return self.send_json({"success": False, "error": "message is required"}, 400)
            nudge = {
                "message": req['message'],
                "timestamp": datetime.now().isoformat(),
                "priority": req.get('priority', 'normal'),
                "requires_ack": req.get('requires_ack', True),
                "from": "human",
                "acknowledged": False
            }
            data["nudge"] = nudge
            save_data(data)
            return self.send_json({
                "success": True,
                "nudge": nudge,
                "message": "Nudge queued for next action"
            })

        # /api/nudge/ack — spec §4.11
        elif self.path == '/api/nudge/ack':
            data["nudge"] = None
            save_data(data)
            return self.send_json({"success": True, "message": "Nudge acknowledged"})

        # /api/action — spec §4.3 combined endpoint
        elif self.path == '/api/action':
            if data["stop_flag"]:
                return self.send_json({
                    "success": False,
                    "error": "Stop requested",
                    "stop_flag": True,
                    "stop_reason": data.get("stop_reason")
                }, 403)

            completed_activity = None
            target = req.get('target', '')

            # 1. Complete previous activity
            if req.get('complete_id'):
                for i, a in enumerate(data["running"]):
                    if a["id"] == req["complete_id"]:
                        duration_ms = int((now - a.get("started_ts", now)) * 1000)
                        a.update({
                            "status": "completed",
                            "result": req.get('result', ''),
                            "duration_ms": duration_ms
                        })
                        if req.get('error'):
                            a["status"] = "error"
                            a["error"] = req['error']
                        if req.get('complete_content_size'):
                            data["tokens"] += int(req['complete_content_size'] / 3.5)
                        if req.get('complete_metadata'):
                            a.setdefault("metadata", {}).update(req['complete_metadata'])
                        completed_activity = dict(a)
                        data["history"].insert(0, a)
                        data["running"].pop(i)
                        break

            # 2. Hints for new target
            hints = get_hints(data, target) if target else None

            # 3. Identity & token tracking
            meta = req.get('metadata', {})
            agent_name = meta.get('agent_name')
            action_tokens = max(1, estimate_tokens(
                [req.get('action'), target], req.get('content_size', 0)
            ))

            if agent_name:
                if not data.get("primary_agent"):
                    data["primary_agent"] = agent_name
                    data["startup_tokens"] = data["tokens"]
                data["last_agent"] = agent_name
                data["last_model"] = meta.get('model_name', data.get("last_model", "---"))
                # session_tokens = primary agent only
                if agent_name == data["primary_agent"]:
                    data["tokens"] += action_tokens
                data.setdefault("agent_tokens", {})
                data["agent_tokens"][agent_name] = data["agent_tokens"].get(agent_name, 0) + action_tokens
            else:
                meta['agent_name'] = data.get("last_agent", "Unknown")
                meta['model_name'] = data.get("last_model", "---")
                data["tokens"] += action_tokens

            # 4. Start new activity
            aid = make_activity_id()
            data["running"].append({
                "id": aid,
                "action": req.get('action'),
                "target": target,
                "details": req.get('details', ''),
                "metadata": meta,
                "status": "running",
                "started": datetime.now().isoformat(),
                "started_ts": now,
                "priority": req.get('priority', 'medium')
            })

            orphans = check_orphans(data)
            tok = get_token_summary(data)
            save_data(data)
            return self.send_json({
                "success": True,
                "activity_id": aid,
                "completed": completed_activity,
                "stop_flag": data["stop_flag"],
                "session_tokens": tok["session_tokens"],
                "context_window": CONTEXT_WINDOW,
                "tokens_remaining": tok["tokens_remaining"],
                "tokens_percent": tok["tokens_percent"],
                "overflow_warning": tok["overflow_warning"],
                "running_count": len(data["running"]),
                "session": get_session_info(),
                "hints": hints,
                "nudge": data["nudge"],
                "orphan_warning": {"count": len(orphans), "tasks": orphans} if orphans else None
            })

        # /api/start — spec §4.3
        elif self.path == '/api/start':
            if data["stop_flag"]:
                return self.send_json({"success": False, "error": "Stop requested", "stop_flag": True}, 403)
            target = req.get('target', '')
            meta = req.get('metadata', {})
            agent_name = meta.get('agent_name')
            action_tokens = max(1, estimate_tokens(
                [req.get('action'), target], req.get('content_size', 0)
            ))
            if agent_name:
                if not data.get("primary_agent"):
                    data["primary_agent"] = agent_name
                data["last_agent"] = agent_name
                data["last_model"] = meta.get('model_name', data.get("last_model", "---"))
                if agent_name == data["primary_agent"]:
                    data["tokens"] += action_tokens
                data.setdefault("agent_tokens", {})
                data["agent_tokens"][agent_name] = data["agent_tokens"].get(agent_name, 0) + action_tokens
            else:
                meta['agent_name'] = data.get("last_agent", "Unknown")
                data["tokens"] += action_tokens
            aid = make_activity_id()
            data["running"].append({
                "id": aid,
                "action": req.get('action'),
                "target": target,
                "details": req.get('details', ''),
                "metadata": meta,
                "status": "running",
                "started": datetime.now().isoformat(),
                "started_ts": now,
                "priority": req.get('priority', 'medium')
            })
            hints = get_hints(data, target) if target else None
            orphans = check_orphans(data)
            save_data(data)
            return self.send_json({
                "success": True,
                "activity_id": aid,
                "nudge": data["nudge"],
                "hints": hints,
                "orphan_warning": {"count": len(orphans), "tasks": orphans} if orphans else None
            })

        # /api/complete — spec §4.3
        elif self.path == '/api/complete':
            aid = req.get('activity_id')
            for i, a in enumerate(data["running"]):
                if a["id"] == aid:
                    duration_ms = int((now - a.get("started_ts", now)) * 1000)
                    a.update({"status": "completed", "result": req.get('result', ''), "duration_ms": duration_ms})
                    if req.get('error'):
                        a["status"] = "error"
                        a["error"] = req['error']
                    if req.get('content_size'):
                        data["tokens"] += int(req['content_size'] / 3.5)
                    if req.get('metadata'):
                        a.setdefault("metadata", {}).update(req['metadata'])
                    data["history"].insert(0, a)
                    data["running"].pop(i)
                    save_data(data)
                    return self.send_json({
                        "success": True,
                        "activity_id": aid,
                        "status": a["status"],
                        "duration_ms": duration_ms
                    })
            data.setdefault("errors", []).append({
                "timestamp": datetime.now().isoformat(),
                "message": f"Activity not found: {aid}",
                "type": "complete_error"
            })
            save_data(data)
            return self.send_json({"success": False, "error": "Activity not found"}, 404)

        # /api/activity/batch — spec §4.9
        elif self.path == '/api/activity/batch':
            operations = req.get('operations', [])
            if len(operations) > 50:
                return self.send_json({"success": False, "error": "Maximum 50 operations per batch"}, 400)
            results = []
            all_ok = True
            for op in operations:
                op_type = op.get('type')
                try:
                    if op_type == 'start':
                        target = op.get('target', '')
                        at = max(1, estimate_tokens([op.get('action'), target], op.get('content_size', 0)))
                        data["tokens"] += at
                        meta = op.get('metadata', {})
                        an = meta.get('agent_name')
                        if an:
                            data.setdefault("agent_tokens", {})
                            data["agent_tokens"][an] = data["agent_tokens"].get(an, 0) + at
                        aid = make_activity_id()
                        data["running"].append({
                            "id": aid,
                            "action": op.get('action'),
                            "target": target,
                            "details": op.get('details', ''),
                            "metadata": meta,
                            "status": "running",
                            "started": datetime.now().isoformat(),
                            "started_ts": now,
                            "priority": op.get('priority', 'medium')
                        })
                        results.append({"success": True, "operation": "start", "activity_id": aid})
                    elif op_type == 'complete':
                        aid = op.get('activity_id')
                        found = False
                        for i, a in enumerate(data["running"]):
                            if a["id"] == aid:
                                dur = int((now - a.get("started_ts", now)) * 1000)
                                a.update({"status": "completed", "result": op.get('result', ''), "duration_ms": dur})
                                data["history"].insert(0, a)
                                data["running"].pop(i)
                                results.append({"success": True, "operation": "complete", "activity_id": aid})
                                found = True
                                break
                        if not found:
                            results.append({"success": False, "operation": "complete", "activity_id": aid, "error": "Activity not found"})
                            all_ok = False
                    else:
                        results.append({"success": False, "operation": op_type, "error": "Unknown operation type"})
                        all_ok = False
                except Exception as e:
                    results.append({"success": False, "operation": op_type, "error": str(e)})
                    all_ok = False
            tok = get_token_summary(data)
            save_data(data)
            return self.send_json({
                "success": all_ok,
                "results": results,
                "count": len(results),
                "session_tokens": tok["session_tokens"],
                "context_window": CONTEXT_WINDOW,
                "tokens_remaining": tok["tokens_remaining"]
            })

        # /api/todos/add — spec §4.4 (nested {todo: {...}})
        elif self.path == '/api/todos/add':
            # Support spec shape {todo: {...}} and legacy flat shape
            todo_data = req.get('todo', {})
            if not todo_data.get('content') and req.get('content'):
                todo_data = req  # backward compat
            if not todo_data.get('content'):
                return self.send_json({"success": False, "error": "todo.content is required"}, 400)
            data.setdefault("todos", [])
            data["todos"].append({
                "id": todo_data.get('id', make_activity_id()),
                "content": todo_data['content'],
                "status": todo_data.get('status', 'pending'),
                "priority": todo_data.get('priority', 'medium'),
                "created": datetime.now().isoformat(),
                "metadata": {
                    "agent_name": req.get('agent_name') or todo_data.get('agent_name'),
                    "tool": req.get('tool'),
                    "skill": req.get('skill')
                }
            })
            save_data(data)
            return self.send_json({"success": True, "count": len(data["todos"])})

        # /api/todos/update — spec §4.4
        elif self.path == '/api/todos/update':
            data["todos"] = req.get('todos', [])
            save_data(data)
            return self.send_json({"success": True, "count": len(data["todos"])})

        # /api/todos/toggle
        elif self.path == '/api/todos/toggle':
            tid = req.get('id')
            for t in data.get("todos", []):
                if t["id"] == tid:
                    t["status"] = "completed" if t.get("status") != "completed" else "pending"
                    save_data(data)
                    return self.send_json({"success": True, "todo": t})
            return self.send_json({"success": False, "error": "Todo not found"}, 404)

        # /api/todos/clear — spec §4.4
        elif self.path == '/api/todos/clear':
            data["todos"] = [t for t in data.get("todos", []) if t.get('status') != 'completed']
            save_data(data)
            return self.send_json({"success": True, "count": len(data["todos"])})

        # /api/notes/add — spec §4.6 (structured Note object)
        elif self.path == '/api/notes/add':
            if not req.get('content'):
                return self.send_json({"success": False, "error": "content is required"}, 400)
            data.setdefault("notes", [])
            note = {
                "id": make_activity_id(),
                "timestamp": datetime.now().isoformat(),
                "category": req.get('category', 'context'),
                "content": req['content'][:500],
                "importance": req.get('importance', 'normal')
            }
            data["notes"].append(note)
            save_data(data)
            return self.send_json({"success": True, "note": note})

        # /api/notes/clear — spec §4.6
        elif self.path == '/api/notes/clear':
            data["notes"] = []
            save_data(data)
            return self.send_json({"success": True})

        # /api/shell/add — spec §4.5
        elif self.path == '/api/shell/add':
            aid = make_activity_id()
            cmd = req.get('command', '')
            meta = req.get('metadata', {})
            if req.get('agent_name') and not meta.get('agent_name'):
                meta['agent_name'] = req['agent_name']
            if req.get('tool') and not meta.get('tool'):
                meta['tool'] = req['tool']
            entry = {
                "id": aid,
                "command": cmd[:500],
                "status": req.get('status', 'completed'),
                "output_preview": req.get('output_preview', '')[:200],
                "timestamp": datetime.now().isoformat(),
                "metadata": meta
            }
            data.setdefault("shell_log", [])
            data["shell_log"].append(entry)
            data["shell_log"] = data["shell_log"][-50:]
            data["history"].insert(0, {
                "id": aid,
                "action": "BASH",
                "target": cmd,
                "details": req.get('output_preview', '')[:200],
                "status": req.get('status', 'completed'),
                "started": datetime.now().isoformat(),
                "started_ts": now,
                "metadata": meta
            })
            save_data(data)
            return self.send_json({"success": True, "activity_id": aid})

        # /api/shell/clear — spec §4.5
        elif self.path == '/api/shell/clear':
            data["shell_log"] = []
            save_data(data)
            return self.send_json({"success": True})

        # /api/clear_history — spec §4.3
        elif self.path == '/api/clear_history':
            data["history"] = []
            save_data(data)
            return self.send_json({"success": True})

        # /api/reset and /api/reset_session — spec §4.3
        elif self.path in ('/api/reset', '/api/reset_session'):
            save_data(reset_state())
            return self.send_json({"success": True})

        # /api/session/refresh — spec §4.10
        elif self.path == '/api/session/refresh':
            return self.send_json({"success": True, "session": get_session_info()})

        # /api/restart — spec §4.10
        elif self.path == '/api/restart':
            self.send_json({"success": True, "message": "Restarting..."})
            threading.Timer(0.5, lambda: os.execv(__file__, ['python3', __file__])).start()
            return

        # /api/shutdown — spec §4.3 (graceful: export → cancel → nudge → delay → kill)
        elif self.path == '/api/shutdown':
            reason = req.get('reason', 'Session ended by user')
            do_export = req.get('export_summary', True)
            summary_path = None
            if do_export:
                try:
                    summary_path, _ = write_summary_file(data)
                except:
                    pass
            cancelled = len(data["running"])
            for a in data["running"]:
                a["status"] = "cancelled"
                data["history"].insert(0, a)
            data["running"] = []
            data["nudge"] = {
                "message": "SESSION ENDING: The human has ended this session. Wrap up any final thoughts, then acknowledge this message. The server will stop shortly.",
                "priority": "urgent",
                "requires_ack": True,
                "from": "system",
                "type": "shutdown",
                "timestamp": datetime.now().isoformat(),
                "acknowledged": False
            }
            save_data(data)
            self.send_json({
                "success": True,
                "message": "Session ending - agent has been notified",
                "summary_exported": do_export,
                "summary_path": summary_path,
                "cancelled_activities": cancelled,
                "note": "Server will stop in 2 seconds. Agent should acknowledge the shutdown nudge."
            })
            threading.Timer(2.0, lambda: os.kill(os.getpid(), signal.SIGINT)).start()
            return

        else:
            return self.send_json({"success": False, "error": f"Unknown endpoint: {self.path}"}, 404)


if __name__ == "__main__":
    print(f"🤖 ACP Minimal v1.0.3 active on port {PORT}")
    print(f"   Auth: {AUTH_USER} / {AUTH_PASS}")
    print(f"   Context Window: {CONTEXT_WINDOW:,} tokens")
    print(f"   Session Timeout: {SESSION_TIMEOUT}s | Orphan Timeout: {ORPHAN_TIMEOUT}s")
    print(f"   Data File: {DATA_FILE} | Summary File: {SUMMARY_FILE}")
    print(f"   Base Directory: {os.environ.get('ACP_BASE_DIR', '.')}")
    HTTPServer(('0.0.0.0', PORT), ACPMinimalHandler).serve_forever()