#!/usr/bin/env python3
"""
ACP Minimal v1.0.3 - Full Spec Compliance with Enhanced Visibility
Endpoints: whoami, status, action, complete, nudge, nudge/ack, stop, reset, shutdown
           running, activity/{id}, stats/duration, todos, notes, shell, summary
           files/list, files/view, files/download, files/stats (read-only)
"""

import json, os, base64, time, signal, re
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

# --- CONFIG ---
PORT = int(os.environ.get("ACP_PORT", "8766"))
AUTH_USER = os.environ.get("ACP_USER", "admin")
AUTH_PASS = os.environ.get("ACP_PASS", "secret")
DATA_FILE = os.environ.get("ACP_DATA_FILE", "acp_data.json")
CONTEXT_WINDOW = int(os.environ.get("ACP_CONTEXT_WINDOW", "200000"))
SESSION_TIMEOUT = int(os.environ.get("ACP_SESSION_TIMEOUT", "86400"))
ORPHAN_TIMEOUT = int(os.environ.get("ACP_ORPHAN_TIMEOUT", "300"))  # 5 minutes

SESSION_START = time.time()

def load_data():
    defaults = {
        "running":[], "history":[], "stop_flag":False, "tokens":0, 
        "files_read":[], "nudge":None, "primary_agent": None, "last_agent": "Unknown", "last_model": "Unknown",
        "todos":[], "notes":"", "summary":"Session Reset.",
        "session_start": SESSION_START, "agent_tokens": {}, "activity_durations": {},
        "shell_log": [], "errors": []
    }
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                d = json.load(f)
                return {**defaults, **d}
        except: pass
    return defaults

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=2)

def estimate_tokens(text_list, content_size=0):
    return int((len("".join(map(str, text_list))) + content_size) / 3.5)

def get_session_info():
    now = time.time()
    elapsed = now - SESSION_START
    return {
        "session_start": SESSION_START,
        "last_activity": now,
        "elapsed_seconds": int(elapsed),
        "idle_seconds": 0,  # Would need tracking
        "timeout_seconds": SESSION_TIMEOUT,
        "remaining_seconds": max(0, SESSION_TIMEOUT - int(elapsed)),
        "is_expired": elapsed > SESSION_TIMEOUT,
        "expires_at": datetime.fromtimestamp(SESSION_START + SESSION_TIMEOUT).isoformat()
    }

def check_orphans(data):
    """Check for activities running too long"""
    now = time.time()
    orphans = []
    for a in data.get("running", []):
        started = a.get("started_ts", now)
        if now - started > ORPHAN_TIMEOUT:
            orphans.append({"id": a["id"], "action": a["action"], "target": a["target"], "duration": int(now - started)})
    return orphans if orphans else None

def get_hints(data, target):
    """Generate contextual hints for an activity"""
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
    
    # Check modification history
    for a in data.get("history", []):
        if a.get("target") == target:
            hints["modified_this_session"] = True
            hints["modification_count"] += 1
            hints["last_action"] = a.get("action")
    
    # Check for loops (same target+action 3+ times recently)
    recent = data.get("history", [])[:10]
    loop_count = sum(1 for a in recent if a.get("target") == target)
    if loop_count >= 3:
        hints["loop_detected"] = True
        hints["loop_count"] = loop_count
        hints["suggestion"] = f"Target '{target}' accessed {loop_count} times recently. Consider caching or alternative approach."
    
    # Find related todos
    for t in data.get("todos", []):
        if target and target.lower() in t.get("content", "").lower():
            hints["related_todos"].append({"id": t["id"], "content": t["content"], "status": t.get("status")})
    
    # Count recent errors
    hints["recent_errors"] = len([e for e in data.get("errors", [])[-5:]])
    if data.get("errors"):
        hints["last_error"] = data["errors"][-1].get("message")
    
    return hints

def calc_duration_stats(data):
    """Calculate duration statistics"""
    by_action = {}
    slow_activities = []
    total_duration = 0
    count = 0
    
    for a in data.get("history", []):
        dur = a.get("duration_ms", 0)
        action = a.get("action", "UNKNOWN")
        
        if action not in by_action:
            by_action[action] = {"count": 0, "total_ms": 0, "average_ms": 0}
        
        by_action[action]["count"] += 1
        by_action[action]["total_ms"] += dur
        by_action[action]["average_ms"] = by_action[action]["total_ms"] // by_action[action]["count"]
        
        total_duration += dur
        count += 1
        
        if dur > 30000:  # > 30 seconds
            slow_activities.append({"id": a["id"], "action": action, "target": a.get("target"), "duration_ms": dur})
    
    return {
        "by_action": by_action,
        "slow_activities": slow_activities,
        "total_duration_ms": total_duration,
        "average_duration_ms": total_duration // max(1, count)
    }

def format_duration(ms):
    """Format milliseconds to human readable string"""
    if not ms:
        return "0ms"
    if ms < 1000:
        return f"{ms}ms"
    if ms < 60000:
        return f"{ms/1000:.1f}s"
    return f"{ms/60000:.1f}m"

# --- UI TEMPLATE ---
UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>ACP Minimal v1.0.3</title>
    <style>
        :root { --bg: #0d1117; --card: #161b22; --border: #30363d; --text: #c9d1d9; --primary: #ff6b35; --success: #238636; --danger: #da3633; --warning: #d29922; --info: #58a6ff; }
        body { font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 15px; margin-bottom: 20px; }
        .sys-controls { display: flex; gap: 8px; flex-wrap: wrap; }
        .btn { padding: 8px 14px; border-radius: 6px; cursor: pointer; border: 1px solid var(--border); font-weight: 600; font-size: 0.85rem; color: white; transition: 0.2s; }
        .btn-stop { background: var(--danger); border: none; }
        .btn-restart { background: #21262d; }
        .btn-shutdown { background: #484f58; }
        .btn-nudge { background: var(--primary); border: none; }
        .btn-export { background: var(--info); border: none; }
        .btn:hover { opacity: 0.8; }
        
        .stats-bar { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 20px; }
        .stat-card { background: var(--card); border: 1px solid var(--border); padding: 12px; border-radius: 8px; text-align: center; }
        .stat-label { font-size: 0.65rem; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; }
        .stat-val { display: block; font-size: 1.0rem; font-family: monospace; color: var(--primary); margin-top: 4px; }
        .stat-val.warn { color: var(--warning); }
        .stat-val.danger { color: var(--danger); }
        
        .grid { display: grid; grid-template-columns: 1fr 300px; gap: 20px; }
        @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
        
        .panel { background: var(--card); border: 1px solid var(--border); border-radius: 8px; margin-bottom: 15px; overflow: hidden; animation: fadeIn 0.3s ease-out; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }
        .panel-header { background: rgba(255,255,255,0.03); padding: 10px 15px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); }
        .panel-title { font-weight: 600; font-size: 0.9rem; }
        .panel-body { padding: 12px; max-height: 400px; overflow-y: auto; }
        .panel-footer { background: rgba(0,0,0,0.2); padding: 8px 15px; font-size: 0.75rem; color: #8b949e; display: flex; gap: 15px; border-top: 1px solid var(--border); flex-wrap: wrap; }
        
        .status-pill { font-size: 0.65rem; padding: 2px 8px; border-radius: 10px; font-weight: bold; text-transform: uppercase; }
        .status-running { background: rgba(56, 139, 253, 0.15); color: #58a6ff; border: 1px solid #58a6ff; }
        .status-completed { background: rgba(63, 185, 80, 0.15); color: #3fb950; border: 1px solid #3fb950; }
        .status-error { background: rgba(248, 81, 73, 0.15); color: #f85149; border: 1px solid #f85149; }
        .tag { font-family: monospace; font-size: 0.7rem; color: #8b949e; }
        pre { background: #07090e; padding: 10px; border-radius: 6px; font-size: 0.8rem; overflow-x: auto; border: 1px solid #21262d; margin-top: 8px; color: #88ee88; white-space: pre-wrap; word-break: break-all; }
        .nudge-banner { background: rgba(255, 107, 53, 0.1); border: 1px solid var(--primary); color: var(--primary); padding: 12px; border-radius: 8px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }
        .orphan-banner { background: rgba(210, 153, 34, 0.1); border: 1px solid var(--warning); color: var(--warning); padding: 12px; border-radius: 8px; margin-bottom: 20px; }
        
        .activity-item { border: 1px solid var(--border); border-radius: 6px; margin-bottom: 10px; overflow: hidden; }
        .activity-header { background: rgba(255,255,255,0.02); padding: 8px 12px; display: flex; justify-content: space-between; align-items: center; }
        .activity-body { padding: 10px 12px; font-size: 0.85rem; }
        .activity-target { font-family: monospace; color: var(--info); margin-bottom: 4px; word-break: break-all; }
        
        .todo-item { display: flex; align-items: center; gap: 10px; padding: 8px; border-bottom: 1px solid var(--border); }
        .todo-item:last-child { border-bottom: none; }
        .todo-checkbox { width: 16px; height: 16px; cursor: pointer; }
        .todo-content { flex: 1; font-size: 0.85rem; }
        .todo-priority { font-size: 0.65rem; padding: 2px 6px; border-radius: 4px; }
        .priority-high { background: rgba(248, 81, 73, 0.2); color: #f85149; }
        .priority-medium { background: rgba(210, 153, 34, 0.2); color: #d29922; }
        .priority-low { background: rgba(56, 139, 253, 0.2); color: #58a6ff; }
        
        .shell-item { font-family: monospace; font-size: 0.75rem; padding: 6px 10px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; }
        .shell-cmd { color: var(--info); }
        .shell-status { font-size: 0.65rem; }
        
        .agent-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; margin-right: 5px; }
        .agent-primary { background: rgba(255, 107, 53, 0.2); color: var(--primary); }
        .agent-other { background: rgba(88, 166, 255, 0.2); color: var(--info); }
        
        .section-divider { border-top: 1px solid var(--border); margin: 15px 0; padding-top: 15px; }
        .section-title { font-size: 0.75rem; color: #8b949e; text-transform: uppercase; margin-bottom: 10px; }
        
        .progress-bar { height: 4px; background: var(--border); border-radius: 2px; margin-top: 6px; overflow: hidden; }
        .progress-fill { height: 100%; background: var(--primary); transition: width 0.3s; }
        .progress-fill.warn { background: var(--warning); }
        .progress-fill.danger { background: var(--danger); }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h2 style="margin:0; color:var(--primary)">🤖 ACP Minimal <small style="color:#6e7681; font-size:0.8rem">v1.0.3</small></h2>
                <div id="timer" style="font-family:monospace; font-size:0.8rem; color:#8b949e; margin-top:4px">Sync in 2.0s</div>
            </div>
            <div class="sys-controls">
                <button class="btn btn-nudge" onclick="sendNudge()">📢 NUDGE</button>
                <button class="btn btn-export" onclick="exportSummary()">📄 EXPORT</button>
                <button class="btn btn-stop" onclick="sys('stop')">⛔ STOP</button>
                <button class="btn btn-restart" onclick="sys('reset')">🔄 RESET</button>
                <button class="btn btn-shutdown" onclick="sys('shutdown')">💀 KILL</button>
            </div>
        </div>

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
        const auth = btoa('"""+AUTH_USER+""":"""+AUTH_PASS+"""');
        let timeLeft = 2.0;
        let lastData = null;

        async function api(path, opts={}) {
            try {
                const res = await fetch(path, { ...opts, headers: {'Authorization': 'Basic '+auth, 'Content-Type': 'application/json'}});
                return res.json();
            } catch(e) { return {error: true}; }
        }

        async function sys(type) {
            if(!confirm(`Confirm ${type.toUpperCase()}?`)) return;
            const res = await api(`/api/${type}`, {method: 'POST'});
            if(type === 'shutdown') document.body.innerHTML = "<h1>Server offline.</h1>";
            timeLeft = 0.1;
        }

        async function sendNudge() {
            const m = prompt("Enter guidance for Super Z:");
            if(m) { await api('/api/nudge', {method:'POST', body: JSON.stringify({message:m})}); timeLeft = 0.1; }
        }

        async function exportSummary() {
            const res = await api('/api/summary/export');
            if(res.summary) {
                const blob = new Blob([res.summary], {type: 'text/markdown'});
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url; a.download = 'acp-session-summary.md';
                a.click(); URL.revokeObjectURL(url);
            }
        }

        async function toggleTodo(id) {
            await api('/api/todos/toggle', {method:'POST', body: JSON.stringify({id})});
            timeLeft = 0.1;
        }

        function formatDuration(ms) {
            if (!ms) return '---';
            if (ms < 1000) return ms + 'ms';
            if (ms < 60000) return (ms/1000).toFixed(1) + 's';
            return (ms/60000).toFixed(1) + 'm';
        }

        function formatSession(seconds) {
            if (seconds < 60) return seconds + 's';
            if (seconds < 3600) return Math.floor(seconds/60) + 'm';
            return Math.floor(seconds/3600) + 'h ' + Math.floor((seconds%3600)/60) + 'm';
        }

        async function refresh() {
            const d = await api('/api/all');
            if(d.error) return;
            lastData = d;

            // Stats
            const pct = d.tokens_percent || 0;
            document.getElementById('stat-tokens').innerText = d.session_tokens?.toLocaleString() || '0';
            document.getElementById('stat-pc').innerText = pct.toFixed(1) + '%';
            document.getElementById('stat-pc').className = 'stat-val' + (pct > 80 ? ' danger' : pct > 50 ? ' warn' : '');
            document.getElementById('stat-running').innerText = (d.running || []).length;
            document.getElementById('stat-completed').innerText = (d.history || []).length;
            document.getElementById('stat-primary-agent').innerText = d.primary_agent || '---';
            document.getElementById('stat-last-agent').innerText = d.last_agent || '---';
            document.getElementById('stat-session').innerText = formatSession(d.session?.elapsed_seconds || 0);
            document.getElementById('stat-todos').innerText = (d.todos || []).length;
            document.getElementById('stat-errors').innerText = (d.errors || []).length;
            
            // Token bar
            const bar = document.getElementById('token-bar');
            bar.style.width = Math.min(100, pct) + '%';
            bar.className = 'progress-fill' + (pct > 80 ? ' danger' : pct > 50 ? ' warn' : '');

            // Nudge banner
            const nArea = document.getElementById('nudge-area');
            nArea.innerHTML = d.nudge ? `<div class="nudge-banner"><span><strong>📢 NUDGE:</strong> ${d.nudge.message}</span><small>${d.nudge.timestamp || ''}</small></div>` : '';

            // Orphan banner
            const oArea = document.getElementById('orphan-area');
            if(d.orphan_warning) {
                oArea.innerHTML = `<div class="orphan-banner"><strong>⚠️ ORPHAN WARNING:</strong> ${d.orphan_warning.count} activities running > 5min</div>`;
            } else {
                oArea.innerHTML = '';
            }

            // Running section
            const runningSection = document.getElementById('running-section');
            if(d.running && d.running.length) {
                runningSection.innerHTML = `
                    <div class="panel">
                        <div class="panel-header"><span class="panel-title">🔄 Running (${d.running.length})</span></div>
                        <div class="panel-body">
                            ${d.running.map(a => {
                                const m = a.metadata || {};
                                return `
                                <div class="activity-item">
                                    <div class="activity-header">
                                        <span class="status-pill status-running">${a.status}</span>
                                        <strong>${a.action}</strong>
                                        <span class="tag">#${a.id}</span>
                                    </div>
                                    <div class="activity-body">
                                        <div class="activity-target">${a.target || 'N/A'}</div>
                                        <div>${a.details || ''}</div>
                                    </div>
                                    <div class="panel-footer">
                                        <span>👤 ${m.agent_name || '---'}</span>
                                        <span>🕒 ${a.started || '---'}</span>
                                        <span>⏱️ ${formatDuration(a.duration_ms)}</span>
                                    </div>
                                </div>`;
                            }).join('')}
                        </div>
                    </div>`;
            } else {
                runningSection.innerHTML = '';
            }

            // History section
            const historySection = document.getElementById('history-section');
            if(d.history && d.history.length) {
                historySection.innerHTML = `
                    <div class="panel">
                        <div class="panel-header"><span class="panel-title">📜 History (${d.history.length})</span></div>
                        <div class="panel-body">
                            ${d.history.slice(0, 20).map(a => {
                                const m = a.metadata || {};
                                return `
                                <div class="activity-item">
                                    <div class="activity-header">
                                        <span class="status-pill status-${a.status === 'error' ? 'error' : 'completed'}">${a.status}</span>
                                        <strong>${a.action}</strong>
                                        <span class="tag">#${a.id}</span>
                                    </div>
                                    <div class="activity-body">
                                        <div class="activity-target">${a.target || 'N/A'}</div>
                                        <div>${a.details || ''}</div>
                                        ${a.result ? `<pre>${a.result}</pre>` : ''}
                                    </div>
                                    <div class="panel-footer">
                                        <span>👤 ${m.agent_name || '---'}</span>
                                        <span>🕒 ${a.started || '---'}</span>
                                        <span>⏱️ ${formatDuration(a.duration_ms)}</span>
                                    </div>
                                </div>`;
                            }).join('')}
                        </div>
                    </div>`;
            } else {
                historySection.innerHTML = '<div style="text-align:center; padding:40px; color:#6e7681">No activity logged yet.</div>';
            }

            // Todos panel
            const todosPanel = document.getElementById('todos-panel');
            if(d.todos && d.todos.length) {
                todosPanel.innerHTML = `
                    <div class="panel">
                        <div class="panel-header"><span class="panel-title">📋 Todos (${d.todos.length})</span></div>
                        <div class="panel-body" style="padding:0">
                            ${d.todos.map(t => `
                                <div class="todo-item">
                                    <input type="checkbox" class="todo-checkbox" ${t.status === 'completed' ? 'checked' : ''} onchange="toggleTodo('${t.id}')">
                                    <span class="todo-content" style="${t.status === 'completed' ? 'text-decoration:line-through;opacity:0.6' : ''}">${t.content}</span>
                                    <span class="todo-priority priority-${t.priority || 'medium'}">${t.priority || 'med'}</span>
                                </div>
                            `).join('')}
                        </div>
                    </div>`;
            } else {
                todosPanel.innerHTML = '';
            }

            // Agents panel
            const agentsPanel = document.getElementById('agents-panel');
            if(d.agent_tokens && Object.keys(d.agent_tokens).length) {
                agentsPanel.innerHTML = `
                    <div class="panel">
                        <div class="panel-header"><span class="panel-title">🤖 Agents</span></div>
                        <div class="panel-body">
                            ${Object.entries(d.agent_tokens).map(([name, tokens]) => `
                                <div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--border)">
                                    <span class="agent-badge ${name === d.last_agent ? 'agent-primary' : 'agent-other'}">${name}</span>
                                    <span class="tag">${tokens} tok</span>
                                </div>
                            `).join('')}
                        </div>
                    </div>`;
            } else {
                agentsPanel.innerHTML = '';
            }

            // Shell panel
            const shellPanel = document.getElementById('shell-panel');
            if(d.shell_log && d.shell_log.length) {
                shellPanel.innerHTML = `
                    <div class="panel">
                        <div class="panel-header"><span class="panel-title">💻 Shell (${d.shell_log.length})</span></div>
                        <div class="panel-body" style="padding:0">
                            ${d.shell_log.slice(0, 10).map(s => `
                                <div class="shell-item">
                                    <span class="shell-cmd">${s.command?.substring(0, 30) || '---'}${s.command?.length > 30 ? '...' : ''}</span>
                                    <span class="shell-status ${s.status === 'error' ? 'status-error' : 'status-completed'}">${s.status}</span>
                                </div>
                            `).join('')}
                        </div>
                    </div>`;
            } else {
                shellPanel.innerHTML = '';
            }

            // Hints panel
            const hintsPanel = document.getElementById('hints-panel');
            if(d.hints && (d.hints.loop_detected || d.hints.active_todos > 0)) {
                hintsPanel.innerHTML = `
                    <div class="panel">
                        <div class="panel-header"><span class="panel-title">💡 Hints</span></div>
                        <div class="panel-body">
                            ${d.hints.loop_detected ? `<div style="color:var(--warning);margin-bottom:8px">⚠️ Loop detected: ${d.hints.loop_count} repetitions</div>` : ''}
                            ${d.hints.suggestion ? `<div style="color:var(--info)">${d.hints.suggestion}</div>` : ''}
                            ${d.hints.active_todos > 0 ? `<div class="tag">📌 ${d.hints.active_todos} active todos</div>` : ''}
                        </div>
                    </div>`;
            } else {
                hintsPanel.innerHTML = '';
            }
        }

        setInterval(() => {
            timeLeft -= 0.1;
            if(timeLeft <= 0) { timeLeft = 2.0; refresh(); }
            document.getElementById('timer').innerText = `Sync in ${Math.max(0, timeLeft).toFixed(1)}s`;
        }, 100);
        refresh();
    </script>
</body>
</html>
"""

# --- HANDLER ---
class ACPMinimalHandler(BaseHTTPRequestHandler):
    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def check_auth(self):
        auth = self.headers.get('Authorization', '')
        if auth.startswith('Basic '):
            try:
                u, p = base64.decodebytes(auth[6:].encode()).decode().split(':', 1)
                if u == AUTH_USER and p == AUTH_PASS: return True
            except: pass
        self.send_response(401); self.send_header('WWW-Authenticate', 'Basic realm="ACP"'); self.end_headers()
        return False

    def log_message(self, format, *args):
        pass  # Suppress default logging

    def do_GET(self):
        if not self.check_auth(): return
        
        # UI
        if self.path in ['/', '/api']:
            self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8'); self.end_headers()
            self.wfile.write(UI_HTML.encode('utf-8'))
        
        # whoami
        elif self.path == '/api/whoami':
            self.send_json({
                "success": True, 
                "version": "1.0.3", 
                "capabilities": ["nudge", "notes", "todos", "shell", "add_routes", "hints", "duration_stats", "agent_tracking", "orphan_detection", "files_readonly"],
                "session": get_session_info()
            })
        
        # status
        elif self.path == '/api/status':
            d = load_data()
            session = get_session_info()
            self.send_json({
                "success": True, 
                "tokens": d["tokens"], 
                "tokens_percent": round(d["tokens"]/CONTEXT_WINDOW*100, 2),
                "running": d["running"], 
                "history": d["history"][:25], 
                "nudge": d["nudge"],
                "primary_agent": d.get("primary_agent"), 
                "last_agent": d["last_agent"], 
                "stop_flag": d["stop_flag"],
                "todos": d.get("todos", []), 
                "notes": d.get("notes", ""), 
                "summary": d.get("summary", ""),
                "session": session,
                "agent_tokens": d.get("agent_tokens", {}),
                "errors": d.get("errors", [])[-5:]
            })
        
        # all - combined endpoint
        elif self.path == '/api/all':
            d = load_data()
            session = get_session_info()
            orphans = check_orphans(d)
            
            # Get current files in base directory
            base_dir = os.environ.get("ACP_BASE_DIR", ".")
            current_files = []
            try:
                for item in sorted(os.listdir(base_dir))[:20]:
                    item_path = os.path.join(base_dir, item)
                    current_files.append({
                        "name": item,
                        "is_dir": os.path.isdir(item_path),
                        "size": os.path.getsize(item_path) if os.path.isfile(item_path) else 0
                    })
            except:
                pass
            
            self.send_json({
                "success": True, 
                "stop_flag": d["stop_flag"],
                "running": d["running"], 
                "history": d["history"][:25],
                "session_tokens": d["tokens"], 
                "context_window": CONTEXT_WINDOW,
                "tokens_remaining": CONTEXT_WINDOW - d["tokens"],
                "primary_agent": d.get("primary_agent"),
                "last_agent": d["last_agent"], 
                "nudge": d["nudge"],
                "session": session,
                "todos": d.get("todos", []),
                "shell_log": d.get("shell_log", [])[-10:],
                "agent_tokens": d.get("agent_tokens", {}),
                "errors": d.get("errors", []),
                "orphan_warning": {"count": len(orphans), "tasks": orphans} if orphans else None,
                "current_files": current_files,
                "base_dir": os.path.abspath(base_dir)
            })
        
        # running
        elif self.path == '/api/running':
            d = load_data()
            self.send_json({"success": True, "running": d["running"]})
        
        # activity/{id}
        elif self.path.startswith('/api/activity/'):
            aid = self.path.split('/')[-1]
            d = load_data()
            for a in d["running"] + d["history"]:
                if a["id"] == aid:
                    return self.send_json({"success": True, "activity": a})
            self.send_json({"success": False, "error": "Activity not found"}, 404)
        
        # todos
        elif self.path == '/api/todos':
            d = load_data()
            self.send_json({"success": True, "todos": d.get("todos", [])})
        
        # notes
        elif self.path == '/api/notes':
            d = load_data()
            self.send_json({"success": True, "notes": d.get("notes", "")})
        
        # summary
        elif self.path == '/api/summary':
            d = load_data()
            self.send_json({"success": True, "summary": d.get("summary", "")})
        
        # stats/duration
        elif self.path == '/api/stats/duration':
            d = load_data()
            self.send_json({"success": True, "stats": calc_duration_stats(d)})
        
        # summary/export
        elif self.path == '/api/summary/export':
            d = load_data()
            session = get_session_info()
            summary = f"# ACP Session Summary\n\n"
            summary += f"**Generated:** {datetime.now().isoformat()}\n\n"
            summary += f"## Session Info\n"
            summary += f"- **Tokens Used:** {d['tokens']:,}\n"
            summary += f"- **Context Window:** {CONTEXT_WINDOW:,}\n"
            summary += f"- **Usage:** {round(d['tokens']/CONTEXT_WINDOW*100, 2)}%\n"
            summary += f"- **Primary Agent:** {d['last_agent']}\n"
            summary += f"- **Session Duration:** {format_duration(session['elapsed_seconds'] * 1000)}\n\n"
            summary += f"## Agents\n"
            for name, tokens in d.get("agent_tokens", {}).items():
                summary += f"- {name}: {tokens} tokens\n"
            summary += f"\n## Todos\n"
            for t in d.get("todos", []):
                status = "✅" if t.get("status") == "completed" else "⬜"
                summary += f"- {status} [{t.get('priority', 'med')}] {t.get('content', '')}\n"
            summary += f"\n## Activity History (last 20)\n"
            for a in d.get("history", [])[:20]:
                summary += f"- [{a.get('action')}] {a.get('target')}: {a.get('result', a.get('details', 'N/A'))}\n"
            if d.get("notes"):
                summary += f"\n## Notes\n{d['notes']}\n"
            self.send_json({"success": True, "summary": summary})

        # ==================== READ-ONLY FILE MANAGER ====================
        
        # /api/files/list - List directory contents
        elif self.path.startswith('/api/files/list'):
            # Get path from query param or header
            query_path = self.path.split('?', 1)[1] if '?' in self.path else ''
            rel_path = query_path.replace('path=', '') if 'path=' in query_path else self.headers.get('X-Path', '')
            rel_path = rel_path.strip('/')
            
            # Base directory is project root
            base_dir = os.environ.get("ACP_BASE_DIR", ".")
            full_path = os.path.join(base_dir, rel_path) if rel_path else base_dir
            
            # Security: prevent path traversal
            if not os.path.abspath(full_path).startswith(os.path.abspath(base_dir)):
                return self.send_json({"success": False, "error": "Access denied"}, 403)
            
            if not os.path.exists(full_path):
                return self.send_json({"success": False, "error": "Path not found"}, 404)
            
            if not os.path.isdir(full_path):
                return self.send_json({"success": False, "error": "Not a directory"}, 400)
            
            try:
                items = []
                for item in sorted(os.listdir(full_path)):
                    item_path = os.path.join(full_path, item)
                    stat = os.stat(item_path)
                    items.append({
                        "name": item,
                        "is_dir": os.path.isdir(item_path),
                        "size": stat.st_size if os.path.isfile(item_path) else 0,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                    })
                self.send_json({"success": True, "path": rel_path or "/", "items": items, "base_dir": base_dir})
            except Exception as e:
                self.send_json({"success": False, "error": str(e)}, 500)

        # /api/files/view - View text file content
        elif self.path.startswith('/api/files/view'):
            query_path = self.path.split('?', 1)[1] if '?' in self.path else ''
            rel_path = query_path.replace('path=', '') if 'path=' in query_path else self.headers.get('X-Path', '')
            rel_path = rel_path.strip('/')
            
            base_dir = os.environ.get("ACP_BASE_DIR", ".")
            full_path = os.path.join(base_dir, rel_path)
            
            # Security: prevent path traversal
            if not os.path.abspath(full_path).startswith(os.path.abspath(base_dir)):
                return self.send_json({"success": False, "error": "Access denied"}, 403)
            
            if not os.path.exists(full_path):
                return self.send_json({"success": False, "error": "File not found"}, 404)
            
            if not os.path.isfile(full_path):
                return self.send_json({"success": False, "error": "Not a file"}, 400)
            
            # Check file size (max 100KB for view)
            if os.path.getsize(full_path) > 100000:
                return self.send_json({"success": False, "error": "File too large for viewing (max 100KB)"}, 400)
            
            try:
                with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                lines = content.count('\n') + 1
                tokens = len(content) // 4  # rough estimate
                self.send_json({
                    "success": True, 
                    "path": rel_path, 
                    "content": content,
                    "lines": lines,
                    "size": len(content),
                    "tokens": tokens
                })
            except Exception as e:
                self.send_json({"success": False, "error": str(e)}, 500)

        # /api/files/download - Download any file (binary safe)
        elif self.path.startswith('/api/files/download'):
            query_path = self.path.split('?', 1)[1] if '?' in self.path else ''
            rel_path = query_path.replace('path=', '') if 'path=' in query_path else ''
            rel_path = rel_path.strip('/')
            
            base_dir = os.environ.get("ACP_BASE_DIR", ".")
            full_path = os.path.join(base_dir, rel_path)
            
            # Security: prevent path traversal
            if not os.path.abspath(full_path).startswith(os.path.abspath(base_dir)):
                self.send_response(403)
                self.end_headers()
                return
            
            if not os.path.exists(full_path) or not os.path.isfile(full_path):
                self.send_response(404)
                self.end_headers()
                return
            
            try:
                filename = os.path.basename(full_path)
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
                self.end_headers()
                with open(full_path, 'rb') as f:
                    self.wfile.write(f.read())
            except Exception as e:
                self.send_response(500)
                self.end_headers()

        # /api/files/stats - Get file/directory statistics
        elif self.path == '/api/files/stats':
            base_dir = os.environ.get("ACP_BASE_DIR", ".")
            
            try:
                total_files = 0
                total_dirs = 0
                total_size = 0
                
                for root, dirs, files in os.walk(base_dir):
                    total_dirs += len(dirs)
                    total_files += len(files)
                    for f in files:
                        try:
                            total_size += os.path.getsize(os.path.join(root, f))
                        except:
                            pass
                
                self.send_json({
                    "success": True,
                    "base_dir": base_dir,
                    "total_files": total_files,
                    "total_directories": total_dirs,
                    "total_size_bytes": total_size,
                    "total_size_mb": round(total_size / (1024 * 1024), 2)
                })
            except Exception as e:
                self.send_json({"success": False, "error": str(e)}, 500)

    def do_POST(self):
        if not self.check_auth(): return
        l = int(self.headers.get('Content-Length', 0))
        req = json.loads(self.rfile.read(l).decode('utf-8')) if l else {}
        data = load_data()
        now = time.time()

        # /api/stop
        if self.path == '/api/stop':
            data["stop_flag"] = True
            data["running"] = []
            save_data(data)
            return self.send_json({"success": True, "stop_flag": True})

        # /api/nudge
        elif self.path == '/api/nudge':
            data["nudge"] = {
                "message": req.get('message'), 
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "priority": req.get('priority', 'normal'),
                "requires_ack": req.get('requires_ack', False)
            }
            save_data(data)
            return self.send_json({"success": True})

        # /api/nudge/ack
        elif self.path == '/api/nudge/ack':
            data["nudge"] = None
            save_data(data)
            return self.send_json({"success": True})

        # /api/action
        elif self.path == '/api/action':
            if data["stop_flag"]: 
                return self.send_json({"error": "Stopped", "stop_flag": True}, 403)
            
            hints = None
            target = req.get('target', '')
            
            # 1. Complete Activity
            if req.get('complete_id'):
                for i, a in enumerate(data["running"]):
                    if a["id"] == req["complete_id"]:
                        duration_ms = int((now - a.get("started_ts", now)) * 1000)
                        a.update({
                            "status": "completed", 
                            "result": req.get('result', ''),
                            "duration_ms": duration_ms
                        })
                        data["history"].insert(0, a)
                        data["running"].pop(i)
                        break

            # 2. Get hints for target
            if target:
                hints = get_hints(data, target)

            # 3. Identity & Action Persistence
            meta = req.get('metadata', {})
            agent_name = meta.get('agent_name')
            
            if agent_name: 
                # Set primary_agent ONCE - first agent wins
                if not data.get("primary_agent") or data["primary_agent"] == "Unknown":
                    data["primary_agent"] = agent_name
                
                # Always update last_agent (tracks most recent)
                data["last_agent"] = agent_name
                data["last_model"] = meta.get('model_name', data.get("last_model", "---"))
                
                # Track per-agent tokens
                if "agent_tokens" not in data:
                    data["agent_tokens"] = {}
                data["agent_tokens"][agent_name] = data["agent_tokens"].get(agent_name, 0) + max(1, estimate_tokens([req.get('action'), target], req.get('content_size', 0)))
            else:
                meta['agent_name'] = data.get("last_agent", "Unknown")
                meta['model_name'] = data.get("last_model", "---")

            data["tokens"] += max(1, estimate_tokens([req.get('action'), target], req.get('content_size', 0)))
            aid = datetime.now().strftime("%H%M%S-") + str(int(time.time()*100)%100)
            
            activity = {
                "id": aid, 
                "action": req.get('action'), 
                "target": target,
                "details": req.get('details', ''), 
                "metadata": meta, 
                "status": "running",
                "started": datetime.now().strftime("%H:%M:%S"),
                "started_ts": now,
                "priority": req.get('priority', 'medium')
            }
            data["running"].append(activity)
            
            # Check for orphans
            orphans = check_orphans(data)
            orphan_warning = {"count": len(orphans), "tasks": orphans} if orphans else None
            
            save_data(data)
            return self.send_json({
                "success": True, 
                "activity_id": aid, 
                "nudge": data["nudge"],
                "hints": hints,
                "orphan_warning": orphan_warning
            })

        # /api/complete
        elif self.path == '/api/complete':
            aid = req.get('activity_id')
            result = req.get('result', '')
            content_size = req.get('content_size', 0)
            
            for i, a in enumerate(data["running"]):
                if a["id"] == aid:
                    duration_ms = int((now - a.get("started_ts", now)) * 1000)
                    a.update({
                        "status": "completed", 
                        "result": result,
                        "duration_ms": duration_ms
                    })
                    data["history"].insert(0, a)
                    data["running"].pop(i)
                    
                    # Add content size to tokens if provided
                    if content_size:
                        data["tokens"] += int(content_size / 3.5)
                    
                    save_data(data)
                    return self.send_json({"success": True, "activity_id": aid, "status": "completed", "duration_ms": duration_ms})
            
            # Log error if not found
            data.setdefault("errors", []).append({
                "timestamp": datetime.now().isoformat(),
                "message": f"Activity not found: {aid}",
                "type": "complete_error"
            })
            save_data(data)
            return self.send_json({"success": False, "error": "Activity not found"}, 404)

        # /api/todos/add
        elif self.path == '/api/todos/add':
            data.setdefault("todos", [])
            data["todos"].append({
                "id": req.get('id', datetime.now().strftime("%H%M%S-") + str(int(time.time()*100)%100)),
                "content": req.get('content', ''),
                "status": req.get('status', 'pending'),
                "priority": req.get('priority', 'medium'),
                "created": datetime.now().isoformat(),
                "metadata": req.get('metadata', {})
            })
            save_data(data)
            return self.send_json({"success": True, "count": len(data["todos"])})

        # /api/todos/update
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

        # /api/todos/clear
        elif self.path == '/api/todos/clear':
            data["todos"] = [t for t in data.get("todos", []) if t.get('status') != 'completed']
            save_data(data)
            return self.send_json({"success": True, "count": len(data["todos"])})

        # /api/notes/add
        elif self.path == '/api/notes/add':
            existing = data.get("notes", "")
            category = req.get('category', 'note')
            content = req.get('content', '')
            timestamp = datetime.now().strftime("%H:%M:%S")
            new_note = f"[{timestamp}] [{category}] {content}"
            data["notes"] = existing + "\n" + new_note if existing else new_note
            save_data(data)
            return self.send_json({"success": True})

        # /api/shell/add
        elif self.path == '/api/shell/add':
            aid = datetime.now().strftime("%H%M%S-") + str(int(time.time()*100)%100)
            cmd = req.get('command', '')
            
            # Add to shell log
            data.setdefault("shell_log", [])
            data["shell_log"].append({
                "id": aid,
                "command": cmd,
                "status": req.get('status', 'completed'),
                "output_preview": req.get('output_preview', '')[:200],
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "metadata": req.get('metadata', {})
            })
            
            # Keep only last 50
            data["shell_log"] = data["shell_log"][-50:]
            
            # Also add to history
            data["history"].insert(0, {
                "id": aid,
                "action": "BASH",
                "target": cmd,
                "details": req.get('output_preview', '')[:200],
                "status": req.get('status', 'completed'),
                "started": datetime.now().strftime("%H:%M:%S"),
                "started_ts": now,
                "metadata": req.get('metadata', {})
            })
            save_data(data)
            return self.send_json({"success": True, "activity_id": aid})

        # /api/reset
        elif self.path == '/api/reset':
            save_data({
                "running": [], 
                "history": [], 
                "stop_flag": False, 
                "tokens": 0, 
                "files_read": [], 
                "nudge": None, 
                "last_agent": "Unknown",
                "last_model": "---",
                "todos": [], 
                "notes": "", 
                "summary": "Session Reset.",
                "session_start": time.time(),
                "agent_tokens": {},
                "shell_log": [],
                "errors": []
            })
            return self.send_json({"success": True})

        # /api/shutdown
        elif self.path == '/api/shutdown':
            self.send_json({"success": True, "message": "Shutting down..."})
            os.kill(os.getpid(), signal.SIGINT)
            return

        # Unknown endpoint
        else:
            return self.send_json({"success": False, "error": f"Unknown endpoint: {self.path}"}, 404)

if __name__ == "__main__":
    print(f"🤖 ACP Minimal v1.0.3 active on port {PORT}")
    print(f"   Context Window: {CONTEXT_WINDOW:,} tokens")
    print(f"   Session Timeout: {SESSION_TIMEOUT}s")
    print(f"   Orphan Timeout: {ORPHAN_TIMEOUT}s")
    print(f"   Base Directory: {os.environ.get('ACP_BASE_DIR', '.')}")
    print(f"   File Endpoints: list, view, download, stats (read-only)")
    HTTPServer(('0.0.0.0', PORT), ACPMinimalHandler).serve_forever()