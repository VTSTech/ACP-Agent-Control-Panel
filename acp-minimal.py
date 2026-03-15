#!/usr/bin/env python3
"""
ACP Minimal v1.0.3 - Full Spec Compliance
Endpoints: whoami, status, action, nudge, nudge/ack, stop, reset, shutdown
"""

import json, os, base64, time, signal
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

# --- CONFIG ---
PORT = int(os.environ.get("ACP_PORT", "8766"))
AUTH_USER = os.environ.get("ACP_USER", "admin")
AUTH_PASS = os.environ.get("ACP_PASS", "secret")
DATA_FILE = os.environ.get("ACP_DATA_FILE", "acp_data.json")
CONTEXT_WINDOW = int(os.environ.get("ACP_CONTEXT_WINDOW", "200000"))

def load_data():
    defaults = {
        "running":[], "history":[], "stop_flag":False, "tokens":0, 
        "files_read":[], "nudge":None, "last_agent": "Unknown", "last_model": "Unknown",
        "todos":[], "notes":"", "summary":"Session Reset."
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

# --- UI TEMPLATE ---
UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>ACP Minimal v1.0.3</title>
    <style>
        :root { --bg: #0d1117; --card: #161b22; --border: #30363d; --text: #c9d1d9; --primary: #ff6b35; --success: #238636; --danger: #da3633; }
        body { font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 20px; }
        .container { max-width: 1000px; margin: 0 auto; }
        .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 15px; margin-bottom: 20px; }
        .sys-controls { display: flex; gap: 8px; }
        .btn { padding: 8px 14px; border-radius: 6px; cursor: pointer; border: 1px solid var(--border); font-weight: 600; font-size: 0.85rem; color: white; transition: 0.2s; }
        .btn-stop { background: var(--danger); border: none; }
        .btn-restart { background: #21262d; }
        .btn-shutdown { background: #484f58; }
        .btn-nudge { background: var(--primary); border: none; }
        .btn:hover { opacity: 0.8; }
        
        .stats-bar { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-bottom: 20px; }
        .stat-card { background: var(--card); border: 1px solid var(--border); padding: 12px; border-radius: 8px; text-align: center; }
        .stat-label { font-size: 0.7rem; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; }
        .stat-val { display: block; font-size: 1.1rem; font-family: monospace; color: var(--primary); margin-top: 4px; }

        .panel { background: var(--card); border: 1px solid var(--border); border-radius: 8px; margin-bottom: 15px; overflow: hidden; animation: fadeIn 0.3s ease-out; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }
        .panel-header { background: rgba(255,255,255,0.03); padding: 10px 15px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); }
        .panel-body { padding: 15px; }
        .panel-footer { background: rgba(0,0,0,0.2); padding: 8px 15px; font-size: 0.75rem; color: #8b949e; display: flex; gap: 20px; border-top: 1px solid var(--border); }
        
        .status-pill { font-size: 0.7rem; padding: 2px 8px; border-radius: 10px; font-weight: bold; text-transform: uppercase; }
        .status-running { background: rgba(56, 139, 253, 0.15); color: #58a6ff; border: 1px solid #58a6ff; }
        .status-completed { background: rgba(63, 185, 80, 0.15); color: #3fb950; border: 1px solid #3fb950; }
        .tag { font-family: monospace; font-size: 0.75rem; color: #8b949e; }
        pre { background: #07090e; padding: 12px; border-radius: 6px; font-size: 0.85rem; overflow-x: auto; border: 1px solid #21262d; margin-top: 10px; color: #88ee88; }
        .nudge-banner { background: rgba(255, 107, 53, 0.1); border: 1px solid var(--primary); color: var(--primary); padding: 12px; border-radius: 8px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }
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
                <button class="btn btn-stop" onclick="sys('stop')">⛔ STOP</button>
                <button class="btn btn-restart" onclick="sys('reset')">🔄 RESET</button>
                <button class="btn btn-shutdown" onclick="sys('shutdown')">💀 KILL</button>
            </div>
        </div>

        <div id="nudge-area"></div>

        <div class="stats-bar">
            <div class="stat-card"><span class="stat-label">Tokens Used</span><span id="stat-tokens" class="stat-val">0</span></div>
            <div class="stat-card"><span class="stat-label">Context Load</span><span id="stat-pc" class="stat-val">0%</span></div>
            <div class="stat-card"><span class="stat-label">Primary Agent</span><span id="stat-agent" class="stat-val">---</span></div>
        </div>

        <div id="activity-list"></div>
    </div>

    <script>
        const auth = btoa('"""+AUTH_USER+""":"""+AUTH_PASS+"""');
        let timeLeft = 2.0;

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

        async function refresh() {
            const d = await api('/api/status');
            if(d.error) return;
            document.getElementById('stat-tokens').innerText = d.tokens.toLocaleString();
            document.getElementById('stat-pc').innerText = d.tokens_percent + '%';
            document.getElementById('stat-agent').innerText = d.last_agent;

            const nArea = document.getElementById('nudge-area');
            nArea.innerHTML = d.nudge ? `<div class="nudge-banner"><span><strong>QUEUED NUDGE:</strong> ${d.nudge.message}</span><small>${d.nudge.timestamp}</small></div>` : '';

            const items = [...(d.running || []), ...(d.history || [])];
            document.getElementById('activity-list').innerHTML = items.length ? items.map(a => {
                const m = a.metadata || {};
                return `
                <div class="panel">
                    <div class="panel-header">
                        <div>
                            <span class="status-pill status-${a.status}">${a.status}</span>
                            <strong style="margin-left:10px">${a.action}</strong>
                        </div>
                        <span class="tag">#${a.id}</span>
                    </div>
                    <div class="panel-body">
                        <div style="font-family:monospace; color:#58a6ff; margin-bottom:8px">${a.target || 'N/A'}</div>
                        <div style="font-size:0.9rem">${a.details || ''}</div>
                        ${a.result ? `<pre>${a.result}</pre>` : ''}
                    </div>
                    <div class="panel-footer">
                        <span>👤 ${m.agent_name || '---'}</span>
                        <span>🤖 ${m.model_name || '---'}</span>
                        <span>🕒 ${a.started || '---'}</span>
                    </div>
                </div>`;
            }).join('') : '<div style="text-align:center; padding:40px; color:#6e7681">No activity logged yet.</div>';
        }

        async function sendNudge() {
            const m = prompt("Enter guidance for Super Z:");
            if(m) { await api('/api/nudge', {method:'POST', body: JSON.stringify({message:m})}); timeLeft = 0.1; }
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

    def do_GET(self):
        if not self.check_auth(): return
        if self.path in ['/', '/api']:
            self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8'); self.end_headers()
            self.wfile.write(UI_HTML.encode('utf-8'))
        elif self.path == '/api/whoami':
            self.send_json({"success":True, "version":"1.0.3", "capabilities":["nudge", "notes", "todos", "shell", "add_routes"]})
        elif self.path == '/api/status':
            d = load_data()
            self.send_json({
                "success":True, "tokens":d["tokens"], "tokens_percent":round(d["tokens"]/CONTEXT_WINDOW*100, 2),
                "running":d["running"], "history":d["history"][:25], "nudge":d["nudge"],
                "last_agent":d["last_agent"], "stop_flag":d["stop_flag"],
                "todos":d.get("todos", []), "notes":d.get("notes", ""), "summary":d.get("summary", "")
            })
        elif self.path == '/api/all':
            d = load_data()
            self.send_json({
                "success": True, "stop_flag": d["stop_flag"],
                "running": d["running"], "history": d["history"][:25],
                "session_tokens": d["tokens"], "context_window": CONTEXT_WINDOW,
                "tokens_remaining": CONTEXT_WINDOW - d["tokens"],
                "last_agent": d["last_agent"], "nudge": d["nudge"]
            })
        elif self.path == '/api/todos':
            d = load_data()
            self.send_json({"success": True, "todos": d.get("todos", [])})
        elif self.path == '/api/notes':
            d = load_data()
            self.send_json({"success": True, "notes": d.get("notes", "")})
        elif self.path == '/api/summary':
            d = load_data()
            self.send_json({"success": True, "summary": d.get("summary", "")})

    def do_POST(self):
        if not self.check_auth(): return
        l = int(self.headers.get('Content-Length', 0))
        req = json.loads(self.rfile.read(l).decode('utf-8')) if l else {}
        data = load_data()

        # MANDATORY: /api/stop
        if self.path == '/api/stop':
            data["stop_flag"] = True; data["running"] = []
            save_data(data); return self.send_json({"success": True})

        # MANDATORY: /api/nudge
        elif self.path == '/api/nudge':
            data["nudge"] = {"message": req.get('message'), "timestamp": datetime.now().strftime("%H:%M:%S")}
            save_data(data); return self.send_json({"success": True})

        # MANDATORY: /api/nudge/ack
        elif self.path == '/api/nudge/ack':
            data["nudge"] = None
            save_data(data); return self.send_json({"success": True})

        # MANDATORY: /api/action
        elif self.path == '/api/action':
            if data["stop_flag"]: return self.send_json({"error": "Stopped", "stop_flag": True}, 403)
            
            # 1. Complete Activity
            if req.get('complete_id'):
                for i, a in enumerate(data["running"]):
                    if a["id"] == req["complete_id"]:
                        a.update({"status":"completed", "result":req.get('result', '')})
                        data["history"].insert(0, a); data["running"].pop(i); break

            # 2. Identity & Action Persistence
            meta = req.get('metadata', {})
            if meta.get('agent_name'): 
                data["last_agent"] = meta['agent_name']
                data["last_model"] = meta.get('model_name', data["last_model"])
            else:
                meta['agent_name'] = data["last_agent"]
                meta['model_name'] = data.get("last_model", "---")

            data["tokens"] += max(1, estimate_tokens([req.get('action'), req.get('target')], req.get('content_size', 0)))
            aid = datetime.now().strftime("%H%M%S-") + str(int(time.time()*100)%100)
            
            data["running"].append({
                "id": aid, "action": req.get('action'), "target": req.get('target', ''),
                "details": req.get('details', ''), "metadata": meta, "status": "running",
                "started": datetime.now().strftime("%H:%M:%S")
            })
            save_data(data)
            return self.send_json({"success": True, "activity_id": aid, "nudge": data["nudge"]})

        # MANDATORY: /api/complete
        elif self.path == '/api/complete':
            aid = req.get('activity_id')
            result = req.get('result', '')
            for i, a in enumerate(data["running"]):
                if a["id"] == aid:
                    a.update({"status": "completed", "result": result})
                    data["history"].insert(0, a)
                    data["running"].pop(i)
                    save_data(data)
                    return self.send_json({"success": True, "activity_id": aid, "status": "completed"})
            return self.send_json({"success": False, "error": "Activity not found"}, 404)

        # TODO ENDPOINTS
        elif self.path == '/api/todos/add':
            data["todos"] = data.get("todos", [])
            data["todos"].append({
                "id": req.get('id', datetime.now().strftime("%H%M%S-" ) + str(int(time.time()*100)%100)),
                "content": req.get('content', ''),
                "status": req.get('status', 'pending'),
                "priority": req.get('priority', 'medium')
            })
            save_data(data)
            return self.send_json({"success": True})

        elif self.path == '/api/todos/update':
            data["todos"] = req.get('todos', [])
            save_data(data)
            return self.send_json({"success": True})

        elif self.path == '/api/todos/clear':
            data["todos"] = [t for t in data.get("todos", []) if t.get('status') != 'completed']
            save_data(data)
            return self.send_json({"success": True})

        # NOTES ENDPOINTS
        elif self.path == '/api/notes/add':
            existing = data.get("notes", "")
            new_note = f"[{req.get('category', 'note')}] {req.get('content', '')}"
            data["notes"] = existing + "\n" + new_note if existing else new_note
            save_data(data)
            return self.send_json({"success": True})

        # SHELL ENDPOINT
        elif self.path == '/api/shell/add':
            # Log shell command to history as a BASH activity
            aid = datetime.now().strftime("%H%M%S-") + str(int(time.time()*100)%100)
            data["history"].insert(0, {
                "id": aid,
                "action": "BASH",
                "target": req.get('command', ''),
                "details": req.get('output_preview', ''),
                "status": req.get('status', 'completed'),
                "started": datetime.now().strftime("%H:%M:%S"),
                "metadata": req.get('metadata', {})
            })
            save_data(data)
            return self.send_json({"success": True, "activity_id": aid})

        # SUMMARY ENDPOINT
        elif self.path == '/api/summary/export':
            d = load_data()
            summary = f"# ACP Session Summary\n\n"
            summary += f"Tokens: {d['tokens']}\nAgent: {d['last_agent']}\n\n"
            summary += f"## History\n"
            for a in d['history'][:10]:
                summary += f"- [{a['action']}] {a['target']}: {a.get('result', 'N/A')}\n"
            return self.send_json({"success": True, "summary": summary})

        # SYSTEM UTILS
        elif self.path == '/api/reset':
            save_data({"running":[], "history":[], "stop_flag":False, "tokens":0, "files_read":[], "nudge":None, "last_agent":"Unknown", "todos":[], "notes":"", "summary":"Session Reset."})
            return self.send_json({"success": True})

        elif self.path == '/api/shutdown':
            self.send_json({"success": True})
            os.kill(os.getpid(), signal.SIGINT); return

if __name__ == "__main__":
    print(f"ACP Minimal v1.0.3 active on {PORT}"); HTTPServer(('0.0.0.0', PORT), ACPMinimalHandler).serve_forever()