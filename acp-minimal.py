#!/usr/bin/env python3
"""
ACP Minimal - Barebones Agent Control Panel with Basic UI
Reference: https://github.com/VTSTech/ACP-Agent-Control-Panel
License: MIT
"""

import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
import time

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════
PORT = int(os.environ.get("ACP_PORT", "8766"))
AUTH_USER = os.environ.get("ACP_USER", "admin")
AUTH_PASS = os.environ.get("ACP_PASS", "secret")
DATA_FILE = os.environ.get("ACP_DATA_FILE", "acp_data.json")
CONTEXT_WINDOW = int(os.environ.get("ACP_CONTEXT_WINDOW", "200000"))
VERSION = "v1.0.1"

# ═══════════════════════════════════════════════════════════════════════════════
# DATA STORAGE
# ═══════════════════════════════════════════════════════════════════════════════
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {"running": [], "history": [], "stop_flag": False, "stop_reason": None, 
            "tokens": 0, "shell": [], "todos": [], "notes": []}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

# ═══════════════════════════════════════════════════════════════════════════════
# UI TEMPLATE
# ═══════════════════════════════════════════════════════════════════════════════
UI_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>ACP Minimal</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: system-ui, sans-serif; background: #0d1117; color: #e6edf3; min-height: 100vh; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #30363d; }
        .logo { font-size: 1.5rem; font-weight: bold; color: #ff6b35; }
        .status-badge { padding: 6px 14px; border-radius: 20px; font-size: 0.85rem; font-weight: 600; }
        .status-active { background: #238636; }
        .status-stopped { background: #da3633; animation: pulse 1.5s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
        .grid { display: grid; grid-template-columns: 300px 1fr; gap: 20px; }
        .sidebar { display: flex; flex-direction: column; gap: 15px; }
        .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 15px; }
        .card-title { font-size: 0.75rem; color: #8b949e; text-transform: uppercase; margin-bottom: 12px; }
        .stat { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #21262d; }
        .stat:last-child { border-bottom: none; }
        .stat-label { color: #8b949e; }
        .stat-value { font-weight: 600; font-family: monospace; }
        .token-bar { height: 8px; background: #21262d; border-radius: 4px; margin-top: 10px; overflow: hidden; }
        .token-fill { height: 100%; background: linear-gradient(90deg, #3fb950, #f0883e, #da3633); border-radius: 4px; transition: width 0.3s; }
        .btn { padding: 10px 16px; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 0.9rem; transition: all 0.2s; }
        .btn-danger { background: #da3633; color: white; }
        .btn-danger:hover { filter: brightness(1.1); }
        .btn-success { background: #238636; color: white; }
        .btn-success:hover { filter: brightness(1.1); }
        .btn-secondary { background: #21262d; color: #e6edf3; border: 1px solid #30363d; }
        .btn-secondary:hover { background: #30363d; }
        .actions { display: flex; gap: 10px; margin-top: 10px; }
        .main { display: flex; flex-direction: column; gap: 15px; }
        .tabs { display: flex; gap: 5px; margin-bottom: 10px; }
        .tab { padding: 8px 16px; background: transparent; border: none; color: #8b949e; cursor: pointer; border-radius: 6px; }
        .tab.active { background: #21262d; color: #e6edf3; }
        .tab:hover { background: #21262d; }
        .activity-list { display: flex; flex-direction: column; gap: 8px; }
        .activity { background: #0d1117; border-radius: 6px; padding: 12px; border-left: 3px solid; }
        .activity.running { border-left-color: #58a6ff; }
        .activity.completed { border-left-color: #3fb950; }
        .activity.cancelled { border-left-color: #f0883e; opacity: 0.7; }
        .activity-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px; }
        .activity-action { font-weight: 600; font-size: 0.8rem; padding: 2px 8px; border-radius: 4px; background: #21262d; }
        .activity-action.priority-high { background: #da3633; }
        .activity-action.priority-low { background: #6e7681; }
        .activity-target { font-family: monospace; font-size: 0.85rem; color: #8b949e; }
        .activity-meta { font-size: 0.75rem; color: #58a6ff; margin-top: 3px; }
        .activity-time { font-size: 0.75rem; color: #6e7681; }
        .activity-result { font-size: 0.8rem; color: #8b949e; margin-top: 5px; padding-top: 5px; border-top: 1px solid #21262d; }
        .shell-list { display: flex; flex-direction: column; gap: 6px; }
        .shell-cmd { background: #0d1117; border-radius: 4px; padding: 8px 12px; font-family: monospace; font-size: 0.85rem; display: flex; justify-content: space-between; }
        .shell-cmd code { color: #58a6ff; }
        .shell-status { font-size: 0.75rem; padding: 2px 6px; border-radius: 4px; }
        .shell-status.completed { background: #238636; }
        .shell-status.error { background: #da3633; }
        .empty { text-align: center; padding: 30px; color: #6e7681; }
        .stop-banner { background: #da3633; color: white; padding: 12px 15px; border-radius: 8px; margin-bottom: 15px; display: none; align-items: center; justify-content: space-between; }
        .stop-banner.show { display: flex; }
        @media (max-width: 768px) { .grid { grid-template-columns: 1fr; } }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">🤖 ACP Minimal</div>
            <div id="status-badge" class="status-badge status-active">ACTIVE</div>
        </div>
        
        <div id="stop-banner" class="stop-banner">
            <span>⛔ <strong>STOPPED:</strong> <span id="stop-reason"></span></span>
            <button class="btn btn-secondary" onclick="resume()">Resume</button>
        </div>
        
        <div class="grid">
            <div class="sidebar">
                <div class="card">
                    <div class="card-title">Session</div>
                    <div class="stat"><span class="stat-label">Tokens</span><span class="stat-value" id="tokens">0</span></div>
                    <div class="stat"><span class="stat-label">Remaining</span><span class="stat-value" id="remaining">200,000</span></div>
                    <div class="stat"><span class="stat-label">Usage</span><span class="stat-value" id="percent">0%</span></div>
                    <div class="token-bar"><div class="token-fill" id="token-bar" style="width: 0%"></div></div>
                </div>
                
                <div class="card">
                    <div class="card-title">Activity</div>
                    <div class="stat"><span class="stat-label">Running</span><span class="stat-value" id="running-count">0</span></div>
                    <div class="stat"><span class="stat-label">Completed</span><span class="stat-value" id="history-count">0</span></div>
                    <div class="actions">
                        <button class="btn btn-danger" onclick="stopAll()">⛔ STOP ALL</button>
                        <button class="btn btn-secondary" onclick="reset()">Reset</button>
                    </div>
                </div>
                
                <div class="card">
                    <div class="card-title">TODOs</div>
                    <div id="todos" class="activity-list"></div>
                </div>
            </div>
            
            <div class="main">
                <div class="tabs">
                    <button class="tab active" onclick="showTab('activity')">Activity</button>
                    <button class="tab" onclick="showTab('terminal')">Terminal</button>
                </div>
                
                <div id="activity-tab" class="card">
                    <div class="activity-list" id="activity-list"></div>
                </div>
                
                <div id="terminal-tab" class="card" style="display:none">
                    <div class="shell-list" id="shell-list"></div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        const auth = btoa('""" + AUTH_USER + """:""" + AUTH_PASS + """');
        let currentTab = 'activity';
        
        async function api(path, opts = {}) {
            const res = await fetch(path, { ...opts, headers: { 'Authorization': 'Basic ' + auth, ...opts.headers } });
            return res.json();
        }
        
        async function refresh() {
            const data = await api('/api/status');
            
            // Update status
            document.getElementById('status-badge').className = 'status-badge ' + (data.stop_flag ? 'status-stopped' : 'status-active');
            document.getElementById('status-badge').textContent = data.stop_flag ? 'STOPPED' : 'ACTIVE';
            document.getElementById('stop-banner').className = 'stop-banner ' + (data.stop_flag ? 'show' : '');
            document.getElementById('stop-reason').textContent = data.stop_reason || '';
            
            // Update tokens
            document.getElementById('tokens').textContent = data.tokens?.toLocaleString() || '0';
            document.getElementById('remaining').textContent = data.tokens_remaining?.toLocaleString() || '200,000';
            document.getElementById('percent').textContent = data.tokens_percent?.toFixed(1) + '%' || '0%';
            document.getElementById('token-bar').style.width = Math.min(data.tokens_percent || 0, 100) + '%';
            
            // Update counts
            document.getElementById('running-count').textContent = data.running?.length || 0;
            
            // Update activity list
            const actList = document.getElementById('activity-list');
            if (data.running?.length > 0 || data.history?.length > 0) {
                const items = [...(data.running || []), ...(data.history || []).slice(0, 20)];
                actList.innerHTML = items.map(a => {
                    const priority = a.priority || 'medium';
                    const agentName = a.metadata?.agent_name || '';
                    const priorityClass = priority === 'high' ? 'priority-high' : priority === 'low' ? 'priority-low' : '';
                    return `
                    <div class="activity ${a.status}">
                        <div class="activity-header">
                            <span class="activity-action ${priorityClass}">${a.action}</span>
                            <span class="activity-time">${a.status} ${a.completed ? '✓' : '⏳'}</span>
                        </div>
                        <div class="activity-target">${a.target}</div>
                        ${agentName ? `<div class="activity-meta">👤 ${agentName}</div>` : ''}
                        ${a.result ? `<div class="activity-result">${a.result}</div>` : ''}
                    </div>
                `}).join('');
            } else {
                actList.innerHTML = '<div class="empty">No activity yet</div>';
            }
            
            document.getElementById('history-count').textContent = data.history?.length || 0;
            
            // Update shell
            const shellList = document.getElementById('shell-list');
            if (data.shell?.length > 0) {
                shellList.innerHTML = data.shell.slice(0, 20).map(s => `
                    <div class="shell-cmd">
                        <code>${s.command?.substring(0, 60) || ''}</code>
                        <span class="shell-status ${s.status}">${s.status}</span>
                    </div>
                `).join('');
            } else {
                shellList.innerHTML = '<div class="empty">No commands yet</div>';
            }
            
            // Update todos
            const todosList = document.getElementById('todos');
            if (data.todos?.length > 0) {
                todosList.innerHTML = data.todos.slice(0, 5).map(t => `
                    <div class="activity ${t.status === 'completed' ? 'completed' : 'running'}">
                        <span style="${t.status === 'completed' ? 'text-decoration: line-through; opacity: 0.6' : ''}">${t.content?.substring(0, 40) || ''}</span>
                    </div>
                `).join('');
            } else {
                todosList.innerHTML = '<div class="empty" style="padding: 10px">No tasks</div>';
            }
        }
        
        function showTab(tab) {
            currentTab = tab;
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            event.target.classList.add('active');
            document.getElementById('activity-tab').style.display = tab === 'activity' ? 'block' : 'none';
            document.getElementById('terminal-tab').style.display = tab === 'terminal' ? 'block' : 'none';
        }
        
        async function stopAll() {
            if (confirm('Stop all agent activity?')) {
                await api('/api/stop', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reason: 'User clicked STOP ALL' }) });
                refresh();
            }
        }
        
        async function resume() {
            await api('/api/resume', { method: 'POST' });
            refresh();
        }
        
        async function reset() {
            if (confirm('Reset session? This clears all history.')) {
                await api('/api/reset', { method: 'POST' });
                refresh();
            }
        }
        
        refresh();
        setInterval(refresh, 2000);
    </script>
</body>
</html>
"""

# ═══════════════════════════════════════════════════════════════════════════════
# HTTP HANDLER
# ═══════════════════════════════════════════════════════════════════════════════
class ACPHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[{datetime.now().isoformat()}] {args[0]}")

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())

    def check_auth(self):
        auth = self.headers.get('Authorization', '')
        if auth.startswith('Basic '):
            import base64
            try:
                creds = base64.b64decode(auth[6:]).decode()
                user, pwd = creds.split(':', 1)
                if user == AUTH_USER and pwd == AUTH_PASS:
                    return True
            except: pass
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="ACP"')
        self.end_headers()
        return False

    def do_GET(self):
        if not self.check_auth(): return
        
        if self.path == '/' or self.path == '/api':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(UI_HTML.encode())
        
        elif self.path == '/api/status':
            data = load_data()
            tokens = data.get("tokens", 0)
            self.send_json({
                "success": True,
                "stop_flag": data["stop_flag"],
                "stop_reason": data["stop_reason"],
                "running": data["running"],
                "history": data.get("history", [])[-50:],
                "shell": data.get("shell", [])[-20:],
                "todos": data.get("todos", [])[-10:],
                "tokens": tokens,
                "tokens_percent": round(tokens / CONTEXT_WINDOW * 100, 1),
                "tokens_remaining": max(0, CONTEXT_WINDOW - tokens),
                "context_window": CONTEXT_WINDOW,
                "version": VERSION
            })
        
        elif self.path == '/api/whoami':
            self.send_json({
                "success": True,
                "identity": {
                    "hint": "You are an AI agent. Identify yourself by name.",
                    "suggestion": "Use agent_name in activity metadata.",
                    "example": {"metadata": {"agent_name": "MyAgent"}}
                },
                "version": VERSION
            })
        
        elif self.path.startswith('/api/activity/'):
            data = load_data()
            act_id = self.path.split('/')[-1]
            # Search in running and history
            for act in data.get("running", []) + data.get("history", []):
                if act.get("id") == act_id:
                    self.send_json({"success": True, "activity": act})
                    return
            self.send_json({"success": False, "error": "Activity not found"}, 404)
        
        else:
            self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        if not self.check_auth(): return
        
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode() if length else '{}'
        try: req = json.loads(body)
        except: self.send_json({"error": "Invalid JSON"}, 400); return

        if self.path == '/api/action':
            data = load_data()
            if data["stop_flag"]:
                self.send_json({"error": "Stop requested", "stop_flag": True}, 403)
                return
            
            # Complete previous
            if req.get('complete_id'):
                for i, act in enumerate(data["running"]):
                    if act["id"] == req["complete_id"]:
                        act["status"] = "completed"
                        act["result"] = req.get('result', '')[:500]
                        act["completed"] = datetime.now().isoformat()
                        data.setdefault("history", []).insert(0, act)
                        data["running"].pop(i)
                        break
            
            # Start new
            action = req.get('action', 'UNKNOWN')
            target = req.get('target', '')
            details = req.get('details', '')
            content_size = req.get('content_size', 0)
            priority = req.get('priority', 'medium')
            metadata = req.get('metadata', {})
            
            # Token estimation: basic fields + content_size
            tokens = int((len(action) + len(target) + len(details) + content_size) / 3.5)
            data["tokens"] = data.get("tokens", 0) + tokens
            
            act_id = datetime.now().strftime("%H%M%S-") + str(int(time.time() * 1000) % 100000)
            activity = {
                "id": act_id, "action": action, "target": target, "details": details,
                "status": "running", "started": datetime.now().isoformat(),
                "priority": priority, "metadata": metadata
            }
            data.setdefault("running", []).append(activity)
            save_data(data)
            self.send_json({
                "success": True, "activity_id": act_id, "stop_flag": False,
                "tokens": data["tokens"], "tokens_percent": round(data["tokens"] / CONTEXT_WINDOW * 100, 1),
                "tokens_remaining": max(0, CONTEXT_WINDOW - data["tokens"])
            })

        elif self.path == '/api/stop':
            data = load_data()
            data["stop_flag"] = True
            data["stop_reason"] = req.get('reason', 'User requested')
            for act in data.get("running", []):
                act["status"] = "cancelled"
                data.setdefault("history", []).insert(0, act)
            data["running"] = []
            save_data(data)
            self.send_json({"success": True})

        elif self.path == '/api/resume':
            data = load_data()
            data["stop_flag"] = False
            data["stop_reason"] = None
            save_data(data)
            self.send_json({"success": True})

        elif self.path == '/api/reset':
            save_data({"running": [], "history": [], "stop_flag": False, "stop_reason": None, 
                      "tokens": 0, "shell": [], "todos": []})
            self.send_json({"success": True})

        elif self.path == '/api/shell/add':
            data = load_data()
            entry = {"command": req.get('command', '')[:200], "status": req.get('status', 'completed'),
                    "timestamp": datetime.now().isoformat()}
            data.setdefault("shell", []).insert(0, entry)
            if len(data["shell"]) > 50: data["shell"] = data["shell"][:50]
            save_data(data)
            self.send_json({"success": True})

        elif self.path == '/api/todos/update':
            data = load_data()
            data["todos"] = req.get('todos', [])
            save_data(data)
            self.send_json({"success": True})
        
        elif self.path == '/api/notes/add':
            data = load_data()
            note = {
                "category": req.get('category', 'context'),
                "content": req.get('content', '')[:500],
                "importance": req.get('importance', 'normal'),
                "timestamp": datetime.now().isoformat()
            }
            data.setdefault("notes", []).insert(0, note)
            if len(data["notes"]) > 50: data["notes"] = data["notes"][:50]
            save_data(data)
            self.send_json({"success": True})

        else:
            self.send_json({"error": "Not found"}, 404)

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print(f"ACP Minimal {VERSION} starting on port {PORT}")
    print(f"Auth: {AUTH_USER}:{AUTH_PASS}")
    print(f"Open http://localhost:{PORT} in browser")
    HTTPServer(('0.0.0.0', PORT), ACPHandler).serve_forever()
