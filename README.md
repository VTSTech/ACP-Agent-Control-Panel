# ACP - Agent Control Panel

A lightweight monitoring and observability sidecar for AI agents. Provides real-time tracking of agent activities, token usage, shell commands, and task management through a web UI and REST API.

## Quick Start

```bash
# Minimal version (single file, ~400 lines)
python acp-minimal.py

# Open http://localhost:8766 (default: admin/secret)
```

## What ACP Does

ACP acts as a "dashboard" for AI agents, allowing them to:

- **Report Activities** - Log what they're doing (reading files, running commands, etc.)
- **Track Token Usage** - Monitor context window consumption
- **Shell History** - Record terminal commands executed
- **Task Management** - Sync TODO lists and track progress
- **Stop/Resume** - Allow humans to pause agent activity

## Versions

### Minimal (`acp-minimal.py`) - Reference Implementation
- **~400 lines** of pure Python (no dependencies)
- Single file, drop-in solution
- Basic web UI included
- Core API endpoints only
- Perfect for learning the protocol or simple integrations

### Full Version (`VTSTech-GLMACP.py`) - Production Ready
The full implementation includes everything in minimal plus:

| Feature | Description |
|---------|-------------|
| **File Browser** | View and browse files the agent has accessed |
| **Syntax Highlighting** | Code highlighting for 50+ languages |
| **Line Numbers** | Optional line numbers in file viewer |
| **Activity Filters** | Filter by action type, status, date range |
| **Search** | Full-text search across activities |
| **Changelog UI** | Version history and release notes |
| **CSRF Protection** | Security hardening |
| **Rate Limiting** | Prevent API abuse |
| **Better Token Estimation** | Improved token counting heuristics |
| **Configurable Context Window** | Environment variable `GLMACP_CONTEXT_WINDOW` |
| **File Token Deduplication** | Don't double-count re-read files |
| **Seamless Restarts** | SO_REUSEPORT for zero-downtime reload |
| **v1.0.1** Activity Priority | `high` \| `medium` \| `low` priority field |
| **v1.0.1** Activity Metadata | Arbitrary key-value pairs for custom context |
| **v1.0.1** Content Size | Accurate token tracking for native tools |
| **v1.0.1** Activity Lookup | GET /api/activity/{id} endpoint |
| **v1.0.1** Activity Hints | Contextual hints in /api/action response |

## API Reference

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/status` | Get current state (running, history, tokens, stop_flag) |
| POST | `/api/action` | Log an activity (start/complete workflow) |
| POST | `/api/stop` | Set stop flag, cancel running activities |
| POST | `/api/resume` | Clear stop flag |
| GET | `/api/history` | Get activity history |
| POST | `/api/reset` | Clear all session data |
| GET | `/api/activity/{id}` | **v1.0.1** Get single activity by ID |

### Extended Endpoints (Full Version)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/files` | List files accessed |
| GET | `/api/files/view` | View file content with token count |
| GET | `/api/changelog` | Get version history |
| GET | `/api/summary` | Get session summary for context recovery |
| POST | `/api/notes/add` | Add note for context recovery |

### Action Parameters (v1.0.1)

| Parameter | Type | Description |
|-----------|------|-------------|
| `action` | string | Action type (required) |
| `target` | string | File path, command, or resource (required) |
| `details` | string | Human-readable description |
| `content_size` | integer | Character count for accurate token tracking |
| `priority` | string | `high` \| `medium` \| `low` (default: medium) |
| `metadata` | object | Arbitrary key-value pairs |

### Action Types

| Action | Target Example | Details |
|--------|----------------|---------|
| `READ` | `/path/to/file.py` | File being read |
| `WRITE` | `/path/to/output.md` | File being written |
| `EXECUTE` | `npm install` | Shell command |
| `SEARCH` | `pattern` | Search operation |
| `LLM` | `claude-3-opus` | LLM interaction |
| `TODO` | `task-id-123` | TODO update |
| `WEB` | `https://example.com` | Web request |

## Integration Pattern

Agents should follow this workflow:

```
1. CHECK STATUS → GET /api/status (check stop_flag)
2. LOG ACTION   → POST /api/action (with action, target, details)
3. EXECUTE      → Do the actual work
4. COMPLETE     → POST /api/action (with complete_id, result)
```

### Example: Reading a File

```python
import requests

ACP_URL = "http://localhost:8766"
AUTH = ("admin", "secret")

# 1. Check if we should stop
status = requests.get(f"{ACP_URL}/api/status", auth=AUTH).json()
if status["stop_flag"]:
    print(f"Stop requested: {status['stop_reason']}")
    exit(1)

# 2. Log action start (v1.0.1: include content_size, priority, metadata)
resp = requests.post(f"{ACP_URL}/api/action", auth=AUTH, json={
    "action": "READ",
    "target": "/home/user/project/main.py",
    "details": "Reading source file",
    "priority": "high",
    "metadata": {"source": "user_request"}
})
activity_id = resp.json()["activity_id"]

# 3. Execute
content = open("/home/user/project/main.py").read()

# 4. Complete (v1.0.1: include content_size for accurate token tracking)
requests.post(f"{ACP_URL}/api/action", auth=AUTH, json={
    "complete_id": activity_id,
    "result": f"Read {len(content)} bytes",
    "complete_content_size": len(content),
    "complete_metadata": {"lines": content.count(chr(10))}
})
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ACP_PORT` | `8766` | Server port |
| `ACP_USER` | `admin` | HTTP Basic Auth username |
| `ACP_PASS` | `secret` | HTTP Basic Auth password |
| `ACP_DATA_FILE` | `acp_data.json` | Session storage file |
| `ACP_CONTEXT_WINDOW` | `200000` | Token limit for progress bar |
| `GLMACP_CONTEXT_WINDOW` | `200000` | (Full version) Alias for above |

## Documentation

- **[ACP-Specification.md](./ACP-Specification.md)** - Full protocol specification (v1.0.1)
- **[ACP-Agent-Guide.md](./ACP-Agent-Guide.md)** - Quick integration guide for agents (Draft 1.1)

## Screenshots

### Minimal UI
![ACP Minimal UI](https://github.com/VTSTech/ACP-Agent-Control-Panel/blob/main/acp-minimal.py)

Dark theme dashboard showing:
- Token usage with progress bar
- Running/completed activities
- Terminal command history
- TODO list sync

### Full Version
The full version adds:
- File browser with syntax highlighting
- Activity filtering and search
- Changelog viewer
- Enhanced statistics

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      AI Agent                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │ File Ops    │  │ Shell Exec  │  │ LLM Calls   │     │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘     │
│         │                │                │             │
│         └────────────────┼────────────────┘             │
│                          │                              │
│                          ▼                              │
│  ┌───────────────────────────────────────────────┐     │
│  │              ACP Client Library               │     │
│  │  log_action() | check_stop() | complete()     │     │
│  └───────────────────────┬───────────────────────┘     │
└──────────────────────────┼──────────────────────────────┘
                           │ HTTP
                           ▼
┌─────────────────────────────────────────────────────────┐
│                    ACP Server                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │ REST API    │  │ Web UI      │  │ Storage     │     │
│  └─────────────┘  └─────────────┘  └─────────────┘     │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
                    Human Operator
                    (Browser/Dashboard)
```

## Use Cases

1. **Development Agents** - Monitor what files your coding agent is touching
2. **Research Agents** - Track web searches and LLM interactions
3. **Task Automation** - See progress of long-running automation tasks
4. **Safety/Control** - Intervene when agents go off-track

## License

MIT

## Author

VTSTech
