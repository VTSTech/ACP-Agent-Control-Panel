#!/usr/bin/env python3
"""
ACP Minimal - Barebones Agent Control Panel Implementation
Reference: https://github.com/VTSTech/ACP-Agent-Control-Panel
License: MIT

A minimal implementation of the ACP specification for AI agent monitoring.
Supports: Activity logging, STOP ALL, basic token tracking.
"""

import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════
PORT = int(os.environ.get("ACP_PORT", "8766"))
AUTH_USER = os.environ.get("ACP_USER", "admin")
AUTH_PASS = os.environ.get("ACP_PASS", "secret")
DATA_FILE = os.environ.get("ACP_DATA_FILE", "acp_data.json")
CONTEXT_WINDOW = int(os.environ.get("ACP_CONTEXT_WINDOW", "200000"))

# ═══════════════════════════════════════════════════════════════════════════════
# DATA STORAGE
# ═══════════════════════════════════════════════════════════════════════════════
def load_data():
    """Load session data from JSON file."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {"running": [], "history": [], "stop_flag": False, "stop_reason": None, "tokens": 0}

def save_data(data):
    """Save session data to JSON file."""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

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
            except:
                pass
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="ACP"')
        self.end_headers()
        return False

    def do_GET(self):
        if not self.check_auth():
            return
        
        if self.path == '/api/status':
            data = load_data()
            tokens = data.get("tokens", 0)
            self.send_json({
                "stop_flag": data["stop_flag"],
                "stop_reason": data["stop_reason"],
                "running": data["running"],
                "tokens": tokens,
                "tokens_percent": round(tokens / CONTEXT_WINDOW * 100, 1),
                "tokens_remaining": max(0, CONTEXT_WINDOW - tokens)
            })
        
        elif self.path == '/api/history':
            data = load_data()
            self.send_json({"history": data["history"][-50:]})  # Last 50
        
        elif self.path == '/' or self.path == '/api':
            self.send_json({"name": "ACP Minimal", "version": "1.0", "endpoints": ["/api/status", "/api/action", "/api/stop", "/api/resume", "/api/history"]})
        
        else:
            self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        if not self.check_auth():
            return
        
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode() if length else '{}'
        try:
            req = json.loads(body)
        except:
            self.send_json({"error": "Invalid JSON"}, 400)
            return

        if self.path == '/api/action':
            data = load_data()
            
            # Check stop flag first
            if data["stop_flag"]:
                self.send_json({"error": "Stop requested", "stop_flag": True}, 403)
                return
            
            # Complete previous activity if provided
            prev_id = req.get('complete_id')
            if prev_id:
                for i, act in enumerate(data["running"]):
                    if act["id"] == prev_id:
                        act["status"] = "completed"
                        act["result"] = req.get('result', '')[:500]
                        act["completed"] = datetime.now().isoformat()
                        data["history"].insert(0, act)
                        data["running"].pop(i)
                        break
            
            # Start new activity
            action = req.get('action', 'UNKNOWN')
            target = req.get('target', '')
            details = req.get('details', '')
            
            # Estimate tokens (simple: chars / 3.5)
            tokens = int(len(action) + len(target) + len(details)) // 3.5
            data["tokens"] = data.get("tokens", 0) + tokens
            
            import time
            act_id = datetime.now().strftime("%H%M%S-") + str(int(time.time() * 1000) % 100000)
            activity = {
                "id": act_id,
                "action": action,
                "target": target,
                "details": details,
                "status": "running",
                "started": datetime.now().isoformat()
            }
            data["running"].append(activity)
            save_data(data)
            
            self.send_json({
                "activity_id": act_id,
                "stop_flag": False,
                "tokens": data["tokens"],
                "tokens_remaining": max(0, CONTEXT_WINDOW - data["tokens"])
            })

        elif self.path == '/api/stop':
            data = load_data()
            data["stop_flag"] = True
            data["stop_reason"] = req.get('reason', 'User requested stop')
            # Cancel running activities
            for act in data["running"]:
                act["status"] = "cancelled"
                data["history"].insert(0, act)
            data["running"] = []
            save_data(data)
            self.send_json({"success": True, "message": "STOP ALL triggered"})

        elif self.path == '/api/resume':
            data = load_data()
            data["stop_flag"] = False
            data["stop_reason"] = None
            save_data(data)
            self.send_json({"success": True, "message": "Resumed"})

        elif self.path == '/api/reset':
            save_data({"running": [], "history": [], "stop_flag": False, "stop_reason": None, "tokens": 0})
            self.send_json({"success": True, "message": "Session reset"})

        else:
            self.send_json({"error": "Not found"}, 404)

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print(f"ACP Minimal starting on port {PORT}")
    print(f"Auth: {AUTH_USER}:{AUTH_PASS}")
    print(f"Endpoints: /api/status, /api/action, /api/stop, /api/resume")
    HTTPServer(('0.0.0.0', PORT), ACPHandler).serve_forever()
