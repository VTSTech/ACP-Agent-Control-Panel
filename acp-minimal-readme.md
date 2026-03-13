# ACP Minimal

A barebones implementation of the [ACP (Agent Control Panel) Specification](https://github.com/VTSTech/ACP-Agent-Control-Panel) with a basic web UI.

**Version:** v1.0.1 | **~450 lines** of Python with no external dependencies.

## Features

- **Activity Monitoring**: Real-time activity tracking with status
- **Token Tracking**: Context window usage estimation with `content_size` support
- **STOP ALL**: Emergency stop capability  
- **Shell History**: Terminal command logging
- **TODO List**: Task tracking
- **Notes**: Context recovery notes (v1.0.1)
- **whoami**: Agent self-awareness endpoint (v1.0.1)
- **Activity Lookup**: GET /api/activity/{id} (v1.0.1)
- **Metadata Support**: priority, agent_name, custom fields (v1.0.1)
- **Basic Web UI**: Dark theme dashboard

## Quick Start

```bash
# Run with defaults (port 8766, admin/secret)
python3 acp-minimal.py

# Configure via environment
ACP_PORT=9000 ACP_USER=myuser ACP_PASS=mypass python3 acp-minimal.py
```

Open `http://localhost:8766` in your browser.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web UI dashboard |
| `/api/status` | GET | Full session status |
| `/api/whoami` | GET | **v1.0.1** Agent self-awareness |
| `/api/activity/{id}` | GET | **v1.0.1** Single activity lookup |
| `/api/action` | POST | Log activity, complete previous |
| `/api/stop` | POST | Trigger STOP ALL |
| `/api/resume` | POST | Clear stop flag |
| `/api/reset` | POST | Reset session |
| `/api/shell/add` | POST | Add shell command |
| `/api/todos/update` | POST | Update TODO list |
| `/api/notes/add` | POST | **v1.0.1** Add context note |

### Action Parameters (v1.0.1)

| Parameter | Type | Description |
|-----------|------|-------------|
| `action` | string | Action type (required) |
| `target` | string | File path, command, or resource (required) |
| `details` | string | Human-readable description |
| `content_size` | integer | Character count for accurate token tracking |
| `priority` | string | `high` \| `medium` \| `low` (default: medium) |
| `metadata` | object | Arbitrary key-value pairs (e.g., `{"agent_name": "MyAgent"}`) |

## Usage Examples

```bash
# Check status
curl -u admin:secret http://localhost:8766/api/status

# whoami - establish identity
curl -u admin:secret http://localhost:8766/api/whoami

# Log an action with v1.0.1 metadata
curl -u admin:secret -X POST http://localhost:8766/api/action \
  -H "Content-Type: application/json" \
  -d '{"action":"READ","target":"config.py","details":"Loading config","priority":"high","metadata":{"agent_name":"MyAgent"}}'

# Log with content_size for accurate token tracking
curl -u admin:secret -X POST http://localhost:8766/api/action \
  -H "Content-Type: application/json" \
  -d '{"action":"READ","target":"large_file.py","content_size":35000,"metadata":{"agent_name":"MyAgent"}}'

# Complete previous + start new in one call
curl -u admin:secret -X POST http://localhost:8766/api/action \
  -H "Content-Type: application/json" \
  -d '{
    "complete_id": "PREV_ID",
    "result": "Read 100 lines",
    "action": "EDIT",
    "target": "config.py",
    "details": "Fixing bug"
  }'

# Get single activity
curl -u admin:secret http://localhost:8766/api/activity/123456-abc123

# Add a note for context recovery
curl -u admin:secret -X POST http://localhost:8766/api/notes/add \
  -H "Content-Type: application/json" \
  -d '{"category":"decision","content":"Using PostgreSQL for scalability","importance":"high"}'

# STOP ALL
curl -u admin:secret -X POST http://localhost:8766/api/stop \
  -H "Content-Type: application/json" \
  -d '{"reason":"User requested"}'

# Add shell command
curl -u admin:secret -X POST http://localhost:8766/api/shell/add \
  -H "Content-Type: application/json" \
  -d '{"command":"npm install","status":"completed"}'

# Update TODOs
curl -u admin:secret -X POST http://localhost:8766/api/todos/update \
  -H "Content-Type: application/json" \
  -d '{"todos":[{"content":"Task 1","status":"pending"},{"content":"Task 2","status":"completed"}]}'
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ACP_PORT` | `8766` | Server port |
| `ACP_USER` | `admin` | Auth username |
| `ACP_PASS` | `secret` | Auth password |
| `ACP_DATA_FILE` | `acp_data.json` | Session storage file |
| `ACP_CONTEXT_WINDOW` | `200000` | Token limit |

## Specification

See the full ACP Specification for complete protocol details:
- [ACP-Specification.md](./ACP-Specification.md)
- [ACP-Agent-Guide.md](./ACP-Agent-Guide.md)

## License

MIT
