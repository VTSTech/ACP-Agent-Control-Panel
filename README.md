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
| **v1.0.3** Per-Agent Tokens | `primary_agent`, `agent_tokens{}` for context isolation |
| **v1.0.3** Context Isolation | Session tokens reflect only primary agent context |
| **v1.0.3** File Deduplication | READ skips tokens for already-read files |
| **v1.0.3** Duration Statistics | GET /api/stats/duration for performance analysis |
| **v1.0.3** Batch Operations | POST /api/activity/batch for bulk activities |
| **v1.0.3** Cloudflared Tunnel | Built-in tunnel support via `GLMACP_TUNNEL=auto` |
| **v1.0.4** Agent Registry | Register agents, track online status, capabilities |
| **v1.0.4** A2A Messaging | Inter-agent communication via message queue |
| **v1.0.4** A2A Hints | Notification of pending messages in activity response |
| **v1.0.4** JSON-RPC 2.0 | A2A protocol compliance via `/jsonrpc`, `/a2a` endpoints |
| **v1.0.4** Agent Card | `/.well-known/agent-card.json` for A2A discovery |


## API Reference

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/status` | Get current state (running, history, tokens, stop_flag) |
| GET | `/api/all` | Combined status + running + history in one call |
| POST | `/api/action` | Combined log/complete workflow (recommended) |
| POST | `/api/start` | Start a new activity |
| POST | `/api/complete` | Complete an activity |
| POST | `/api/stop` | Set stop flag, cancel running activities |
| POST | `/api/resume` | Clear stop flag |
| POST | `/api/shutdown` | **v1.0.2** Gracefully end session with summary export |
| GET | `/api/running` | List currently running activities |
| GET | `/api/history` | Get activity history |
| GET | `/api/activity/{id}` | **v1.0.1** Get single activity by ID |
| GET | `/api/whoami` | **v1.0.1** Agent self-awareness and identity hint |
| GET | `/api/csrf-token` | Get CSRF token (if enabled) |
| POST | `/api/clear_history` | Clear activity history |
| POST | `/api/reset_session` | Reset session tokens to startup value |
| POST | `/api/reset` | **v1.0.4** Full session reset including agents and A2A messages |
| POST | `/api/nudge` | **v1.0.2** Send guidance to agent |
| GET | `/api/nudge` | **v1.0.2** Check pending nudge |
| POST | `/api/nudge/ack` | **v1.0.2** Acknowledge nudge |
| GET | `/api/stats/duration` | **v1.0.3** Activity duration statistics |
| POST | `/api/activity/batch` | **v1.0.3** Batch activity operations |
| GET | `/api/agents` | **v1.0.4** List all registered agents |
| GET | `/api/agents/{name}` | **v1.0.4** Get specific agent details |
| POST | `/api/agents/register` | **v1.0.4** Register agent with capabilities |
| POST | `/api/agents/unregister` | **v1.0.4** Unregister an agent |
| POST | `/api/a2a/send` | **v1.0.4** Send message to another agent |
| GET | `/api/a2a/history` | **v1.0.4** Get A2A message history |
| GET | `/.well-known/agent-card.json` | **v1.0.4** A2A Agent Card discovery |
| POST | `/jsonrpc` `/a2a` `/api/jsonrpc` | **v1.0.4** JSON-RPC 2.0 endpoint |

### Extended Endpoints (Full Version)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/files/list` | List directory contents |
| GET | `/api/files/view` | View file content with token count |
| GET | `/api/files/download` | Download file (binary safe) |
| POST | `/api/files/upload` | Upload file |
| POST | `/api/files/save` | Save edited file |
| POST | `/api/files/delete` | Delete file or directory |
| POST | `/api/files/mkdir` | Create directory |
| POST | `/api/files/extract` | Extract archive |
| POST | `/api/files/compress` | Create zip archive |
| GET | `/api/system` | CPU, RAM, disk statistics |
| GET | `/api/session` | Session info and timeout |
| POST | `/api/session/refresh` | Extend session timeout |
| POST | `/api/restart` | Restart the ACP server |
| GET | `/api/summary` | Get session summary for context recovery |
| GET | `/api/summary/export` | Export summary to persistent markdown file |
| GET | `/api/notes` | Get all saved notes |
| POST | `/api/notes/add` | Add note for context recovery |
| POST | `/api/notes/clear` | Clear all AI notes |
| GET | `/api/todos` | Get current TODO list |
| POST | `/api/todos/update` | Replace entire TODO list |
| POST | `/api/todos/add` | Add single TODO item |
| POST | `/api/todos/clear` | Clear completed TODOs |
| GET | `/api/shell` | Get shell command history |
| POST | `/api/shell/add` | Add shell command to history |
| POST | `/api/shell/clear` | Clear shell history |

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
| `A2A` | `AgentA → AgentB` | **v1.0.4** Agent-to-agent communication |

## Integration Pattern

Agents should follow this workflow:

```
0. SESSION START (mandatory)
   GET /api/whoami              → Establish identity (use agent_name in metadata)
   POST /api/agents/register   → Register with Agent Registry (v1.0.4)
   GET /api/todos               → Restore TODO state
   POST /api/action             → Log bootstrap activity (CHAT, "Session bootstrap")

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

# Register with agent registry (v1.0.4)
requests.post(f"{ACP_URL}/api/agents/register", auth=AUTH, json={
    "agent_name": agent_name,
    "capabilities": ["file-reading", "code-analysis"]
})

# 1. Check if we should stop
status = requests.get(f"{ACP_URL}/api/status", auth=AUTH).json()
if status["stop_flag"]:
    print(f"Stop requested: {status['stop_reason']}")
    exit(1)

# 2. Log action start (include content_size, priority, metadata)
resp = requests.post(f"{ACP_URL}/api/action", auth=AUTH, json={
    "action": "READ",
    "target": "/home/user/project/main.py",
    "details": "Reading source file",
    "priority": "high",
    "metadata": {"agent_name": agent_name, "source": "user_request"}
})
activity_id = resp.json()["activity_id"]

# Check A2A hints for pending messages (v1.0.4)
hints = resp.json().get("hints", {})
if hints.get("a2a", {}).get("pending_count", 0) > 0:
    messages = requests.get(f"{ACP_URL}/api/a2a/history?to={agent_name}", auth=AUTH).json()
    # process messages...

# 3. Execute
content = open("/home/user/project/main.py").read()

# 4. Complete (include content_size for accurate token tracking)
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
| `GLMACP_DATA_FILE` | `./agent_activity.json` | Session state storage file path |
| `GLMACP_FILES_DIR` | *(script parent)* | Base directory for file manager |
| `GLMACP_SUMMARY_FILE` | `./acp_session_summary.md` | Context recovery summary file path |
| `GLMACP_QUIET` | `false` | Suppress server log output |
| `GLMACP_CSRF_ENABLED` | `false` | Enable CSRF protection (recommended for production) |
| `GLMACP_CONTEXT_WINDOW` | `200000` | Token limit for progress bar |
| `GLMACP_STARTUP_TOKENS` | `3000` | Initial token overhead estimate |
| `GLMACP_SESSION_TIMEOUT` | `86400` | Session timeout in seconds |
| `GLMACP_MAX_UPLOAD_SIZE` | `104857600` | Max upload size (100MB) |
| `GLMACP_MAX_FILE_VIEW_SIZE` | `10485760` | Max file view size (10MB) |
| `GLMACP_TUNNEL` | `false` | **v1.0.3** Auto-start cloudflared tunnel (`auto`, `true`, `yes`) |
| `GLMACP_TUNNEL_URL` | *(none)* | **v1.0.3** Reuse an existing tunnel URL |

## Documentation

- **[ACP-Specification.md](./ACP-Specification.md)** - Full protocol specification (v1.0.4)
- **[ACP-Agent-Guide-MIN.md](./ACP-Agent-Guide-MIN.md)** - Quick reference for AI agents (v1.0.4)
- **[ACP-Agent-Guide-MAX.md](./ACP-Agent-Guide-MAX.md)** - Complete integration guide with examples (v1.0.4)

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
                           │ HTTP REST / JSON-RPC 2.0
                           ▼
┌─────────────────────────────────────────────────────────┐
│                    ACP Server                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │ REST API    │  │ Web UI      │  │ Storage     │     │
│  └─────────────┘  └─────────────┘  └─────────────┘     │
│  ┌─────────────┐  ┌─────────────┐                       │
│  │ A2A/JSON-   │  │ Agent       │  (v1.0.4)             │
│  │ RPC Layer   │  │ Registry    │                       │
│  └─────────────┘  └─────────────┘                       │
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
5. **Multi-Agent Systems** - Coordinate and observe multiple agents sharing one session

## License

MIT

## Author

VTSTech