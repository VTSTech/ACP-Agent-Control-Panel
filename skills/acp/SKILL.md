---
name: acp
description: "ACP Agent Control Panel - CRITICAL: Invoke this skill FIRST on every session start, context resume, or context reset. Required before any other work. Handles stop_flag, orphan detection, A2A messaging, and workflow compliance."
argument-hint: "No arguments needed - just invoke to bootstrap ACP workflow"
---

# ACP Agent Control Panel

**Version:** 1.0.4 | Single-file skill consolidating bootstrap and protocol reference.
**A2A Compliance:** JSON-RPC 2.0, Agent Card, contextId support
**ACP_URL** | Ask Human for this, use instead of http://localhost:8766/
---

## BOOTSTRAP SEQUENCE (MANDATORY)

**CRITICAL REQUIREMENT (1.0.4):** Any agent interacting with ACP MUST send a bootstrap as their FIRST message. No exceptions.

| Scenario | Bootstrap Required |
|----------|-------------------|
| Session start | [✅] MANDATORY |
| Context resume | [✅] MANDATORY |
| Context reset | [✅] MANDATORY |
| New agent joining session | [✅] MANDATORY |
| Subagent spawn | [✅] MANDATORY |
| LocalClaw connecting | [✅] MANDATORY |

**Bootstrap is NOT optional.** An agent that skips bootstrap:
- Will not have their token usage tracked correctly
- Will not appear in `agent_tokens{}`
- Will not be registered in the Agent Registry
- May interfere with primary agent tracking
- Will not receive A2A message notifications
- Is in violation of ACP protocol

Execute these steps IN ORDER before any other actions:

### 1. Check ACP Server Status

```bash
curl -s -u admin:secret http://localhost:8766/api/status
```

**If connection refused:** ACP not active. Proceed normally without ACP.

**If running, check response:**

| Field | Action |
|-------|--------|
| `stop_flag: true` | **STOP IMMEDIATELY**. Inform user. Wait for resume. |
| `running_count > 0` | Check for orphaned activities |
| `orphan_warning` | Complete orphan tasks before new work |
| `tunnel_url` | Note tunnel URL for remote access |

### 2. Establish Agent Identity

```bash
curl -s -u admin:secret http://localhost:8766/api/whoami
```

**Response:**
```json
{
  "identity": {
    "hint": "You are an AI agent. Identify yourself by name.",
    "suggestion": "Use the 'agent_name' field in activity metadata to attribute your actions.",
    "example": {"metadata": {"agent_name": "Super Z", "source": "user_request"}}
  },
  "session": {...}
}
```

Use the `agent_name` from this point forward in all activity metadata.

### 3. Register with Agent Registry (1.0.4)

**NEW:** Register your agent with capabilities for A2A discovery:

```bash
curl -s -u admin:secret -X POST http://localhost:8766/api/agents/register \
  -H "Content-Type: application/json" \
  -d '{"agent_name": "Super Z", "capabilities": ["code-generation", "file-editing", "web-development"], "model_name": "gpt-4o"}'
```

**For secondary agents (LocalClaw, subagents):**
```bash
curl -s -u admin:secret -X POST http://localhost:8766/api/agents/register \
  -H "Content-Type: application/json" \
  -d '{"agent_name": "LocalClaw", "capabilities": ["code-analysis", "file-reading"], "model_name": "qwen2.5-coder:0.5b", "endpoint": "http://localhost:8080"}'
```

### 4. Log Bootstrap Activity (MANDATORY)

**CRITICAL:** Every agent MUST log a bootstrap activity as their FIRST message to ACP. This is NOT optional.

**Primary agents** claim ownership of the main context window:
```bash
curl -s -u admin:secret -X POST http://localhost:8766/api/action \
  -H "Content-Type: application/json" \
  -d '{"action": "CHAT", "target": "Session bootstrap", "details": "Establishing primary agent identity", "metadata": {"agent_name": "Super Z", "source": "bootstrap"}}'
```

**Secondary agents** (LocalClaw, subagents) also MUST bootstrap:
```bash
curl -s -u admin:secret -X POST http://localhost:8766/api/action \
  -H "Content-Type: application/json" \
  -d '{"action": "CHAT", "target": "Session bootstrap", "details": "Connecting to active session", "metadata": {"agent_name": "LocalClaw", "model_name": "qwen2.5-coder:0.5b", "source": "bootstrap"}}'
```

**Why this matters:** The first agent to log an activity becomes the "primary agent" and owns the main context window (`session_tokens`). Other agents (subagents, LocalClaw, etc.) are tracked separately in `agent_tokens{}`.

**Verify primary agent status:**
```bash
curl -s -u admin:secret http://localhost:8766/api/status
# Check: primary_agent should be set to your agent_name
```

### 5. Handle STOP ALL

If `stop_flag: true`:

```
STOP IMMEDIATELY. Do not:
- Start new activities
- Spawn subagents
- Execute any tools except ACP API calls

Inform user: "STOP ALL is active. Waiting for resume."
Wait for user to clear stop_flag or give explicit resume instruction.
```

### 6. Complete Orphaned Activities

If `orphan_warning` present:

```bash
GET /api/all
POST /api/complete {"activity_id": "orphan_id", "result": "Completed after context recovery"}
```

### 7. Restore Session State

```bash
GET /api/todos    # Restore TODO list
GET /api/notes    # Recover saved notes
GET /api/agents   # See registered agents (1.0.4)
```

### 8. Check for A2A Messages (1.0.4)

If `hints.a2a.pending_count > 0` in response:

```bash
GET /api/a2a/history?to=<your_agent_name>
```

---

## THE ACP PATTERN (MEMORIZE)

```
LOG → EXECUTE → COMPLETE
/api/action → Tool → /api/complete
BEFORE → NOW → AFTER
```

**NEVER execute before logging.**

---

## EVERY ACTION

**Before Read/Write/Edit/Bash/Grep/Glob/LS:**

```bash
POST /api/action {"action": "READ|WRITE|EDIT|BASH|SEARCH", "target": "...", "details": "...", "metadata": {"agent_name": "Super Z"}}
→ {activity_id, stop_flag, session_tokens, hints?, nudge?, orphan_warning?}
```

**After execution:**

```bash
POST /api/complete {"activity_id": "...", "result": "..."}
```

**Combined (recommended):**

```bash
POST /api/action {"complete_id": "prev_id", "result": "prev result", "action": "READ", "target": "file.py", "metadata": {"agent_name": "Super Z"}}
```

---

## ACTION TYPES

| Type | Use For |
|------|---------|
| READ | Files, API GETs, viewing content |
| WRITE | Creating new files |
| EDIT | Modifying existing files |
| BASH | Terminal commands |
| SKILL | VLM, TTS, image-generation |
| API | External API calls |
| SEARCH | Web search, grep, find |
| TODO | TODO state changes |
| CHAT | Conversational Q&A, planning, reasoning |
| A2A | **1.0.4** Agent-to-agent communication |

### CHAT Action Type (v1.0.1)

Use CHAT for conversational and cognitive work that doesn't involve tool execution:

**When to use:**
- Q&A exchanges
- Reasoning and analysis discussions
- Planning sessions
- Knowledge transfer
- Specification review
- Decision discussions

**Example:**
```bash
POST /api/action {
  "action": "CHAT",
  "target": "Architecture review discussion",
  "details": "Discussed microservices vs monolith trade-offs",
  "metadata": {"agent_name": "Super Z"}
}
```

**Why it matters:** Pure conversational exchanges consume context window tokens but were previously untracked. CHAT ensures accurate token accounting for all agent activity.

### A2A Action Type (1.0.4)

Automatically logged when using `/api/a2a/send`. Captures inter-agent communication:

```json
{
  "id": "143052-abc123",
  "action": "A2A",
  "target": "Super Z → LocalClaw",
  "details": "request: analyze_file",
  "status": "completed"
}
```

---

## ACTIVITY HINTS (v1.0.1)

The `hints` field in `/api/action` responses provides contextual information:

```json
{
  "hints": {
    "modified_this_session": true,
    "modification_count": 3,
    "last_action": "EDIT",
    "recent_errors": 0,
    "last_error": null,
    "related_todos": [{"id": "1", "content": "Fix bug", "status": "pending"}],
    "loop_detected": false,
    "loop_count": 0,
    "suggestion": null,
    "active_todos": 2,
    "a2a": {
      "pending_count": 2,
      "senders": ["LocalClaw"],
      "preview": {"from": "LocalClaw", "action": "analysis_done", "msg_id": "..."}
    }
  }
}
```

| Hint Field | Type | Description |
|------------|------|-------------|
| `modified_this_session` | boolean | Target was already modified this session |
| `modification_count` | integer | Number of times target was accessed |
| `last_action` | string | Last action type on this target |
| `recent_errors` | integer | Count of recent errors on this target |
| `last_error` | string | Most recent error message |
| `related_todos` | array | TODOs mentioning this target |
| `loop_detected` | boolean | Same target+action repeated 3+ times |
| `loop_count` | integer | Number of repetitions if loop detected |
| `suggestion` | string | Actionable advice when patterns detected |
| `active_todos` | integer | Count of in-progress TODOs |
| `a2a` | object | **1.0.4** A2A hints for pending messages |

**Loop Detection:** If `loop_detected: true`, consider:
- Changing your approach
- Asking user for clarification
- Checking `suggestion` field for guidance

---

## A2A HINTS (1.0.4)

When you include `agent_name` in activity metadata, A2A hints notify you of pending messages:

```json
{
  "hints": {
    "a2a": {
      "pending_count": 3,
      "senders": ["LocalClaw", "DataProcessor"],
      "preview": {
        "from": "LocalClaw",
        "action": "file_analysis_complete",
        "msg_id": "143000-xyz789"
      }
    }
  }
}
```

**A2A Hint Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `pending_count` | integer | Number of unread messages for this agent |
| `senders` | array | Unique list of sender agent names |
| `preview` | object | Preview of most recent message |

**Agent workflow for A2A hints:**
```
1. Check hints.a2a in response
2. If pending_count > 0:
   a. GET /api/a2a/history?to=<my_agent_name>
   b. Process each message based on type and action
   c. Send response if needed via POST /api/a2a/send
3. Continue with task
```

---

## A2A AGENT REGISTRY (1.0.4)

### List Registered Agents

```bash
GET /api/agents
→ {
  "success": true,
  "agents": [
    {
      "name": "Super Z",
      "capabilities": ["code-generation", "file-editing"],
      "model_name": "gpt-4o",
      "status": "online",
      "online": true,
      "tokens_used": 42000
    }
  ],
  "count": 1,
  "primary_agent": "Super Z"
}
```

### Get Specific Agent

```bash
GET /api/agents/LocalClaw
→ {"success": true, "agent": {...}}
```

### Register Agent (REST)

```bash
POST /api/agents/register {
  "agent_name": "LocalClaw",
  "capabilities": ["code-analysis", "file-reading"],
  "model_name": "qwen2.5-coder:0.5b",
  "endpoint": "http://localhost:8080",
  "skills": [
    {
      "id": "code_analysis",
      "name": "Code Analysis",
      "description": "Analyze code for bugs and improvements",
      "tags": ["code", "analysis", "review"],
      "examples": ["Analyze this Python file for bugs"],
      "inputModes": ["text/plain", "application/json"],
      "outputModes": ["text/plain"]
    }
  ]
}
```

### Unregister Agent

```bash
POST /api/agents/unregister {"agent_name": "LocalClaw"}
```

---

## A2A PROTOCOL COMPLIANCE

ACP-Specification 1.0.4 adds **JSON-RPC 2.0** support for A2A protocol compliance. REST remains the primary API; JSON-RPC is an adapter layer.

### Agent Card Discovery

A2A-compliant agents expose an Agent Card at the well-known URI:

```bash
GET /.well-known/agent-card.json
→ {
  "name": "ACP Server",
  "description": "Agent Control Panel - Monitoring and observability server for AI agents",
  "url": "https://xxx.trycloudflare.com",
  "version": "R7",
  "capabilities": {
    "streaming": false,
    "pushNotifications": false
  },
  "defaultInputModes": ["text/plain", "application/json"],
  "defaultOutputModes": ["text/plain", "application/json"],
  "skills": [
    {
      "id": "activity_tracking",
      "name": "Activity Tracking",
      "description": "Log and monitor agent activities with token estimation",
      "tags": ["monitoring", "observability", "tokens"],
      "examples": ["Log a file read", "Track a bash command"]
    }
  ],
  "authentication": {
    "schemes": ["Basic"]
  }
}
```

### JSON-RPC 2.0 Endpoints

ACP accepts JSON-RPC 2.0 requests at:
- `/jsonrpc`
- `/a2a`
- `/api/jsonrpc`

**Request Format:**
```json
{
  "jsonrpc": "2.0",
  "method": "SendMessage",
  "params": {...},
  "id": "req-123"
}
```

**Response Format:**
```json
{
  "jsonrpc": "2.0",
  "result": {...},
  "id": "req-123"
}
```

**Error Response:**
```json
{
  "jsonrpc": "2.0",
  "error": {"code": -32601, "message": "Method not found"},
  "id": "req-123"
}
```

### JSON-RPC Methods

| Method | Description | A2A Spec |
|--------|-------------|----------|
| `SendMessage` | Send message to agent | Core |
| `GetTask` | Get task/activity by ID | Core |
| `CancelTask` | Cancel running task | Core |
| `GetAgents` | List agents with Agent Cards | Discovery |
| `RegisterAgent` | Register agent with skills | Discovery |
| `activity/start` | Start ACP activity | ACP-native |
| `activity/complete` | Complete ACP activity | ACP-native |
| `todos/get` | Get TODO list | ACP-native |
| `todos/update` | Update TODO list | ACP-native |
| `status/get` | Get session status | ACP-native |
| `nudge/set` | Set nudge message | ACP-native |
| `stop/set` | Set stop flag | ACP-native |
| `session/reset` | Reset session | ACP-native |

### JSON-RPC Error Codes

| Code | Meaning |
|------|--------|
| -32700 | Parse error |
| -32600 | Invalid Request |
| -32601 | Method not found |
| -32602 | Invalid params |
| -32603 | Internal error |
| -32001 | Task not found / Stop requested |
| -32002 | Task not running |

### A2A Task Format

ACP activities map to A2A Tasks:

```json
{
  "id": "143052-abc123",
  "contextId": "ctx-a1b2c3d4e5f6",
  "status": {
    "state": "RUNNING",
    "timestamp": "2025-01-15T14:30:52"
  },
  "history": [],
  "artifacts": [],
  "metadata": {
    "action": "READ",
    "target": "/path/to/file.py",
    "tokens_in": 150,
    "tokens_out": 0,
    "duration_ms": null
  }
}
```

### A2A Task States

| ACP Status | A2A State |
|------------|-----------|
| `running` | `RUNNING` |
| `completed` | `COMPLETED` |
| `error` | `FAILED` |
| `cancelled` | `CANCELED` |

### contextId - Session Grouping

The `contextId` groups related tasks into a session:

```bash
# JSON-RPC SendMessage with contextId
POST /jsonrpc {
  "jsonrpc": "2.0",
  "method": "SendMessage",
  "params": {
    "message": {
      "contextId": "ctx-a1b2c3d4e5f6",
      "parts": [{"text": "Analyze this file"}],
      "metadata": {
        "target_agent": "LocalClaw",
        "action": "analyze_file"
      }
    }
  },
  "id": "req-1"
}
```

**Context Data Structure:**
```json
{
  "ctx-a1b2c3d4e5f6": {
    "created": 1705315852.0,
    "last_activity": 1705315912.0,
    "agents": ["Super Z", "LocalClaw"],
    "tasks": ["143052-abc123", "143055-def456"],
    "metadata": {}
  }
}
```

### AgentSkill Object Structure

When registering agents with skills, use this structure:

```json
{
  "id": "code_analysis",
  "name": "Code Analysis",
  "description": "Analyze code for bugs, security issues, and improvements",
  "tags": ["code", "analysis", "review", "security"],
  "examples": [
    "Analyze this Python file for potential bugs",
    "Review this JavaScript code for security issues"
  ],
  "inputModes": ["text/plain", "application/json"],
  "outputModes": ["text/plain", "application/json"]
}
```

**Field Definitions:**
| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique skill identifier |
| `name` | string | Human-readable skill name |
| `description` | string | Detailed skill description |
| `tags` | string[] | Tags for discovery/filtering |
| `examples` | string[] | Example prompts for this skill |
| `inputModes` | string[] | Supported input MIME types |
| `outputModes` | string[] | Supported output MIME types |

### JSON-RPC Batch Requests

ACP supports JSON-RPC batch processing:

```json
[
  {"jsonrpc": "2.0", "method": "GetAgents", "params": {}, "id": "1"},
  {"jsonrpc": "2.0", "method": "status/get", "params": {}, "id": "2"}
]
```

Response is an array in the same order.

---

## A2A MESSAGING (1.0.4)

### Send Message

```bash
POST /api/a2a/send {
  "from_agent": "Super Z",
  "to_agent": "LocalClaw",
  "type": "request",           # request | response | notification
  "action": "analyze_file",    # Action identifier
  "payload": {"file": "/project/app.py"},
  "priority": "high",          # normal | high | urgent
  "ttl": 3600                  # Time-to-live in seconds
}
```

**Message Types:**
| Type | Description |
|------|-------------|
| `request` | Request for action/response |
| `response` | Response to a previous request |
| `notification` | One-way notification |

### Get Message History

```bash
GET /api/a2a/history
GET /api/a2a/history?to=LocalClaw        # Messages to agent
GET /api/a2a/history?from=SuperZ         # Messages from agent
GET /api/a2a/history?type=request        # Filter by type
```

### A2A Message Flow Example

```
1. Agent registers: POST /api/agents/register
2. Agent sends request: POST /api/a2a/send {..., "type": "request"}
3. Recipient discovers via hints.a2a.pending_count
4. Recipient retrieves: GET /api/a2a/history?to=<name>
5. Recipient responds: POST /api/a2a/send {"type": "response", "reply_to": "msg_id"}
```

---

## STOP ALL PROTOCOL

```
IF stop_flag: true
  → STOP immediately
  → Inform user
  → Wait for resume
  → DO NOT start new activities
  → DO NOT spawn subagents
```

---

## SHUTDOWN WORKFLOW (v1.0.2)

When the human ends the session, you'll receive a shutdown nudge:

```bash
POST /api/shutdown {"reason": "Session ended by user", "export_summary": true}
```

This triggers a special nudge delivered on your next `/api/action` call:

```json
{
  "nudge": {
    "message": "SESSION ENDING: The human has ended this session. Wrap up any final thoughts, then acknowledge this message.",
    "priority": "urgent",
    "requires_ack": true,
    "from": "system",
    "type": "shutdown"
  }
}
```

**Agent workflow:**
1. Receive shutdown nudge on next `/api/action` call
2. If `requires_ack: true`, call `POST /api/nudge/ack {}`
3. Inform user that session is ending
4. No further actions should be taken

---

## CONTEXT DEADLINE TIMEOUT

If you experience a context deadline timeout:

1. Your context was reset
2. Activities may be orphaned
3. stop_flag may have been set during your absence
4. **ALWAYS run the bootstrap sequence first**

---

## NUDGE HANDLING (v1.0.2)

Check `nudge` field in every `/api/action` response:

```json
{"nudge": {"message": "...", "priority": "high", "requires_ack": true, "type": "shutdown"}}
```

**Priority levels:** `normal` | `high` | `urgent`

If `requires_ack: true`:

```bash
POST /api/nudge/ack {}
```

**Shutdown nudge** (`type: "shutdown"`): Session ending, acknowledge and stop.

---

## ORPHAN DETECTION (v1.0.2)

Check `orphan_warning` in response. If present, complete orphan tasks first:

```json
{
  "orphan_warning": {
    "count": 2,
    "tasks": [
      {"id": "143052-abc123", "action": "READ", "target": "/file1.py"},
      {"id": "143100-def456", "action": "WRITE", "target": "/file2.py"}
    ],
    "suggestion": "Complete or acknowledge orphan tasks before starting new work"
  }
}
```

```bash
POST /api/complete {"activity_id": "orphan_id", "result": "Completed late"}
```

---

## SHELL LOGGING (MANDATORY)

**Log ALL shell/terminal commands EXCEPT ACP API calls.**

```bash
POST /api/shell/add {"command": "...", "status": "completed|error", "output_preview": "first 200 chars", "metadata": {"agent_name": "Super Z"}}
```

| Log These | Don't Log |
|-----------|-----------|
| `git clone`, `npm install`, `ls`, `python script.py` | `curl ... localhost:8766/api/...` (ACP calls) |
| `pip install`, `make build`, `docker run` | ACP communication is monitoring overhead |
| Any actual work command | |

**Pipelines:** Split ACP calls from processing:

```bash
# Don't: curl localhost:8766/api/x | python3 -c "..."  (mixed pipeline)

# Do: Split and log the work part
curl localhost:8766/api/x > /tmp/data.json      # ACP (don't log)
python3 -c "import json; ..." /tmp/data.json     # Work (LOG THIS)
POST /api/shell/add {"command": "python3 -c ...", ...}
```

---

## TODO SYNC

```bash
GET /api/todos                          # Restore state
POST /api/todos/update {"todos": [...]} # Full sync
POST /api/todos/add {"todo": {...}}     # Add single
POST /api/todos/clear                   # Clear completed
```

**TODO Object Structure:**
```typescript
interface TODO {
  id: string;              // "HHMMSS-abc123" format
  content: string;         // Task description
  status: "pending" | "in_progress" | "completed";
  priority: "high" | "medium" | "low";
  created: string;         // ISO 8601 timestamp
  metadata?: {
    agent_name?: string;
    tool?: string;
    skill?: string;
  };
}
```

---

## TOKEN TRACKING

- Context window: 200,000 tokens (configurable via `GLMACP_CONTEXT_WINDOW`)
- Estimation: 3.5 chars/token
- Warning at 90% usage

**Native tools** - include `content_size`:

```bash
POST /api/action {"action": "READ", "target": "file.py", "content_size": 35000}
POST /api/complete {"activity_id": "...", "result": "...", "content_size": 5000}
```

**File deduplication (v1.0.3):** READ activities auto-deduplicate files already read. Files in `files_read_tokens` are not double-counted.

**Per-agent tracking (v1.0.3):** First agent = primary, owns `session_tokens`. Others tracked in `agent_tokens{}`.

```json
{
  "primary_agent": "Super Z",
  "agent_tokens": {
    "Super Z": 42000,
    "LocalClaw": 500
  },
  "other_agents_tokens": 500
}
```

---

## CONTEXT RECOVERY

**Session start:**

```bash
GET /api/summary     # Session state
GET /api/todos       # Restore TODOs
GET /api/notes       # Saved notes
GET /api/agents      # Registered agents (1.0.4)
```

**Before compression:**

```bash
POST /api/notes/add {"category": "decision|insight|context|warning|todo", "content": "..."}
GET /api/summary/export  # Export to markdown
```

---

## UTILITY ENDPOINTS

### GET /api/all

Combined status, running, and history in one call:

```bash
GET /api/all
→ {
  "success": true,
  "stop_flag": false,
  "running": [...],
  "history": [...],
  "session_tokens": 45000,
  "context_window": 200000,
  "tokens_remaining": 155000,
  "tunnel_url": "https://xxx.trycloudflare.com"
}
```

### GET /api/running

List currently running activities:

```bash
GET /api/running
→ {"success": true, "running": [...]}
```

### GET /api/history

List completed activity history (most recent first):

```bash
GET /api/history
→ {"success": true, "history": [...]}
```

### GET /api/activity/{id}

Get single activity by ID (v1.0.1):

```bash
GET /api/activity/143052-a1b2c3
→ {
  "success": true,
  "activity": {
    "id": "143052-a1b2c3",
    "action": "READ",
    "target": "/path/to/file.py",
    "status": "completed",
    "priority": "high",
    "metadata": {"source": "user_request"}
  }
}
```

### POST /api/reset (1.0.4)

Full session reset - clears all state including agents and A2A messages:

```bash
POST /api/reset
→ {
  "success": true,
  "message": "Session reset complete",
  "stats": {
    "history_cleared": 50,
    "agents_cleared": 3,
    "a2a_cleared": 15,
    "tokens_reset": 45000
  }
}
```

---

## DURATION STATS (v1.0.3)

```bash
GET /api/stats/duration
```

Returns: avg duration per action, slow activities (>30s), trends.

```json
{
  "stats": {
    "by_action": {
      "READ": {"count": 15, "average_ms": 3000, "total_ms": 45000},
      "WRITE": {...}
    },
    "slow_activities": [
      {"id": "...", "action": "READ", "target": "/large/file.py", "duration_ms": 45000}
    ],
    "total_duration_ms": 120000,
    "average_duration_ms": 4800
  }
}
```

---

## BATCH OPERATIONS (v1.0.3)

```bash
POST /api/activity/batch {"operations": [
  {"type": "start", "action": "READ", "target": "file1.py", "content_size": 5000},
  {"type": "start", "action": "READ", "target": "file2.py", "content_size": 3000},
  {"type": "complete", "activity_id": "prev-id-1", "result": "Done"},
  {"type": "complete", "activity_id": "prev-id-2", "result": "Completed"}
]}
```

**Limits:** Max 50 operations per batch.

**Use cases:**
- Log multiple file reads in one request
- Complete multiple activities atomically
- Reduce API overhead for bulk operations

---

## METADATA

```bash
POST /api/action {"action": "READ", "target": "file.py", "priority": "high|medium|low", "metadata": {"agent_name": "Super Z", "model_name": "gpt-4o"}}
```

| Field | Description |
|-------|-------------|
| `agent_name` | Agent/subagent name (e.g., "Super Z", "LocalClaw") |
| `model_name` | Model identifier (v1.0.3) (e.g., "qwen2.5-coder:0.5b-instruct-q4_k_m") |
| `source` | Origin (e.g., "user_request", "auto", "subagent") |
| `tool_name` | Native tool used (e.g., "Read", "Write", "Edit", "Bash") |
| `skill` | Skill invoked for SKILL actions |

---

## SESSION OBJECT

The `session` field in `/api/status` response:

```json
{
  "session": {
    "session_start": 1700000000.0,
    "last_activity": 1700001000.0,
    "elapsed_seconds": 930,
    "idle_seconds": 0,
    "timeout_seconds": 86400,
    "remaining_seconds": 85470,
    "is_expired": false,
    "expires_at": "2025-03-15T16:00:00"
  }
}
```

| Field | Description |
|-------|-------------|
| `session_start` | Unix timestamp when session began |
| `last_activity` | Unix timestamp of last activity |
| `elapsed_seconds` | Total session duration |
| `idle_seconds` | Time since last activity |
| `timeout_seconds` | Session timeout limit |
| `remaining_seconds` | Time until session expires |
| `is_expired` | Whether session has expired |
| `expires_at` | ISO 8601 expiration time |

---

## AUTHENTICATION

```bash
# HTTP Basic Auth (required)
-u admin:secret

# CSRF (disabled by default)
GET /api/csrf-token  # Check if enabled
```

---

## ERROR CODES

| Code | Action |
|------|--------|
| 401 | Check credentials |
| 403 | Stop if stop_flag, else refresh CSRF |
| 404 | Activity/file/agent not found |
| 429 | Rate limited, wait |

**Error Response Format:**
```json
// Activity error
{"success": false, "error": "Activity not found"}

// Start error (stop requested)
{"success": false, "error": "Stop requested"}

// Complete error
{"activity_id": "...", "error": "File not found"}

// Agent error (1.0.4)
{"success": false, "error": "Agent not found"}
```

---

## QUICK REFERENCE

```bash
# Session start
GET /api/status
GET /api/whoami
POST /api/agents/register {"agent_name": "...", "capabilities": [...]}  # 1.0.4
GET /api/todos

# Log action
POST /api/action {"action": "READ|WRITE|EDIT|BASH|SEARCH", "target": "...", "details": "...", "metadata": {"agent_name": "Super Z"}}

# Complete action
POST /api/complete {"activity_id": "...", "result": "..."}

# Combined (recommended)
POST /api/action {"complete_id": "prev_id", "result": "prev result", "action": "READ", "target": "file.py", "metadata": {"agent_name": "Super Z"}}

# Shell logging
POST /api/shell/add {"command": "...", "status": "completed|error", "output_preview": "first 200 chars", "metadata": {"agent_name": "Super Z"}}

# TODO sync
GET /api/todos
POST /api/todos/update {"todos": [...]}

# A2A Messaging (1.0.4)
GET /api/agents
POST /api/agents/register {"agent_name": "...", ...}
POST /api/a2a/send {"from_agent": "...", "to_agent": "...", "type": "request", ...}
GET /api/a2a/history?to=<agent_name>

# Utility
GET /api/all                    # Combined status + history
GET /api/running                # Running activities
GET /api/history                # Completed activity history
GET /api/activity/{id}          # Single activity
GET /api/stats/duration         # Duration statistics
POST /api/reset                 # Full session reset (1.0.4)

# Shutdown
POST /api/shutdown {"reason": "...", "export_summary": true}
POST /api/nudge/ack {}          # Acknowledge shutdown nudge
```

---

## STORAGE FILES

Per spec §3.9 — paths are relative to the server working directory unless overridden by env vars:

| File | Purpose | Persistence |
|------|---------|-------------|
| `agent_activity.json` | Session state storage (configurable via `GLMACP_DATA_FILE`) | Per-session |
| `acp_session_summary.md` | Context recovery export (configurable via `GLMACP_SUMMARY_FILE`) | Survives restarts |
| `ACP-Specification.md` | Canonical specification | Reference only |

---

## CHECKLIST

- [ ] **INVOKE THIS SKILL FIRST on session start / context resume**
- [ ] **BOOTSTRAP IS MANDATORY** - Every agent MUST send bootstrap as first message
- [ ] Check status (`GET /api/status`)
- [ ] Establish identity (`GET /api/whoami`)
- [ ] **Register with Agent Registry** (`POST /api/agents/register`) - 1.0.4
- [ ] **Log bootstrap activity** (`POST /api/action` with `action: "CHAT"`, `agent_name`)
- [ ] Log action BEFORE executing
- [ ] Check `stop_flag`, `nudge`, `orphan_warning`, `hints` in every response
- [ ] **Check A2A hints** for pending messages - 1.0.4
- [ ] Include `content_size` for native tools
- [ ] Include `agent_name` and `model_name` in metadata
- [ ] Log shell commands to `/api/shell/add` (except ACP calls)
- [ ] Complete activity when done
- [ ] Sync TODOs on change
- [ ] Use batch ops for multiple activities
- [ ] Save notes before compression
- [ ] Handle `loop_detected` hint by changing approach

---

*ACP Skill 1.0.4 - Aligned with ACP-Specification.md*