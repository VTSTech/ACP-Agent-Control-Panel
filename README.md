# ACP - Agent Control Panel

A lightweight monitoring and observability sidecar for AI agents. Provides real-time tracking of agent activities, token usage, shell commands, and task management through a web UI and REST API.

## Quick Start

```bash
# Minimal version (single file, ~400 lines)
python acp-minimal.py

# Full version (production ready)
python VTSTech-GLMACP.py

# Open http://localhost:8766 (default: admin/secret)
```

## What ACP Does

ACP acts as a "dashboard" for AI agents, allowing them to:

- **Report Activities** - Log what they're doing (reading files, running commands, etc.)
- **Track Token Usage** - Monitor context window consumption
- **Shell History** - Record terminal commands executed
- **Task Management** - Sync TODO lists and track progress
- **Stop/Resume** - Allow humans to pause agent activity
- **Context Recovery** - Preserve session state across context compressions

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
| **Optional CSRF** | Security hardening (disabled by default) |
| **Rate Limiting** | Prevent API abuse |
| **Better Token Estimation** | Improved token counting heuristics |
| **Configurable Context Window** | Environment variable `GLMACP_CONTEXT_WINDOW` |
| **File Token Deduplication** | Don't double-count re-read files |
| **Seamless Restarts** | SO_REUSEPORT for zero-downtime reload |
| **v1.0.1** Activity Priority | `high` \| `medium` \| `low` priority field |
| **v1.0.1** Activity Metadata | Arbitrary key-value pairs with `agent_name` support |
| **v1.0.1** Content Size | Accurate token tracking for native tools |
| **v1.0.1** Activity Lookup | GET /api/activity/{id} endpoint |
| **v1.0.1** Activity Hints | Contextual hints in /api/action response |
| **v1.0.1** CHAT Action Type | Track conversational/cognitive work |
| **v1.0.1** whoami Endpoint | GET /api/whoami for agent self-awareness |
| **v1.0.2** Nudge API | Human guidance via synchronous message delivery |
| **v1.0.2** Orphan Detection | Warning when starting tasks with running activities |
| **v1.0.2** Nudge Priority | `normal` \| `high` \| `urgent` priority levels |
| **v1.0.2** TODO/Shell Metadata | `agent_name`, `tool`, `skill` attribution |
| **v1.0.2** Per-Agent Tokens | `primary_agent`, `agent_tokens{}` for context isolation |
| **v1.0.2** Context Isolation | Session tokens reflect only primary agent context |

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
| GET | `/api/whoami` | **v1.0.1** Agent self-awareness and identity hint |
| GET | `/api/csrf-token` | Get CSRF token (if enabled) |
| POST | `/api/nudge` | **v1.0.2** Send guidance to agent |
| GET | `/api/nudge` | **v1.0.2** Check pending nudge |
| POST | `/api/nudge/ack` | **v1.0.2** Acknowledge nudge |

### Extended Endpoints (Full Version)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/files` | List files accessed |
| GET | `/api/files/view` | View file content with token count |
| GET | `/api/changelog` | Get version history |
| GET | `/api/summary` | Get session summary for context recovery |
| POST | `/api/summary/export` | Export summary to markdown file |
| GET | `/api/notes` | Get all saved notes |
| POST | `/api/notes/add` | Add note for context recovery |

### Action Parameters (v1.0.1)

| Parameter | Type | Description |
|-----------|------|-------------|
| `action` | string | Action type (required) |
| `target` | string | File path, command, or resource (required) |
| `details` | string | Human-readable description |
| `content_size` | integer | Character count for accurate token tracking |
| `priority` | string | `high` \| `medium` \| `low` (default: medium) |
| `metadata` | object | Arbitrary key-value pairs (e.g., `{"agent_name": "Super Z"}`) |

### Action Types

| Action | Target Example | Details |
|--------|----------------|---------|
| `READ` | `/path/to/file.py` | File being read |
| `WRITE` | `/path/to/output.md` | File being written |
| `EDIT` | `/path/to/file.py` | File being modified |
| `BASH` | `npm install` | Shell command |
| `SEARCH` | `pattern` | Search operation |
| `SKILL` | `image-generation` | Skill invocation |
| `API` | `POST https://api.example.com` | External API call |
| `TODO` | `task-id-123` | TODO update |
| `CHAT` | `discussion topic` | **v1.0.1** Conversational/cognitive work |

## Integration Pattern

Agents should follow this workflow:

```
0. SESSION START (recommended)
   GET /api/whoami  → Establish identity (use agent_name in metadata)
   GET /api/todos   → Restore TODO state

1. CHECK STATUS → GET /api/status (check stop_flag)
2. LOG ACTION   → POST /api/action (with action, target, details, metadata)
3. EXECUTE      → Do the actual work
4. COMPLETE     → POST /api/action (with complete_id, result)
```

### Example: Reading a File

```python
import requests

ACP_URL = "http://localhost:8766"
AUTH = ("admin", "secret")

# 0. Session start - establish identity
whoami = requests.get(f"{ACP_URL}/api/whoami", auth=AUTH).json()
agent_name = "MyAgent"  # Use this in all activity metadata

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
    "metadata": {"agent_name": agent_name, "source": "user_request"}
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
| `GLMACP_PORT` | `8766` | Server port |
| `GLMACP_USER` | `admin` | HTTP Basic Auth username |
| `GLMACP_PASS` | `secret` | HTTP Basic Auth password |
| `GLMACP_CSRF_ENABLED` | `false` | Enable CSRF protection (recommended for production) |
| `GLMACP_CONTEXT_WINDOW` | `200000` | Token limit for progress bar |
| `GLMACP_SESSION_TIMEOUT` | `86400` | Session timeout in seconds |
| `GLMACP_MAX_UPLOAD_SIZE` | `104857600` | Max upload size (100MB) |

## Documentation

- **[ACP-Specification.md](./ACP-Specification.md)** - Full protocol specification (v1.0.2)
- **[ACP-Agent-Guide-MIN.md](./ACP-Agent-Guide-MIN.md)** - Quick reference for AI agents (v1.0.2)
- **[ACP-Agent-Guide-MAX.md](./ACP-Agent-Guide-MAX.md)** - Complete integration guide with examples (v1.0.2)

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
