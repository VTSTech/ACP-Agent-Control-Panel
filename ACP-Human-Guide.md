# ACP Human Guide

**Setting up ACP (Agent Control Panel) for AI Agent Monitoring**

This guide covers how to set up and run ACP so your AI agent can connect to it.

---

## Quick Start

### Option 1: acp-minimal (Recommended)

```bash
# Download
git clone https://github.com/VTSTech/ACP-Agent-Control-Panel
cd ACP-Agent-Control-Panel

# Run with defaults (port 8766, admin/secret)
python3 acp-minimal.py

# Or configure
ACP_PORT=9000 ACP_USER=myuser ACP_PASS=mypass python3 acp-minimal.py
```

### Option 2: GLMACP (Full Featured)

```bash
# Download
# Get VTSTech-GLMACP.py from your source

# Run with tunnel
GLMACP_TUNNEL=auto python3 VTSTech-GLMACP.py

# Or without tunnel
python3 VTSTech-GLMACP.py
```

---

## Tunnel Setup (Remote Access)

For remote AI agents to connect, you need a tunnel.

### Cloudflare Tunnel (Recommended)

```bash
# Install cloudflared
# macOS
brew install cloudflare/cloudflare/cloudflared

# Linux
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O cloudflared
chmod +x cloudflared
sudo mv cloudflared /usr/local/bin/

# Run tunnel
cloudflared tunnel --url http://localhost:8766
```

Output will show:
```
Your quick Tunnel has been created! Visit it at:
https://xxx-yyy-zzz.trycloudflare.com
```

This URL is your `ACP_URL` - give it to your AI agent.

### GLMACP Built-in Tunnel

GLMACP can start the tunnel automatically:

```bash
GLMACP_TUNNEL=auto python3 VTSTech-GLMACP.py
```

The tunnel URL will be printed on startup and available via `GET /api/status`.

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ACP_PORT` / `GLMACP_PORT` | `8766` | Server port |
| `ACP_USER` / `GLMACP_USER` | `admin` | Auth username |
| `ACP_PASS` / `GLMACP_PASS` | `secret` | Auth password |
| `ACP_CONTEXT_WINDOW` / `GLMACP_CONTEXT_WINDOW` | `200000` | Token limit |
| `GLMACP_CSRF_ENABLED` | `false` | Enable CSRF protection |
| `GLMACP_TUNNEL` | `false` | Auto-start tunnel (`auto` or `true`) |
| `GLMACP_STARTUP_TOKENS` | `3000` | Initial token overhead estimate |
| `GLMACP_SESSION_TIMEOUT` | `86400` | Session timeout in seconds |

### acp-minimal

```bash
ACP_PORT=9000 \
ACP_USER=myuser \
ACP_PASS=mypass \
ACP_CONTEXT_WINDOW=128000 \
python3 acp-minimal.py
```

### GLMACP

```bash
GLMACP_PORT=8766 \
GLMACP_USER=admin \
GLMACP_PASS=secret \
GLMACP_TUNNEL=auto \
python3 VTSTech-GLMACP.py
```

---

## Providing ACP_URL to Your Agent

Tell your agent:

```
ACP_URL=https://xxx.trycloudflare.com
ACP_USER=admin
ACP_PASS=secret
```

The agent will bootstrap automatically:
1. `GET {ACP_URL}/api/status` — check connection and stop_flag
2. `GET {ACP_URL}/api/whoami` — establish identity
3. `POST {ACP_URL}/api/agents/register` — register in agent registry
4. `GET {ACP_URL}/api/todos` — restore task state
5. Log bootstrap CHAT activity and complete it
6. Begin logging all work actions via the ACP workflow

---

## Web UI

Open the ACP URL in your browser (with auth):

```
https://admin:secret@xxx.trycloudflare.com/
```

Features:
- Real-time activity monitoring
- Token usage tracking
- STOP ALL button
- TODO list (with toggle support v1.0.6)
- Shell command history
- Agent registry (v1.0.4)
- A2A message history (v1.0.4)
- Nudge delivery to primary agent (v1.0.5)

---

## Security Notes

1. **Change default credentials** — `admin:secret` is default
2. **Use HTTPS** — Tunnel provides this automatically
3. **Don't expose without auth** — ACP has Basic Auth enabled by default
4. **Tunnel URLs are public** — Anyone with URL can access (with auth)
5. **Enable CSRF for production** — Set `GLMACP_CSRF_ENABLED=true` for networks exposed to untrusted clients

---

## Troubleshooting

### Connection Refused

```
curl: (7) Failed to connect to localhost port 8766
```

ACP not running. Start it with `python3 acp-minimal.py`.

### Tunnel Not Working

```bash
# Check cloudflared installed
which cloudflared

# Run manually
cloudflared tunnel --url http://localhost:8766
```

### Agent Can't Connect

1. Verify ACP is running: `curl -u admin:secret http://localhost:8766/api/status`
2. Verify tunnel URL works: `curl -u admin:secret https://xxx.trycloudflare.com/api/status`
3. Give agent the correct `ACP_URL`, `ACP_USER`, `ACP_PASS`

### CSRF Errors (403)

If CSRF is enabled, agents must fetch and include the CSRF token in POST request headers:
```
X-CSRF-Token: <timestamp>:<signature>
```
Check status: `GET {ACP_URL}/api/csrf-token`

---

## Features by Version

| Version | Features |
|---------|----------|
| 1.0.0 | Activity tracking, token estimation, STOP ALL |
| 1.0.1 | Notes, whoami, activity lookup, metadata, priority, content_size |
| 1.0.2 | Nudge API, orphan detection, shutdown, shell metadata |
| 1.0.3 | model_name field, file dedup, duration stats, batch ops, tunnel |
| 1.0.4 | Agent Registry, A2A Messaging, JSON-RPC 2.0, Agent Card |
| 1.0.5 | Primary agent in whoami, nudge delivery isolation |
| 1.0.6 | TODO toggle, nudge polling endpoint, CORS support |

---

## Files

| File | Purpose |
|------|---------|
| `acp-minimal.py` | Minimal ACP server (~400 lines, no dependencies) |
| `VTSTech-GLMACP.py` | Full-featured ACP server (~5000 lines) |
| `skills/acp/SKILL.md` | Agent-facing skill file (canonical reference, v1.0.6) |
| `acp_data.json` | Session state (auto-created) |
| `acp_session_summary.md` | Context recovery export |

---

## More Information

- [`skills/acp/SKILL.md`](https://github.com/VTSTech/ACP-Agent-Control-Panel/blob/main/skills/acp/SKILL.md) — Agent skill file (v1.0.6, canonical)
- [`ACP-Specification.md`](https://github.com/VTSTech/ACP-Agent-Control-Panel/blob/main/ACP-Specification.md) — Full API spec
- [`OpenAPI.yaml`](https://github.com/VTSTech/ACP-Agent-Control-Panel/blob/main/OpenAPI.yaml) — OpenAPI 3.0 spec
- [`acp-minimal-readme.md`](https://github.com/VTSTech/ACP-Agent-Control-Panel/blob/main/acp-minimal-readme.md) — Minimal server docs

---

*ACP Human Guide v1.0.6*