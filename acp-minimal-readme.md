# ACP Minimal

A barebones implementation of the [ACP (Agent Control Panel) Specification](https://github.com/VTSTech/ACP-Agent-Control-Panel) with a basic web UI.

**Version:** v1.0.5 | **~1000 lines** of Python with no external dependencies.

## Features

### Core (v1.0.0)
- **Activity Monitoring**: Real-time activity tracking with status
- **Token Tracking**: Context window usage estimation with `content_size` support
- **STOP ALL**: Emergency stop capability
- **Shell History**: Terminal command logging
- **TODO List**: Task tracking

### v1.0.1
- **Notes**: Context recovery notes
- **whoami**: Agent self-awareness endpoint
- **Activity Lookup**: GET /api/activity/{id}
- **Metadata Support**: priority, agent_name, custom fields

### v1.0.2
- **Nudge API**: Human-to-agent guidance (GET/POST /api/nudge)
- **Orphan Detection**: Warning for stalled activities
- **Duration Statistics**: Activity timing analysis

### v1.0.3
- **model_name Field**: Separate agent identity from model identifier
- **Session Management**: Timeout tracking, refresh endpoints
- **Context Recovery**: Summary export to markdown

### v1.0.4 (A2A Protocol)
- **Agent Registry**: Register/unregister agents with capabilities
- **A2A Messaging**: Inter-agent communication via message queue
- **JSON-RPC 2.0**: Protocol adapter for A2A compliance
- **Agent Card**: Discovery endpoint at `/.well-known/agent-card.json`
- **A2A Hints**: Notification of pending messages in activity response

### v1.0.5 (Primary Agent)
- **primary_agent in /api/whoami**: Check if you own the context
- **Nudge Delivery**: Nudges delivered only to primary agent
- **Context Isolation**: Secondary agents receive `nudge: null`

## Quick Start

```bash
# Run with defaults (port 8766, admin/secret)
python3 acp-minimal.py

# Configure via environment
ACP_PORT=9000 ACP_USER=myuser ACP_PASS=mypass python3 acp-minimal.py
```

Open `http://localhost:8766` in your browser.

## API Endpoints

### Core Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web UI dashboard |
| `/api/status` | GET | Full session status |
| `/api/whoami` | GET | Agent self-awareness |
| `/api/activity/{id}` | GET | Single activity lookup |
| `/api/action` | POST | Log activity, complete previous |
| `/api/complete` | POST | Complete running activity |
| `/api/stop` | POST | Trigger STOP ALL |
| `/api/resume` | POST | Clear stop flag |
| `/api/reset` | POST | Reset session |

### TODO & Notes

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/todos` | GET | List TODOs |
| `/api/todos/update` | POST | Update TODO list |
| `/api/todos/toggle` | POST | Toggle TODO status |
| `/api/notes` | GET | List notes |
| `/api/notes/add` | POST | Add context note |

### Shell & Summary

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/shell` | GET | Shell command history |
| `/api/shell/add` | POST | Add shell command |
| `/api/summary` | GET | Structured session summary |
| `/api/summary/export` | POST | Export to markdown file |

### Agent Registry (v1.0.4)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/agents` | GET | List registered agents |
| `/api/agents/{name}` | GET | Get specific agent |
| `/api/agents/register` | POST | Register agent |
| `/api/agents/unregister` | POST | Unregister agent |

### A2A Messaging (v1.0.4)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/a2a/send` | POST | Send message to agent |
| `/api/a2a/history` | GET | Message history |

### JSON-RPC 2.0 (v1.0.4)

| Endpoint | Methods |
|----------|---------|
| `/jsonrpc` | `GetAgents`, `RegisterAgent`, `SendMessage`, `GetTask`, `CancelTask`, `activity/start`, `activity/complete`, `todos/update`, `stop/set`, `session/reset` |
| `/.well-known/agent-card.json` | A2A discovery endpoint |

## Action Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `action` | string | Action type (required) |
| `target` | string | File path, command, or resource (required) |
| `details` | string | Human-readable description |
| `content_size` | integer | Character count for accurate token tracking |
| `priority` | string | `high` \| `medium` \| `low` (default: medium) |
| `metadata` | object | Arbitrary key-value pairs |

### Standard Metadata Fields

| Field | Description |
|-------|-------------|
| `agent_name` | Agent identifier (e.g., "Super Z", "Claude") |
| `model_name` | Model identifier (e.g., "claude-sonnet", "gpt-4") |
| `source` | Action origin (e.g., "user_request", "subagent") |

## Usage Examples

```bash
# Check status
curl -u admin:secret http://localhost:8766/api/status

# whoami - establish identity
curl -u admin:secret http://localhost:8766/api/whoami

# Register agent (v1.0.4)
curl -u admin:secret -X POST http://localhost:8766/api/agents/register \
  -H "Content-Type: application/json" \
  -d '{"agent_name":"Super Z","model_name":"claude-sonnet","capabilities":["code","research"]}'

# Log an action with metadata
curl -u admin:secret -X POST http://localhost:8766/api/action \
  -H "Content-Type: application/json" \
  -d '{"action":"READ","target":"config.py","details":"Loading config","priority":"high","metadata":{"agent_name":"Super Z","model_name":"claude-sonnet"}}'

# Complete activity
curl -u admin:secret -X POST http://localhost:8766/api/complete \
  -H "Content-Type: application/json" \
  -d '{"activity_id":"123456-78","result":"Read 100 lines"}'

# Send A2A message (v1.0.4)
curl -u admin:secret -X POST http://localhost:8766/api/a2a/send \
  -H "Content-Type: application/json" \
  -d '{"from_agent":"Super Z","to_agent":"ResearchAgent","type":"request","action":"search","payload":{"query":"ACP protocol"}}'

# JSON-RPC call (v1.0.4)
curl -u admin:secret -X POST http://localhost:8766/jsonrpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"GetAgents","params":{},"id":1}'

# Get agent card (v1.0.4)
curl -u admin:secret http://localhost:8766/.well-known/agent-card.json

# STOP ALL
curl -u admin:secret -X POST http://localhost:8766/api/stop \
  -H "Content-Type: application/json" \
  -d '{"reason":"User requested"}'

# Update TODOs
curl -u admin:secret -X POST http://localhost:8766/api/todos/update \
  -H "Content-Type: application/json" \
  -d '{"todos":[{"id":"1","content":"Task 1","status":"pending","priority":"high"}]}'

# Export session summary
curl -u admin:secret -X POST http://localhost:8766/api/summary/export
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ACP_PORT` | `8766` | Server port |
| `ACP_USER` | `admin` | Auth username |
| `ACP_PASS` | `secret` | Auth password |
| `ACP_DATA_FILE` | `acp_data.json` | Session storage file |
| `ACP_CONTEXT_WINDOW` | `200000` | Token limit |
| `ACP_SESSION_TIMEOUT` | `86400` | Session timeout (seconds) |
| `ACP_ORPHAN_TIMEOUT` | `300` | Orphan detection threshold (seconds) |

## Specification

See the full ACP Specification for complete protocol details:
- [ACP-Specification.md](./ACP-Specification.md) - Full API specification
- [ACP-Agent-Guide-MIN.md](./ACP-Agent-Guide-MIN.md) - Quick reference
- [ACP-Agent-Guide-MAX.md](./ACP-Agent-Guide-MAX.md) - Complete guide

## License

MIT