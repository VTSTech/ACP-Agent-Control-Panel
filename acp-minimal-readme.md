# ACP Minimal

A barebones implementation of the [ACP (Agent Control Panel) Specification](https://github.com/VTSTech/ACP-Agent-Control-Panel).

## What is ACP?

ACP is a monitoring and observability protocol for AI agents. It provides:
- **Activity Tracking**: Real-time monitoring of agent actions
- **Token Management**: Context window usage estimation  
- **STOP ALL**: Emergency stop capability

## Quick Start

```bash
# Run with defaults
python3 acp-minimal.py

# Configure via environment
ACP_PORT=9000 ACP_USER=myuser ACP_PASS=mypass python3 acp-minimal.py
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | Check stop flag and token usage |
| `/api/action` | POST | Log activity, complete previous |
| `/api/stop` | POST | Trigger STOP ALL |
| `/api/resume` | POST | Clear stop flag |
| `/api/history` | GET | Get activity history |
| `/api/reset` | POST | Reset session |

## Usage Example

```bash
# Check status
curl -u admin:secret http://localhost:8766/api/status

# Log an action (returns activity_id)
curl -u admin:secret -X POST http://localhost:8766/api/action \
  -H "Content-Type: application/json" \
  -d '{"action": "READ", "target": "/src/main.py", "details": "Loading main"}'

# Complete and start new in one call
curl -u admin:secret -X POST http://localhost:8766/api/action \
  -H "Content-Type: application/json" \
  -d '{
    "complete_id": "PREV_ID",
    "result": "Read 100 lines",
    "action": "EDIT",
    "target": "/src/main.py",
    "details": "Fixing bug"
  }'

# Emergency stop
curl -u admin:secret -X POST http://localhost:8766/api/stop \
  -H "Content-Type: application/json" \
  -d '{"reason": "User requested"}'
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ACP_PORT` | `8766` | Server port |
| `ACP_USER` | `admin` | Auth username |
| `ACP_PASS` | `secret` | Auth password |
| `ACP_DATA_FILE` | `acp_data.json` | Session storage |
| `ACP_CONTEXT_WINDOW` | `200000` | Token limit |

## Specification

See the full ACP Specification for complete protocol details:
- [ACP-Specification.md](https://github.com/VTSTech/ACP-Agent-Control-Panel/blob/main/ACP-Specification.md)
- [ACP-Agent-Guide.md](https://github.com/VTSTech/ACP-Agent-Control-Panel/blob/main/ACP-Agent-Guide.md)

## License

MIT
