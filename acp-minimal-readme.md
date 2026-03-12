# ACP Minimal

A barebones implementation of the [ACP (Agent Control Panel) Specification](https://github.com/VTSTech/ACP-Agent-Control-Panel) with a basic web UI.

## Features

- **Activity Monitoring**: Real-time activity tracking with status
- **Token Tracking**: Context window usage estimation
- **STOP ALL**: Emergency stop capability  
- **Shell History**: Terminal command logging
- **TODO List**: Task tracking
- **Basic Web UI**: Dark theme dashboard

**~400 lines** of Python with no external dependencies.

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
| `/api/action` | POST | Log activity, complete previous |
| `/api/stop` | POST | Trigger STOP ALL |
| `/api/resume` | POST | Clear stop flag |
| `/api/reset` | POST | Reset session |
| `/api/shell/add` | POST | Add shell command |
| `/api/todos/update` | POST | Update TODO list |

## Usage Examples

```bash
# Check status
curl -u admin:secret http://localhost:8766/api/status

# Log an action
curl -u admin:secret -X POST http://localhost:8766/api/action \
  -H "Content-Type: application/json" \
  -d '{"action":"READ","target":"config.py","details":"Loading config"}'

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
