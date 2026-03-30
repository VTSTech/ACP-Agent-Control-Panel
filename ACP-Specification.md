# Agent Control Panel (ACP) Specification

**Version:** 1.0.6  
**Status:** Draft  
**Authors:** VTSTech, Community Contributors  
**A2A Compliance:** JSON-RPC 2.0, Agent Card, contextId support

---

## Abstract

The Agent Control Panel (ACP) is a monitoring and observability protocol for AI agents. Unlike communication protocols (MCP, A2A) that connect agents to tools or other agents, ACP provides a standardized way to monitor, control, and recover AI agent sessions through a RESTful HTTP API.

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Architecture](#2-architecture)
3. [Data Model](#3-data-model)
4. [API Specification](#4-api-specification)
5. [Agent Workflow](#5-agent-workflow)
6. [Context Recovery](#6-context-recovery)
7. [Security](#7-security)
8. [Configuration](#8-configuration)
9. [Implementation Guide](#9-implementation-guide)

---

## 1. Introduction

### 1.1 Purpose

ACP solves the observability problem for AI agents by providing:

- **Activity Tracking**: Real-time monitoring of agent actions
- **Token Management**: Context window usage estimation
- **Control Mechanism**: Emergency stop capability
- **Context Recovery**: Session state preservation across context compressions
- **TODO Management**: Task tracking for agents
- **Shell History**: Terminal command logging
- **File Management**: Integrated file browser for workspace access
- **Remote Access**: Built-in cloudflared tunnel for public access (v1.0.3)
- **Agent Registry**: A2A agent discovery and presence tracking (1.0.4)
- **Inter-Agent Messaging**: Lightweight agent-to-agent communication (1.0.4)

### 1.2 Design Principles

1. **Sidecar Architecture**: ACP runs alongside the agent, not between agent and user
2. **RESTful API**: Simple HTTP interface, language-agnostic
3. **Stateless Server**: All state persisted to storage, server can restart safely
4. **Log-First Workflow**: Agents must log actions BEFORE executing them
5. **Self-Contained**: No external dependencies required
6. **Mandatory Integration**: Agents MUST log actions, shell commands, and TODO changes

### 1.3 Comparison to Other Protocols

| Feature | ACP | MCP | A2A | OpenTelemetry |
|---------|-----|-----|-----|---------------|
| Purpose | Monitoring | Tool Injection | Inter-Agent | Telemetry |
| Direction | Sidecar | Agent↔Tool | Agent↔Agent | Agent→Backend |
| Token Tracking | ✅ | ❌ | ❌ | ⚠️ Custom |
| STOP ALL | ✅ | ❌ | ❌ | ❌ |
| TODO Management | ✅ | ❌ | ❌ | ❌ |
| Context Recovery | ✅ | ❌ | ❌ | ⚠️ Limited |
| File Manager | ✅ | ⚠️ Basic | ❌ | ❌ |
| Shell History | ✅ | ❌ | ❌ | ❌ |
| Agent Registry | ✅ | ❌ | ⚠️ Basic | ❌ |
| Inter-Agent Messaging | ✅ | ❌ | ✅ | ❌ |
| JSON-RPC 2.0 | ✅ | ✅ | ✅ | ❌ |
| Agent Card | ✅ | ❌ | ✅ | ❌ |
| contextId | ✅ | ❌ | ✅ | ❌ |
| Transport | HTTP REST + JSON-RPC | JSON-RPC | JSON-RPC/gRPC | OTLP |

---

## 2. Architecture

### 2.1 Components

```
┌─────────────────────────────────────────────────────────────────┐
│                        AI AGENT                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  1. CHECK STATUS (stop_flag?)                            │   │
│  │  2. LOG ACTION (POST /api/action)                        │   │
│  │  3. EXECUTE ACTION                                        │   │
│  │  4. LOG COMPLETE (POST /api/complete)                    │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP REST
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ACP SERVER                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │  Activity   │  │   Token     │  │   File      │             │
│  │  Monitor    │  │   Tracker   │  │   Manager   │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │    TODO     │  │   Shell     │  │   Context   │             │
│  │   Tracker   │  │   History   │  │   Recovery  │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
│  ┌─────────────┐  ┌─────────────┐                               │
│  │   A2A       │  │   Agent     │  (1.0.4)                     │
│  │  Messaging  │  │  Registry   │                               │
│  └─────────────┘  └─────────────┘                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    STORAGE                                      │
│  ┌──────────────────────┐  ┌──────────────────────┐            │
│  │  agent_activity.json │  │  acp_session_summary │            │
│  │  (Session State)     │  │  .md (Recovery)      │            │
│  └──────────────────────┘  └──────────────────────┘            │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Request Flow

```
Agent Action Flow:
─────────────────

     ┌──────────────┐
     │ CHECK STATUS │─────► GET /api/status
     └──────┬───────┘       (stop_flag == true ? STOP)
            │
            ▼
     ┌──────────────┐
     │ LOG ACTION   │─────► POST /api/action (recommended)
     └──────┬───────┘       OR POST /api/start
            │               Returns: activity_id, hints, a2a_hints
            ▼
     ┌──────────────┐
     │ DO ACTION    │─────► Execute Read/Write/Edit/Bash/etc.
     └──────┬───────┘
            │
            ▼
     ┌──────────────┐
     │ LOG COMPLETE │─────► POST /api/complete
     └──────────────┘       OR include in next POST /api/action
                            {activity_id, result}

Note: POST /api/action is the recommended combined endpoint that can
complete previous activity AND start new one in a single request.
```

---

## 3. Data Model

### 3.1 Session State

The complete session state is stored in a single JSON file:

```json
{
  "running": ["<Activity>", "..."],
  "history": ["<Activity>", "..."],
  "stop_flag": false,
  "stop_reason": null,
  "session_tokens": 45000,
  "startup_tokens": 3000,
  "todos": ["<TODO>", "..."],
  "shell_history": ["<ShellEntry>", "..."],
  "ai_notes": ["<Note>", "..."],
  "session_start": 1700000000.0,
  "last_activity": 1700001000.0,
  "nudge": null,
  "primary_agent": "Super Z",
  "agent_tokens": {
    "Super Z": 42000,
    "LocalClaw": 500
  },
  "files_read_tokens": {
    "/path/to/file.py": 1500,
    "/path/to/config.json": 800
  },
  "agents": {
    "Super Z": {"<Agent>", "..."},
    "LocalClaw": {"<Agent>", "..."}
  },
  "a2a_messages": ["<A2AMessage>", "..."]
}
```

#### Per-Agent Token Fields

| Field | Description |
|-------|-------------|
| `primary_agent` | First agent to log activity; owns the main context window |
| `agent_tokens` | Token usage breakdown per agent name |
| `files_read_tokens` | Tracks files already counted for token deduplication |

#### Session Metadata Fields

| Field | Description |
|-------|-------------|
| `last_agent` | Name of the agent that most recently logged an activity (default: `"Unknown"`) |
| `last_model` | Model identifier from the most recent activity's metadata (default: `"Unknown"`) |

#### A2A Fields (1.0.4)

| Field | Description |
|-------|-------------|
| `agents` | Agent registry mapping agent names to Agent objects |
| `a2a_messages` | Queue of inter-agent messages (newest first) |
| `contexts` | **1.0.4** A2A contextId → session mapping for multi-turn interactions |
| `agent_skills` | **1.0.4** AgentSkill objects per agent for capability discovery |

## 3.1.1 Ownership Model (1.0.4)

Every activity belongs to the agent that created it, as specified by `metadata.agent_name`. This enables safe multi-tenant operation where multiple agents share a single ACP instance.

**Server-Side Enforcement Requirements:**

1. **Activity Creation**: When an activity is created via `/api/action` or `/api/start`, the server MUST store `metadata.agent_name` as the activity`s owner.

2. **Activity Completion**: When an activity is completed via `/api/complete` or the combined `/api/action`, the server MUST validate that the requesting agent matches the activity owner.

3. **Orphan Filtering**: The `orphan_warning` response field MUST only include activities owned by the requesting agent.

4. **Error Response**: If ownership validation fails, return HTTP `403 Forbidden`:
   ```json
   {
     "success": false,
     "error": "activity owned by {owner_agent_name}"
   }
   ```

**Example - Ownership Violation:**
```bash
# AgentA created activity "abc123"
# AgentB tries to complete it:
POST /api/complete {
  "activity_id": "abc123",
  "result": "Completed",
  "metadata": {"agent_name": "AgentB"}
}
→ HTTP 403
{
  "success": false,
  "error": "activity owned by AgentA"
}
```

**Why This Matters:**
- **Multi-tenant safety**: Multiple agents can share one ACP instance without interfering
- **Orphan isolation**: Agent A cannot accidentally complete Agent B orphaned tasks
- **Audit integrity**: Activity history accurately reflects which agent performed each action
- **Security**: Prevents malicious or buggy agents from tampering with other agents work

### 3.2 Activity Object

```typescript
interface Activity {
  id: string;              // "HHMMSS-abc123" format
  action: ActionType;      // READ | WRITE | EDIT | BASH | TODO | SKILL | API | SEARCH | CHAT | A2A
  target: string;          // File path, command, or resource identifier
  details: string;         // Human-readable description
  status: ActivityStatus;  // running | completed | error | cancelled
  started: string;         // ISO 8601 timestamp
  completed?: string;      // ISO 8601 timestamp
  tokens_in: number;       // Estimated input tokens
  tokens_out?: number;     // Estimated output tokens
  result?: string;         // Result summary (max 500 chars)
  error?: string;          // Error message (max 200 chars)
  duration_ms?: number;    // Duration in milliseconds
  priority?: Priority;     // v1.0.1: high | medium | low (default: medium)
  metadata?: object;       // v1.0.1: Arbitrary key-value pairs
}
```

### 3.2.1 Priority Levels

| Priority | When to Use |
|----------|-------------|
| `high` | Critical operations, user-requested tasks, blocking dependencies |
| `medium` | Normal operations (default) |
| `low` | Background tasks, optional enhancements, non-urgent |

### 3.2.2 Metadata

Arbitrary key-value pairs for attaching custom context:

```json
{
  "metadata": {
    "agent_name": "Super Z",
    "source": "user_request",
    "tool_name": "Read",
    "file_hash": "abc123",
    "related_file": "/path/to/related.py",
    "retry_count": 2
  }
}
```

#### Standard Metadata Fields

| Field | Description | Example |
|-------|-------------|---------|
| `agent_name` | Name of the agent/subagent performing the action | `"Super Z"`, `"LocalClaw"` |
| `model_name` | **v1.0.3** Model identifier used by the agent | `"qwen2.5-coder:0.5b-instruct-q4_k_m"`, `"gpt-4o"` |
| `source` | Origin of the action | `"user_request"`, `"auto"`, `"subagent"` |
| `tool_name` | Native tool used | `"Read"`, `"Write"`, `"Edit"`, `"Bash"` |
| `skill` | Skill invoked (for SKILL actions) | `"image-generation"`, `"VLM"` |

The `agent_name` field is particularly important for multi-agent scenarios where multiple agents or subagents may work on the same session.

The `model_name` field separates the agent identity from the model it's using. This enables:
- Clean UI display: `LocalClaw · qwen2.5-coder:0.5b-instruct-q4_k_m`
- Filtering activities by model
- Tracking model usage across sessions

**Example with model_name:**
```json
{
  "metadata": {
    "agent_name": "LocalClaw",
    "model_name": "qwen2.5-coder:0.5b-instruct-q4_k_m",
    "source": "user_request"
  }
}
```

### 3.3 Action Types

| Action | Description | Example Target |
|--------|-------------|----------------|
| `READ` | Reading files, viewing content, API GETs | `/path/to/file.py` |
| `WRITE` | Creating new files | `/path/to/newfile.py` |
| `EDIT` | Modifying existing files | `/path/to/file.py` |
| `BASH` | Terminal commands, scripts, CLI tools | `ls -la` |
| `TODO` | TODO state changes | `task-id` or task description |
| `SKILL` | Invoking skills (VLM, TTS, etc.) | `image-generation` |
| `API` | External API calls | `POST https://api.example.com` |
| `SEARCH` | Web search, grep, find operations | `search query` |
| `CHAT` | Conversational/informational exchanges | `discussion topic or question` |
| `A2A` | **1.0.4** Agent-to-agent communication | `AgentA → AgentB` |

### 3.3.1 CHAT Action Type

The `CHAT` action type captures token usage from conversational and cognitive work that doesn't involve tool execution:

**When to use:**
- Q&A exchanges
- Reasoning and analysis discussions
- Planning sessions
- Knowledge transfer
- Specification review
- Decision discussions

**Example:**
```json
POST /api/action {
  "action": "CHAT",
  "target": "AgentSkill specification review",
  "details": "Discussed skill format, discovered missing CHAT type for token tracking"
}
```

**Why it matters:**
Pure conversational exchanges consume context window tokens but were previously untracked. The CHAT type ensures accurate token accounting for all agent activity, including cognitive work without tool execution.

### 3.3.2 A2A Action Type (1.0.4)

The `A2A` action type captures inter-agent communication events:

**When logged:**
- Automatically logged when using `/api/a2a/send`
- Captures sender, recipient, and message type
- Enables activity history tracking of agent interactions

**Example Activity:**
```json
{
  "id": "143052-abc123",
  "action": "A2A",
  "target": "Super Z → LocalClaw",
  "details": "request: analyze_file",
  "status": "completed",
  "tokens_in": 0,
  "tokens_out": 0
}
```

### 3.4 TODO Object

```typescript
interface TODO {
  id: string;              // "HHMMSS-abc123" format
  content: string;         // Task description
  status: TODOStatus;      // pending | in_progress | completed
  priority: Priority;      // high | medium | low
  created: string;         // ISO 8601 timestamp
  metadata?: {             // Optional attribution metadata
    agent_name?: string;   // Agent that created this TODO
    tool?: string;         // Tool that created it
    skill?: string;        // Skill that created it
  };
}
```

### 3.5 Shell Entry Object

```typescript
interface ShellEntry {
  id: string;              // "HHMMSS-abc123" format
  command: string;         // Command executed (max 500 chars)
  timestamp: string;       // ISO 8601 timestamp
  status: ShellStatus;     // running | completed | error
  output_preview: string;  // Output snippet (max 200 chars)
  metadata?: {             // Optional attribution metadata
    agent_name?: string;   // Agent that ran this command
    tool?: string;         // Tool that executed it
  };
}
```

### 3.6 AI Note Object

```typescript
interface Note {
  id: string;              // "HHMMSS-abc123" format
  timestamp: string;       // ISO 8601 timestamp
  category: NoteCategory;  // decision | insight | context | warning | todo
  content: string;         // Note content (max 500 chars)
  importance: Importance;  // normal | high
}
```

### 3.7 Agent Object (1.0.4)

```typescript
interface Agent {
  name: string;              // Agent identifier
  capabilities: string[];    // List of capabilities this agent has
  model_name?: string;       // Model identifier (optional)
  endpoint?: string;         // Remote endpoint URL (optional)
  status: AgentStatus;       // online | offline
  registered_at: string;     // ISO 8601 timestamp
  last_seen: string;         // ISO 8601 timestamp
  tokens_used: number;       // Total tokens consumed by this agent
  online?: boolean;          // Computed: true if last_seen < 60s ago
}
```

**Agent Status:**
- `online`: Agent has been active within last 60 seconds
- `offline`: Agent has not been active recently

**Capabilities Examples:**
- `["code-generation", "file-editing"]`
- `["web-search", "api-integration"]`
- `["image-analysis", "vlm"]`

### 3.8 A2A Context Object

The context object groups related tasks into a session for multi-turn interactions:

```typescript
interface A2AContext {
  contextId: string;         // "ctx-<uuid>" format
  created: number;           // Unix timestamp
  last_activity: number;     // Unix timestamp of last activity
  agents: string[];          // List of agent names in this context
  tasks: string[];           // List of task/activity IDs in this context
  metadata?: object;         // Additional context metadata
}
```

**Usage:**
- Created automatically when `SendMessage` is called without a `contextId`
- Groups related tasks for session tracking
- Enables multi-turn conversation tracking between agents

### 3.9 A2A Task Object

ACP activities map to A2A Task format for protocol compliance:

```typescript
interface A2ATask {
  id: string;                // Activity ID
  contextId?: string;        // Session context ID
  status: {
    state: A2ATaskState;     // RUNNING | COMPLETED | FAILED | CANCELED
    timestamp: string;       // ISO 8601 timestamp
  };
  history: object[];         // Task history (future use)
  artifacts: object[];       // Task artifacts (future use)
  metadata: {
    action: string;          // ACP action type
    target: string;          // ACP target
    tokens_in: number;       // Input tokens
    tokens_out: number;      // Output tokens
    duration_ms?: number;    // Duration in milliseconds
  };
}
```

**State Mapping:**
| ACP Status | A2A State |
|------------|-----------|
| `running` | `RUNNING` |
| `completed` | `COMPLETED` |
| `error` | `FAILED` |
| `cancelled` | `CANCELED` |

### 3.10 AgentSkill Object

Skills describe specific capabilities an agent can perform:

```typescript
interface AgentSkill {
  id: string;                // Unique skill identifier
  name: string;              // Human-readable skill name
  description: string;       // Detailed skill description
  tags?: string[];           // Tags for discovery/filtering
  examples?: string[];       // Example prompts for this skill
  inputModes?: string[];     // Supported input MIME types
  outputModes?: string[];    // Supported output MIME types
}
```

**Example:**
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

### 3.11 Agent Card Object

The Agent Card is served at `/.well-known/agent-card.json` for A2A discovery:

```typescript
interface AgentCard {
  name: string;              // Agent/server name
  description: string;       // Agent description
  url: string;               // Agent endpoint URL
  version: string;           // Agent version
  capabilities: {
    streaming: boolean;      // SSE streaming support
    pushNotifications: boolean; // Push notification support
  };
  defaultInputModes: string[];  // Default input MIME types
  defaultOutputModes: string[]; // Default output MIME types
  skills: AgentSkill[];      // List of agent skills
  authentication: {
    schemes: string[];       // Supported auth schemes
  };
  metadata?: object;         // Additional metadata
}
```

### 3.12 A2A Message Object (1.0.4)

```typescript
interface A2AMessage {
  id: string;                // "HHMMSS-abc123" format
  from_agent: string;        // Sender agent name
  to_agent: string;          // Recipient agent name
  type: MessageType;         // request | response | notification
  action?: string;           // Action to perform (for requests)
  payload?: object;          // Message data/parameters
  priority: Priority;        // normal | high | urgent
  reply_to?: string;         // Message ID this is replying to
  created_at: string;        // ISO 8601 timestamp
  expires_at: string;        // ISO 8601 expiration timestamp
  ttl: number;               // Time-to-live in seconds
}
```

**Message Types:**
| Type | Description | Use Case |
|------|-------------|----------|
| `request` | Request for action/response | Ask another agent to perform a task |
| `response` | Response to a request | Reply to a previous request |
| `notification` | One-way notification | Broadcast status, progress, or events |

**Priority Levels:**
| Priority | When to Use |
|----------|-------------|
| `normal` | Routine communication (default) |
| `high` | Important but not blocking |
| `urgent` | Requires immediate attention |

### 3.13 Storage Files

| File | Purpose | Persistence |
|------|---------|-------------|
| `agent_activity.json` | Session state storage | Per-session |
| `acp_session_summary.md` | Context recovery export | Survives restarts |
| `acp_restart.log` | Server restart debugging | Overwritten each restart |
| `csrf_secret.txt` | CSRF token signing secret | Survives restarts |

---

## 4. API Specification

### 4.1 Authentication

All API requests require HTTP Basic Authentication:

```
Authorization: Basic base64(username:password)
```

### 4.2 CSRF Protection

CSRF protection is **optional** and **disabled by default** for development/testing convenience.

When enabled (via `GLMACP_CSRF_ENABLED=true`), all POST requests require a CSRF token header:

```
X-CSRF-Token: <timestamp>:<signature>
```

Obtain token via `GET /api/csrf-token`. The response includes `csrf_enabled` to indicate whether CSRF is active.

**Recommendation:** Enable CSRF for production deployments exposed to untrusted networks.

### 4.3 Activity Monitor Endpoints

#### GET /api/status

Check stop flag and token usage.

**Response:**
```json
{
  "success": true,
  "stop_flag": false,
  "stop_reason": null,
  "running_count": 1,
  "running": ["<Activity>"],
  "session_tokens": 45000,
  "startup_tokens": 3000,
  "activity_tokens": 42000,
  "context_window": 200000,
  "tokens_remaining": 155000,
  "tokens_percent": 22.5,
  "overflow_warning": null,
  "primary_agent": "Super Z",
  "agent_tokens": {
    "Super Z": 42000,
    "LocalClaw": 500
  },
  "other_agents_tokens": 500,
  "tunnel_url": "https://xxx.trycloudflare.com",
  "session": { "<SessionInfo>" }
}
```

### Per-Agent Token Tracking

The first agent to log an activity becomes the "primary agent" and owns the main context window. Other agents (subagents, LocalClaw, etc.) are tracked separately.

**Fields:**
| Field | Description |
|-------|-------------|
| `primary_agent` | Name of the first agent to log an activity (owns context) |
| `agent_tokens` | Object mapping agent names to their token usage |
| `other_agents_tokens` | Sum of tokens from non-primary agents |
| `session_tokens` | Only reflects primary agent's context consumption |
| `tunnel_url` | **v1.0.3** Active cloudflared tunnel URL, or `null` if not active |

**Why it matters:** Subagents and other agents won't pollute the primary agent's context window estimation, providing accurate tracking for the main session.

#### GET /api/running

List currently running activities.

#### GET /api/history

List completed activity history (most recent first).

#### GET /api/all

Convenience endpoint that returns status, running, history, tokens, and session metadata in one call. Used by the ACP web UI for polling.

**Response:**
```json
{
  "success": true,
  "stop_flag": false,
  "stop_reason": null,
  "running": ["<Activity>"],
  "history": ["<Activity>", "..."],
  "session_tokens": 45000,
  "context_window": 200000,
  "tokens_remaining": 155000,
  "tokens_percent": 22.5,
  "tunnel_url": "https://xxx.trycloudflare.com",
  "primary_agent": "Super Z",
  "last_agent": "Super Z",
  "agent_tokens": {"Super Z": 42000, "LocalClaw": 500},
  "session": { "<SessionInfo>" },
  "todos": ["<TODO>", "..."],
  "shell_history": ["<ShellEntry>", "..."],
  "errors": [],
  "agents": {"Super Z": {"<Agent>"}, "LocalClaw": {"<Agent>"}},
  "hints": { "<ActivityHints>" },
  "nudge": null,
  "orphan_warning": null,
  "current_files": ["file1.py", "file2.md"],
  "base_dir": "/path/to/workspace"
}
```

**Extended Fields (beyond base status):**
| Field | Description |
|-------|-------------|
| `primary_agent` | Name of the primary agent |
| `last_agent` | Most recent agent to log an activity |
| `agent_tokens` | Per-agent token breakdown |
| `session` | Session info with timeout tracking |
| `todos` | Current TODO list |
| `shell_history` | Last 10 shell commands |
| `errors` | Recent error log entries |
| `agents` | Registered agents from Agent Registry |
| `hints` | Activity hints for the most recent action |
| `nudge` | Pending nudge (primary agent only) |
| `orphan_warning` | Orphaned running activities |
| `current_files` | Files accessed in current session |
| `base_dir` | Base directory for file operations |

#### GET /api/activity/{activity_id}

**v1.0.1** Get a single activity by ID.

**Response:**
```json
{
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

**Error Response:**
```json
{
  "success": false,
  "error": "Activity not found"
}
```

#### POST /api/start

Start a new activity.

**Request:**
```json
{
  "action": "READ",
  "target": "/path/to/file.py",
  "details": "Reading configuration file",
  "content_size": 35000,
  "priority": "high",
  "metadata": {"source": "user_request"}
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | Yes | Action type (READ, WRITE, EDIT, BASH, etc.) |
| `target` | string | Yes | File path, command, or resource identifier |
| `details` | string | No | Human-readable description |
| `content_size` | integer | No | **v1.0.1** Character count of content read/consumed |
| `priority` | string | No | **v1.0.1** Activity priority: `high`, `medium` (default), `low` |
| `metadata` | object | No | **v1.0.1** Arbitrary key-value pairs |

**Response:**
```json
{
  "success": true,
  "activity_id": "143052-a1b2c3",
  "session_tokens": 45100,
  "context_window": 200000,
  "tokens_remaining": 154900,
  "hints": {
    "modified_this_session": true,
    "a2a": {
      "pending_count": 2,
      "senders": ["LocalClaw"],
      "preview": {
        "from": "LocalClaw",
        "action": "file_analysis_complete",
        "msg_id": "143000-xyz789"
      }
    }
  }
}
```

**Error (Stop Requested):**
```json
{
  "success": false,
  "error": "Stop requested"
}
```

#### POST /api/complete

Complete an activity.

**Request:**
```json
{
  "activity_id": "143052-a1b2c3",
  "result": "File read successfully, 150 lines",
  "content_size": 5000,
  "metadata": {"file_hash": "abc123"}
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `activity_id` | string | Yes | ID of activity to complete |
| `result` | string | No | Result summary (max 500 chars) |
| `error` | string | No | Error message if failed (max 200 chars) |
| `content_size` | integer | No | **v1.0.1** Character count of content written/generated |
| `metadata` | object | No | **v1.0.1** Additional metadata (merged with existing) |

**Response:**
```json
{
  "success": true,
  "activity": {"<Activity>"},
  "session_tokens": 45100,
  "context_window": 200000,
  "tokens_remaining": 154900,
  "hints": {
    "a2a": {
      "pending_count": 1,
      "senders": ["LocalClaw"]
    }
  }
}
```

**Error Response:**
```json
{
  "success": false,
  "error": "Activity not found"
}
```

#### POST /api/action

Combined endpoint: complete previous + start new in one call.

**Request:**
```json
{
  "complete_id": "143052-a1b2c3",
  "result": "Previous action completed",
  "complete_content_size": 5000,
  "complete_metadata": {"file_hash": "abc123"},
  "action": "READ",
  "target": "/path/to/next/file.py",
  "details": "Reading next file",
  "content_size": 35000,
  "priority": "high",
  "metadata": {"source": "user_request"}
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `complete_id` | string | No | ID of previous activity to complete |
| `result` | string | No | Result summary for previous activity |
| `error` | string | No | Error message if previous activity failed |
| `complete_content_size` | integer | No | **v1.0.1** Character count written in previous activity |
| `complete_metadata` | object | No | **v1.0.1** Metadata to merge into previous activity |
| `action` | string | Yes | Action type for new activity |
| `target` | string | Yes | Target for new activity |
| `details` | string | No | Description for new activity |
| `content_size` | integer | No | **v1.0.1** Character count to be read in new activity |
| `priority` | string | No | **v1.0.1** Priority for new activity |
| `metadata` | object | No | **v1.0.1** Metadata for new activity |

**Response:**
```json
{
  "success": true,
  "activity_id": "143100-d4e5f6",
  "completed": { "<Previous Activity>" },
  "stop_flag": false,
  "session_tokens": 45200,
  "context_window": 200000,
  "tokens_remaining": 154800,
  "tokens_percent": 22.6,
  "overflow_warning": null,
  "session": { "<SessionInfo>" },
  "running_count": 1,
  "hints": {
    "modified_this_session": true,
    "modification_count": 3,
    "last_action": "EDIT",
    "related_todos": [{"id": "1", "content": "Fix bug in file.py", "status": "pending"}],
    "active_todos": 2,
    "a2a": {
      "pending_count": 2,
      "senders": ["LocalClaw"],
      "preview": {"from": "LocalClaw", "action": "analysis_done"}
    }
  },
  "nudge": null,
  "orphan_warning": null
}
```

### Orphan Warning (v1.0.2)

The `orphan_warning` field alerts agents when they're starting a new task while other tasks are still running:

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

**When present:**
- Indicates running tasks from previous operations that weren't completed
- The agent should complete these tasks first or acknowledge them
- Helps prevent "task leakage" where activities pile up in running state

**Agent workflow for orphan handling:**
```
1. Check response for orphan_warning
2. If present:
   a. Review the orphan tasks list
   b. Complete each orphan: POST /api/complete {id, result}
   c. Or acknowledge and proceed if intentional
3. Continue with new task
```

### Activity Hints (v1.0.1)

The `hints` field provides contextual information to help agents make better decisions:

| Field | Type | Description |
|-------|------|-------------|
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

### A2A Hints (1.0.4)

When an agent includes `agent_name` in activity metadata, A2A hints are automatically included to notify about pending messages:

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
   a. GET /api/a2a/history?to=<my_agent_name> to retrieve messages
   b. Process each message based on type and action
   c. Send response if needed via POST /api/a2a/send
3. Continue with task
```

#### POST /api/stop

Trigger STOP ALL - cancels all running activities.

**Request:**
```json
{
  "reason": "User clicked STOP ALL"
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `reason` | string | No | Human-readable reason for stop (default: "User requested") |

#### POST /api/resume

Clear stop flag and resume operations.

#### POST /api/shutdown

**v1.0.2** Gracefully end the session. This endpoint:
1. Exports session summary for context recovery
2. Cancels all running activities
3. Sets a shutdown nudge to notify the agent
4. Stops the server after a brief delay

**Request:**
```json
{
  "reason": "Session ended by user",
  "export_summary": true
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `reason` | string | No | Human-readable reason for shutdown (default: "Session ended by user") |
| `export_summary` | boolean | No | Whether to export session summary (default: true) |

**Response:**
```json
{
  "success": true,
  "message": "Session ending - agent has been notified",
  "summary_exported": true,
  "summary_path": "/path/to/acp_session_summary.md",
  "cancelled_activities": 2,
  "note": "Server will stop in 2 seconds. Agent should acknowledge the shutdown nudge."
}
```

**Shutdown Nudge:**

The agent receives a special nudge with `type: "shutdown"`:

```json
{
  "nudge": {
    "message": "SESSION ENDING: The human has ended this session. Wrap up any final thoughts, then acknowledge this message. The server will stop shortly.",
    "priority": "urgent",
    "requires_ack": true,
    "from": "system",
    "type": "shutdown"
  }
}
```

#### POST /api/clear_history

Clear activity history.

#### POST /api/reset_session

Reset session to fresh state (tokens reset to startup value).

#### POST /api/reset

**1.0.4** Full session reset - clears all state including agents and A2A messages.

**Response:**
```json
{
  "success": true,
  "message": "Session reset complete",
  "stats": {
    "history_cleared": 50,
    "shell_cleared": 20,
    "todos_cleared": 5,
    "agents_cleared": 3,
    "a2a_cleared": 15,
    "tokens_reset": 45000
  }
}
```

### 4.4 TODO Endpoints

#### GET /api/todos

Get current TODO list.

#### POST /api/todos/update

Replace entire TODO list.

**Request:**
```json
{
  "todos": [
    {"content": "Task 1", "status": "pending", "priority": "high"},
    {"content": "Task 2", "status": "in_progress", "priority": "medium"}
  ]
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `todos` | array | Yes | Array of TODO objects to replace entire list |
| `todos[].content` | string | Yes | Task description |
| `todos[].status` | string | No | `pending`, `in_progress`, or `completed` (default: `pending`) |
| `todos[].priority` | string | No | `high`, `medium`, or `low` (default: `medium`) |

#### POST /api/todos/add

Add single TODO item.

**Request:**
```json
{
  "todo": {
    "content": "New task",
    "status": "pending",
    "priority": "high"
  },
  "agent_name": "Super Z",
  "tool": "planning",
  "skill": "fullstack-dev"
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `todo.content` | string | Yes | Task description |
| `todo.status` | string | No | `pending`, `in_progress`, or `completed` (default: `pending`) |
| `todo.priority` | string | No | `high`, `medium`, or `low` (default: `medium`) |
| `agent_name` | string | No | Name of agent creating the TODO |
| `tool` | string | No | Tool that created the TODO |
| `skill` | string | No | Skill that created the TODO |

#### POST /api/todos/clear

Clear completed TODOs.

#### POST /api/todos/toggle

Toggle a TODO item's status between `pending` and `completed`.

**Request:**
```json
{
  "id": "143052-a1b2c3"
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `id` | string | Yes | TODO item ID to toggle |

**Response:**
```json
{
  "success": true,
  "todo": {"<TODO>"},
  "toggled": true
}
```

### 4.5 Shell History Endpoints

#### GET /api/shell

Get shell command history.

#### POST /api/shell/add

Add shell command to history.

**Request:**
```json
{
  "command": "ls -la",
  "status": "completed",
  "output_preview": "total 64\ndrwxr-xr-x...",
  "agent_name": "Super Z",
  "tool": "shell"
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `command` | string | Yes | Command executed (max 500 chars) |
| `status` | string | No | `running`, `completed`, or `error` (default: `completed`) |
| `output_preview` | string | No | Output snippet (max 200 chars) |
| `agent_name` | string | No | Name of agent running the command |
| `tool` | string | No | Tool that executed the command |
| `metadata` | object | No | Additional metadata (can include agent_name, tool, etc.) |

#### POST /api/shell/clear

Clear shell history.

### 4.6 Context Recovery Endpoints

#### GET /api/summary

Get condensed session summary for context recovery.

**Response:**
```json
{
  "success": true,
  "summary": {
    "session_overview": {
      "duration": "15m 30s",
      "duration_seconds": 930,
      "total_activities": 42,
      "activity_breakdown": {"READ": 25, "EDIT": 10, "BASH": 7, "CHAT": 5},
      "currently_running": 0,
      "stop_flag": false,
      "stop_reason": null
    },
    "token_usage": {
      "session_tokens": 45000,
      "tokens_percent": 22.5,
      "context_window": 200000,
      "tokens_remaining": 155000
    },
    "file_interactions": {
      "files_read": ["file1.py", "file2.py"],
      "files_written": ["newfile.py"],
      "files_edited": ["config.py"]
    },
    "ai_notes": ["<Note>", "..."],
    "todos": ["<TODO>", "..."],
    "recent_activities": ["<Activity>", "..."]
  }
}
```

#### GET /api/summary/export

Export summary to persistent markdown file for sharing with new sessions.

**Response:**
```json
{
  "success": true,
  "message": "Summary exported to persistent file",
  "filepath": "/path/to/acp_session_summary.md",
  "note": "Share this file with new AI sessions for context recovery"
}
```

#### GET /api/notes

Get all AI notes.

#### POST /api/notes/add

Add note for context recovery.

**Request:**
```json
{
  "category": "decision",
  "content": "Decided to use PostgreSQL instead of SQLite for scalability",
  "importance": "high"
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `category` | string | No | Note category (default: `context`) |
| `content` | string | Yes | Note content (max 500 chars) |
| `importance` | string | No | `normal` or `high` (default: `normal`) |

**Categories:**
- `decision`: Important decisions made
- `insight`: Key discoveries or insights
- `context`: Context that should be preserved
- `warning`: Issues or problems encountered
- `todo`: Things to remember to do

#### POST /api/notes/clear

Clear all AI notes.

### 4.7 File Manager Endpoints

#### GET /api/files/list

List directory contents.

**Headers:**
- `X-Path`: Relative path from base directory
- `X-Sort-By`: `name` | `date` | `size`
- `X-Sort-Dir`: `asc` | `desc`

#### GET /api/files/view

View file content (text files only, size limited).

**Headers:**
- `X-Path`: Relative path to file

**Response:**
```json
{
  "content": "file contents...",
  "path": "path/to/file.py",
  "lines": 150,
  "tokens": 450,
  "session_tokens": 45450
}
```

#### GET /api/files/download

Download file (binary safe).

**Query Parameters:**
- `path`: Relative path to file

#### GET /api/files/image

Get image file.

#### GET /api/files/stats

Get file statistics (total files, directories, size).

#### POST /api/files/upload

Upload file.

**Headers:**
- `X-Path`: Destination directory
- `X-Filename`: File name
- `Content-Type`: `application/octet-stream`

**Body:** Raw binary file content

#### POST /api/files/save

Save edited file.

**Request:**
```json
{
  "path": "path/to/file.py",
  "content": "updated content..."
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | Yes | Relative path to file |
| `content` | string | Yes | File content to save |

#### POST /api/files/delete

Delete file or directory.

**Request:**
```json
{
  "path": "path/to/delete"
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | Yes | Relative path to file or directory to delete |

#### POST /api/files/mkdir

Create directory.

**Request:**
```json
{
  "path": "parent/path",
  "name": "new_directory"
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | Yes | Parent directory path |
| `name` | string | Yes | New directory name |

#### POST /api/files/extract

Extract archive.

**Request:**
```json
{
  "path": "path/to/archive.zip"
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | Yes | Relative path to archive file |

**Supported formats:** `.zip`, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tbz2`, `.gz`, `.bz2`

#### POST /api/files/compress

Create zip archive.

**Request:**
```json
{
  "path": "directory/path",
  "name": "archive.zip",
  "items": ["file1.py", "file2.py", "subdir/"]
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | Yes | Base directory path |
| `name` | string | Yes | Archive filename (should end in `.zip`) |
| `items` | array | Yes | List of files/directories to include |

### 4.8 Duration Statistics API (v1.0.3)

#### GET /api/stats/duration

Get activity duration statistics for performance analysis.

**Response:**
```json
{
  "success": true,
  "stats": {
    "by_action": {
      "READ": {
        "count": 15,
        "total_ms": 45000,
        "average_ms": 3000,
        "average_str": "3.00s",
        "min_ms": 500,
        "max_ms": 10000
      },
      "WRITE": {...}
    },
    "slow_activities": [
      {
        "id": "143052-abc123",
        "action": "READ",
        "target": "/large/file.py",
        "duration_ms": 45000,
        "duration_str": "45.0s"
      }
    ],
    "total_duration_ms": 120000,
    "activities_with_duration": 25,
    "average_duration_ms": 4800,
    "slow_threshold_ms": 30000,
    "trend": [
      {"action": "READ", "duration_ms": 3000, "timestamp": "2025-03-14T16:00:00"},
      {...}
    ]
  },
  "slow_threshold_seconds": 30.0
}
```

**Fields:**
| Field | Description |
|-------|-------------|
| `by_action` | Duration statistics grouped by action type |
| `slow_activities` | List of activities exceeding 30 second threshold (max 10) |
| `total_duration_ms` | Sum of all activity durations |
| `activities_with_duration` | Count of activities with recorded duration |
| `average_duration_ms` | Overall average duration |
| `slow_threshold_ms` | Threshold for slow activity detection (30000ms) |
| `trend` | Last 20 activity durations for trend analysis |

**Use cases:**
- Identify performance bottlenecks
- Find slow operations for optimization
- Track activity duration trends over session

### 4.9 Batch Operations API (v1.0.3)

#### POST /api/activity/batch

Process multiple activity operations in a single atomic request.

**Request:**
```json
{
  "operations": [
    {"type": "start", "action": "READ", "target": "/file1.py", "content_size": 5000},
    {"type": "start", "action": "READ", "target": "/file2.py", "content_size": 3000},
    {"type": "complete", "activity_id": "prev-id-1", "result": "Completed"},
    {"type": "complete", "activity_id": "prev-id-2", "result": "Done"}
  ]
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `operations` | array | Yes | Array of operations (max 50) |
| `operations[].type` | string | Yes | Operation type: `start` or `complete` |
| `operations[].action` | string | Conditional | Action type (required for `start`) |
| `operations[].target` | string | No | Target for `start` operations |
| `operations[].activity_id` | string | Conditional | Activity ID (required for `complete`) |
| `operations[].result` | string | No | Result for `complete` operations |
| `operations[].content_size` | integer | No | Content size for token tracking |
| `operations[].metadata` | object | No | Metadata for activity |

**Response:**
```json
{
  "success": true,
  "results": [
    {"success": true, "operation": "start", "activity_id": "143100-abc123"},
    {"success": true, "operation": "start", "activity_id": "143100-def456"},
    {"success": true, "operation": "complete", "activity_id": "prev-id-1"},
    {"success": true, "operation": "complete", "activity_id": "prev-id-2"}
  ],
  "count": 4,
  "session_tokens": 45500,
  "context_window": 200000,
  "tokens_remaining": 154500
}
```

**Error handling:**
- If any operation fails, `success` is `false`, but all operations are attempted
- Each result includes `success` and `error` fields
- Maximum 50 operations per batch

**Use cases:**
- Log multiple file reads in one request
- Complete multiple activities atomically
- Reduce API overhead for bulk operations

### 4.10 System Endpoints

#### GET /api/system

Get CPU, RAM, Disk statistics.

**Response:**
```json
{
  "success": true,
  "system": {
    "cpu": {"percent": 45.2, "cores": 8},
    "ram": {"percent": 62.5, "used_gb": 10.0, "total_gb": 16.0},
    "disk": {"percent": 35.0, "used_gb": 1.2, "total_gb": 50.0}
  }
}
```

#### GET /api/session

Get session info (timeout, activity timestamps).

#### POST /api/session/refresh

Reset session timeout (extend session).

#### POST /api/restart

Restart the ACP server. Useful for applying configuration changes.

**Response:**
```json
{
  "success": true,
  "message": "Restarting..."
}
```

#### GET /api/csrf-token

Get CSRF token for POST requests. Also indicates whether CSRF protection is enabled.

**Response (CSRF enabled):**
```json
{
  "success": true,
  "csrf_enabled": true,
  "csrf_token": "1234567890:abc123...",
  "expires_in": 3600,
  "message": null
}
```

**Response (CSRF disabled - default):**
```json
{
  "success": true,
  "csrf_enabled": false,
  "csrf_token": null,
  "expires_in": null,
  "message": "CSRF protection is disabled. Token not required."
}
```

#### GET /api/whoami

Self-awareness endpoint for AI agents. Returns identity context to help agents understand their role and properly attribute activities.

**Response:**
```json
{
  "success": true,
  "identity": {
    "hint": "You are an AI agent. Identify yourself by name (e.g., 'Super Z', 'Claude', 'GPT-4').",
    "suggestion": "Use the 'agent_name' field in activity metadata to attribute your actions.",
    "example": {"metadata": {"agent_name": "Super Z", "source": "user_request"}},
    "purpose": "Attribution helps track which agent/subagent performed each action."
  },
  "primary_agent": "Super Z",
  "session": {"<SessionInfo>"}
}
```

**Response Fields:**
| Field | Description |
|-------|-------------|
| `identity` | Self-awareness context for the agent |
| `primary_agent` | **1.0.5** Name of the agent that owns the context window (first to log activity) |
| `session` | Current session information |

**When to call:**
- At session start to establish identity
- After context compression to re-establish context
- Before invoking subagents (to contrast agent names)

**Agent workflow integration:**
```
1. Call GET /api/whoami at session start
2. Check primary_agent to see if you own the context
3. Extract identity hint and determine agent_name
4. Include agent_name in all activity metadata:
   POST /api/action {"metadata": {"agent_name": "Super Z", ...}}
```

### 4.11 Nudge API (v1.0.2)

Synchronous nudges allow humans to provide mid-task guidance. Unlike WebSockets, nudges are delivered synchronously on the agent's next `/api/action` call.

#### POST /api/nudge

Create a nudge to be delivered on next action.

**Request:**
```json
{
  "message": "Focus on the API first",
  "priority": "high",
  "requires_ack": true
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `message` | string | Yes | Guidance message for the agent |
| `priority` | string | No | `normal` (default), `high`, or `urgent` |
| `requires_ack` | boolean | No | If true, agent must call `/api/nudge/ack` (default: true) |

**Response:**
```json
{
  "success": true,
  "nudge": {
    "message": "Focus on the API first",
    "priority": "high",
    "requires_ack": true,
    "timestamp": "2025-03-13T17:50:00",
    "from": "human",
    "acknowledged": false
  },
  "message": "Nudge queued for next action"
}
```

#### GET /api/nudge

Check if a nudge is pending.

**Response:**
```json
{
  "success": true,
  "nudge": {...},
  "has_pending": true
}
```

#### POST /api/nudge/ack

Acknowledge a nudge (clears it).

**Response:**
```json
{
  "success": true,
  "message": "Nudge acknowledged"
}
```

#### Nudge Delivery on /api/action

The nudge is delivered in the `/api/action` response:

```json
POST /api/action {"action": "READ", "target": "file.py"}
→ {
  "success": true,
  "activity_id": "...",
  "nudge": {
    "message": "Focus on the API first",
    "priority": "high",
    "requires_ack": true,
    "timestamp": "2025-03-13T17:50:00",
    "from": "human"
  }
}
```

**Agent workflow for nudges:**
```
1. Call POST /api/action
2. If response contains "nudge" field:
   a. Read the message
   b. Adjust behavior accordingly
   c. Call POST /api/nudge/ack (if requires_ack=true)
3. Continue with task
```

#### Primary Agent Delivery (1.0.5)

Nudges are delivered **only to the primary agent** (the first agent to log activity in a session). This prevents context pollution in multi-agent environments.

**Delivery Behavior:**

| Agent Type | `/api/action` Response |
|------------|------------------------|
| Primary Agent | `"nudge": {...}` if pending, else `null` |
| Secondary Agents | `"nudge": null` (always) |

**Why this matters:**
- Secondary agents (subagents, LocalClaw, etc.) don't receive nudges meant for the primary agent
- Prevents the same nudge from being added to every agent's context
- Ensures human guidance reaches only the intended agent

**Example:**
```
Session has:
  - primary_agent: "Super Z"
  - pending nudge: {"message": "Check the API first"}
  
Super Z calls /api/action:
  → nudge: {"message": "Check the API first"}  ✓

LocalClaw calls /api/action:
  → nudge: null  (not delivered)
```

### 4.12 Agent Registry API (1.0.4)

The Agent Registry provides agent discovery and presence tracking for multi-agent environments.

#### GET /api/agents

List all registered agents.

**Response:**
```json
{
  "success": true,
  "agents": [
    {
      "name": "Super Z",
      "capabilities": ["code-generation", "file-editing", "web-development"],
      "model_name": "gpt-4o",
      "endpoint": null,
      "status": "online",
      "registered_at": "2025-03-14T10:00:00",
      "last_seen": "2025-03-14T10:30:00",
      "tokens_used": 42000,
      "online": true
    },
    {
      "name": "LocalClaw",
      "capabilities": ["code-analysis", "file-reading"],
      "model_name": "qwen2.5-coder:0.5b",
      "endpoint": "http://localhost:8080",
      "status": "online",
      "registered_at": "2025-03-14T10:05:00",
      "last_seen": "2025-03-14T10:29:30",
      "tokens_used": 500,
      "online": true
    }
  ],
  "count": 2,
  "primary_agent": "Super Z"
}
```

**Fields:**
| Field | Description |
|-------|-------------|
| `agents` | Array of registered agent objects |
| `count` | Total number of registered agents |
| `primary_agent` | Name of the primary agent (owns context) |

#### GET /api/agents/{agent_name}

Get a specific agent by name.

**Response:**
```json
{
  "success": true,
  "agent": {
    "name": "Super Z",
    "capabilities": ["code-generation", "file-editing"],
    "model_name": "gpt-4o",
    "status": "online",
    "registered_at": "2025-03-14T10:00:00",
    "last_seen": "2025-03-14T10:30:00",
    "tokens_used": 42000,
    "online": true
  }
}
```

**Error Response:**
```json
{
  "success": false,
  "error": "Agent not found"
}
```

#### POST /api/agents/register

Register an agent with capabilities.

**Request:**
```json
{
  "agent_name": "LocalClaw",
  "capabilities": ["code-analysis", "file-reading"],
  "model_name": "qwen2.5-coder:0.5b",
  "endpoint": "http://localhost:8080"
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent_name` | string | Yes | Unique agent identifier |
| `capabilities` | array | No | List of capability strings |
| `model_name` | string | No | Model identifier |
| `endpoint` | string | No | Remote endpoint URL (for remote agents) |

**Response:**
```json
{
  "success": true,
  "agent": {
    "name": "LocalClaw",
    "capabilities": ["code-analysis", "file-reading"],
    "model_name": "qwen2.5-coder:0.5b",
    "endpoint": "http://localhost:8080",
    "status": "online",
    "registered_at": "2025-03-14T10:05:00",
    "last_seen": "2025-03-14T10:05:00",
    "tokens_used": 0
  },
  "message": "Agent 'LocalClaw' registered"
}
```

#### POST /api/agents/unregister

Unregister an agent.

**Request:**
```json
{
  "agent_name": "LocalClaw"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Agent 'LocalClaw' unregistered"
}
```

**Error Response:**
```json
{
  "success": false,
  "error": "Agent not found"
}
```

### 4.13 A2A Messaging API (1.0.4)

The A2A Messaging API enables lightweight inter-agent communication through a message queue pattern.

#### POST /api/a2a/send

Send a message to another agent.

**Request:**
```json
{
  "from_agent": "Super Z",
  "to_agent": "LocalClaw",
  "type": "request",
  "action": "analyze_file",
  "payload": {
    "file_path": "/project/main.py",
    "analysis_type": "complexity"
  },
  "priority": "high",
  "ttl": 3600,
  "reply_to": null
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `from_agent` | string | Yes | Sender agent name |
| `to_agent` | string | Yes | Recipient agent name |
| `type` | string | No | Message type: `request`, `response`, `notification` (default: `notification`) |
| `action` | string | No | Action identifier for requests |
| `payload` | object | No | Message data/parameters |
| `priority` | string | No | `normal`, `high`, `urgent` (default: `normal`) |
| `ttl` | integer | No | Time-to-live in seconds (default: 3600) |
| `reply_to` | string | No | Message ID this is replying to |

**Response:**
```json
{
  "success": true,
  "message": {
    "id": "143052-abc123",
    "from_agent": "Super Z",
    "to_agent": "LocalClaw",
    "type": "request",
    "action": "analyze_file",
    "payload": {
      "file_path": "/project/main.py",
      "analysis_type": "complexity"
    },
    "priority": "high",
    "created_at": "2025-03-14T10:30:00",
    "expires_at": "2025-03-14T11:30:00",
    "ttl": 3600
  }
}
```

#### GET /api/a2a/history

Get A2A message history.

**Query Parameters:**
| Parameter | Description |
|-----------|-------------|
| `from` | Filter by sender agent name |
| `to` | Filter by recipient agent name |
| `type` | Filter by message type |

**Response:**
```json
{
  "success": true,
  "messages": [
    {
      "id": "143052-abc123",
      "from_agent": "Super Z",
      "to_agent": "LocalClaw",
      "type": "request",
      "action": "analyze_file",
      "payload": {...},
      "priority": "high",
      "created_at": "2025-03-14T10:30:00",
      "expires_at": "2025-03-14T11:30:00",
      "ttl": 3600
    }
  ],
  "count": 1
}
```

**Example - Get messages sent to an agent:**
```
GET /api/a2a/history?to=LocalClaw
```

**Example - Get messages from a specific agent:**
```
GET /api/a2a/history?from=SuperZ
```

### A2A Message Flow Example

```
1. Agent registers:
   POST /api/agents/register {"agent_name": "LocalClaw", "capabilities": [...]}

2. Agent sends request:
   POST /api/a2a/send {
     "from_agent": "Super Z",
     "to_agent": "LocalClaw",
     "type": "request",
     "action": "analyze_code",
     "payload": {"file": "/project/app.py"}
   }

3. Recipient discovers message via A2A hints:
   POST /api/action {"action": "READ", "target": "...", "metadata": {"agent_name": "LocalClaw"}}
   → hints.a2a.pending_count = 1

4. Recipient retrieves message:
   GET /api/a2a/history?to=LocalClaw

5. Recipient processes and responds:
   POST /api/a2a/send {
     "from_agent": "LocalClaw",
     "to_agent": "Super Z",
     "type": "response",
     "reply_to": "143052-abc123",
     "payload": {"complexity_score": 42, "issues": [...]}
   }
```

### 4.14 JSON-RPC 2.0 API

ACP 1.0.4 adds JSON-RPC 2.0 support for A2A protocol compliance. REST remains the primary API; JSON-RPC is an adapter layer over existing functionality.

#### Endpoints

JSON-RPC requests are accepted at:
- `/jsonrpc`
- `/a2a`
- `/api/jsonrpc`

#### GET /.well-known/agent-card.json

A2A Agent Card discovery endpoint. Returns the server's Agent Card describing capabilities, skills, and authentication.

**Response:**
```json
{
  "name": "ACP Server",
  "description": "Agent Control Panel - Monitoring and observability server for AI agents",
  "url": "https://xxx.trycloudflare.com",
  "version": "1.0.4",
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
    },
    {
      "id": "a2a_messaging",
      "name": "A2A Messaging",
      "description": "Inter-agent communication via message queue",
      "tags": ["messaging", "multi-agent", "coordination"],
      "examples": ["Send message to another agent", "Check inbox"]
    }
  ],
  "authentication": {
    "schemes": ["Basic"]
  }
}
```

**Headers:**
- `Cache-Control: max-age=3600` - 1 hour cache
- `ETag: "<hash>"` - For conditional requests

#### JSON-RPC Request Format

**Single Request:**
```json
{
  "jsonrpc": "2.0",
  "method": "SendMessage",
  "params": {
    "message": {
      "contextId": "ctx-abc123",
      "parts": [{"text": "Analyze this file"}],
      "metadata": {"target_agent": "LocalClaw", "action": "analyze_file"}
    }
  },
  "id": "req-123"
}
```

**Batch Request:**
```json
[
  {"jsonrpc": "2.0", "method": "GetAgents", "params": {}, "id": "1"},
  {"jsonrpc": "2.0", "method": "status/get", "params": {}, "id": "2"}
]
```

#### JSON-RPC Response Format

**Success:**
```json
{
  "jsonrpc": "2.0",
  "result": {"task": {...}},
  "id": "req-123"
}
```

**Error:**
```json
{
  "jsonrpc": "2.0",
  "error": {"code": -32601, "message": "Method not found"},
  "id": "req-123"
}
```

#### JSON-RPC Methods

| Method | Description | Type |
|--------|-------------|------|
| `SendMessage` | Send message to agent | A2A Core |
| `GetTask` | Get task/activity by ID | A2A Core |
| `CancelTask` | Cancel running task | A2A Core |
| `GetAgents` | List agents with Agent Cards | A2A Discovery |
| `RegisterAgent` | Register agent with skills | A2A Discovery |
| `activity/start` | Start ACP activity | ACP-native |
| `activity/complete` | Complete ACP activity | ACP-native |
| `todos/get` | Get TODO list | ACP-native |
| `todos/update` | Update TODO list | ACP-native |
| `status/get` | Get session status | ACP-native |
| `nudge/set` | Set nudge message | ACP-native |
| `stop/set` | Set stop flag | ACP-native |
| `session/reset` | Reset session | ACP-native |

#### JSON-RPC Error Codes

| Code | Meaning | Description |
|------|---------|-------------|
| -32700 | Parse error | Invalid JSON received |
| -32600 | Invalid Request | Missing jsonrpc/method |
| -32601 | Method not found | Unknown method name |
| -32602 | Invalid params | Missing required parameter |
| -32603 | Internal error | Server-side error |
| -32001 | Task not found | Activity or task ID not found |
| -32002 | Task not running | Cannot cancel non-running task |
| -32003 | Stop requested | STOP ALL is active |

#### SendMessage Method

Sends a message to another agent. Uses flat parameters mapped from the A2A `SendMessage` method to ACP's internal message format.

**Request:**
```json
{
  "jsonrpc": "2.0",
  "method": "SendMessage",
  "params": {
    "from_agent": "Super Z",
    "to_agent": "LocalClaw",
    "type": "request",
    "action": "analyze_file",
    "payload": {"file_path": "/project/main.py"},
    "contextId": "ctx-abc123",
    "priority": "normal",
    "ttl": 3600,
    "reply_to": null
  },
  "id": "req-1"
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `to_agent` | string | Yes | Recipient agent name |
| `from_agent` | string | No | Sender agent name (default: `"Unknown"`) |
| `type` | string | No | `request`, `response`, or `notification` (default: `"request"`) |
| `action` | string | No | Action to perform (for requests) |
| `payload` | object | No | Message data/parameters |
| `contextId` | string | No | A2A context ID for multi-turn sessions |
| `priority` | string | No | `normal`, `high`, or `urgent` (default: `"normal"`) |
| `ttl` | integer | No | Time-to-live in seconds (default: `3600`) |
| `reply_to` | string | No | Message ID this is replying to |

**Response:**
```json
{
  "jsonrpc": "2.0",
  "result": {
    "id": "143052-abc123",
    "contextId": "ctx-abc123",
    "status": {
      "state": "COMPLETED",
      "timestamp": "2025-01-15T14:30:52"
    },
    "history": [],
    "artifacts": [],
    "metadata": {
      "action": "A2A",
      "target": "Super Z → LocalClaw",
      "tokens_in": 0,
      "tokens_out": 0
    }
  },
  "id": "req-1"
}
```

**Note:** ACP maps the standard A2A `SendMessage` method to flat parameters rather than the nested `message.parts` / `message.metadata` structure. Implementers may support either format; the flat format is the reference.

#### GetTask Method

Gets an ACP activity as an A2A Task.

**Request:**
```json
{
  "jsonrpc": "2.0",
  "method": "GetTask",
  "params": {"id": "143052-abc123"},
  "id": "req-2"
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "result": {
    "task": {
      "id": "143052-abc123",
      "contextId": "ctx-abc123",
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
  },
  "id": "req-2"
}
```

#### RegisterAgent Method

Registers an agent with AgentSkill objects.

**Request:**
```json
{
  "jsonrpc": "2.0",
  "method": "RegisterAgent",
  "params": {
    "agent_name": "LocalClaw",
    "description": "Local code analysis agent",
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
  },
  "id": "req-3"
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "result": {
    "agent_card": {
      "name": "LocalClaw",
      "description": "Local code analysis agent",
      "url": "http://localhost:8080",
      "version": "1.0.0",
      "skills": [...]
    },
    "message": "Agent 'LocalClaw' registered"
  },
  "id": "req-3"
}
```

#### A2A Task State Mapping

ACP activity status maps to A2A task states:

| ACP Status | A2A State | Description |
|------------|-----------|-------------|
| `running` | `RUNNING` | Task is currently executing |
| `completed` | `COMPLETED` | Task finished successfully |
| `error` | `FAILED` | Task encountered an error |
| `cancelled` | `CANCELED` | Task was cancelled |

---

## 5. Agent Workflow

### 5.0 Mandatory Integration Requirements

All agents using ACP **MUST**:

1. **Send bootstrap as FIRST message** - Every agent MUST log a bootstrap activity before any other ACP interaction
2. **Register with Agent Registry** - Register agent name and capabilities (1.0.4)
3. **Log every action** via `/api/action` BEFORE executing
4. **Log every shell command** via `/api/shell/add` AFTER executing
5. **Sync TODO state** via `/api/todos/update` when TODOs change
6. **Check stop flag** before starting any new activity
7. **Check A2A hints** for pending inter-agent messages (1.0.4)

**Bootstrap is MANDATORY for:**

| Scenario | Bootstrap Required |
|----------|-------------------|
| Session start | ✅ MANDATORY |
| Context resume | ✅ MANDATORY |
| Context reset | ✅ MANDATORY |
| New agent joining session | ✅ MANDATORY |
| Subagent spawn | ✅ MANDATORY |
| LocalClaw connecting | ✅ MANDATORY |

Failure to follow these requirements results in incomplete activity tracking,
inaccurate token estimation, and lost session history.

### 5.1 Mandatory Workflow

AI agents using ACP **MUST** follow this workflow:

```
┌─────────────────────────────────────────────────────────────────┐
│                    ACP AGENT WORKFLOW                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  0. BOOTSTRAP (MANDATORY - FIRST MESSAGE)                       │
│     GET /api/status  →  Check if ACP is running                 │
│     GET /api/whoami  →  Establish identity context              │
│     POST /api/agents/register → Register capabilities (1.0.4)  │
│     POST /api/action →  Log bootstrap activity:                 │
│       {"action": "CHAT", "target": "Session bootstrap",         │
│        "details": "Establishing agent identity",                │
│        "metadata": {"agent_name": "Super Z", "source": "bootstrap"}} │
│     This makes you primary agent if first to connect            │
│                                                                 │
│  1. CHECK STATUS                                                │
│     GET /api/status                                             │
│     If stop_flag == true, STOP IMMEDIATELY and inform user     │
│                                                                 │
│  2. LOG ACTION FIRST (before doing it!)                         │
│     POST /api/start {"action": "READ", "target": "/file.py"}   │
│     Returns: {"activity_id": "HHMMSS-abc123", "hints": {...}}  │
│     Check hints.a2a for pending messages (1.0.4)              │
│                                                                 │
│  3. NOW DO THE ACTION                                           │
│     Perform Read, Write, Edit, Bash, Skill invocation, etc.    │
│                                                                 │
│  4. LOG COMPLETION                                              │
│     POST /api/complete {"activity_id": "...", "result": "..."} │
│     Or: {"activity_id": "...", "error": "error message"}       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 Optimized Workflow (Single Request)

For efficiency, use the combined `/api/action` endpoint:

```
POST /api/action {
  "complete_id": "previous_activity_id",
  "result": "Previous action completed successfully",
  "action": "READ",
  "target": "/next/file.py",
  "details": "Reading next file",
  "metadata": {"agent_name": "Super Z"}
}
```

This single request:
1. Checks stop flag
2. Completes previous activity
3. Starts new activity
4. Returns updated token counts
5. Includes A2A hints for pending messages

### 5.3 Shell Command Logging (MANDATORY)

**All shell/terminal commands MUST be logged to ACP, EXCEPT ACP API calls.**

| Log These | Don't Log |
|-----------|-----------|
| `git clone`, `npm install`, `ls`, `python script.py` | `curl ... localhost:8766/api/...` (ACP calls) |
| `pip install`, `make build`, `docker run` | ACP communication is monitoring overhead |
| Any actual work command | |

**Why the exception?** ACP API calls (curl to localhost:8766) are the monitoring mechanism itself. Logging them would create recursive noise without value - they're not "work" being done, they're the reporting of work.

When running BASH commands, log to both Activity Monitor AND Shell History:

```
# Log to Activity Monitor
POST /api/start {"action": "BASH", "target": "npm install"}

# Also log to Terminal tab for visibility
POST /api/shell/add {
  "command": "npm install",
  "status": "running",
  "output_preview": ""
}

# Execute command...

# Update shell history
POST /api/shell/add {
  "command": "npm install",
  "status": "completed",
  "output_preview": "added 150 packages..."
}

# Complete activity
POST /api/complete {"activity_id": "...", "result": "Installed dependencies"}
```

### 5.4 TODO Synchronization (MANDATORY)

**TODO state must be synchronized with ACP.**

**At Session Start:**
```
GET /api/todos → Restore TODO state from previous session
```

**When TODOs Change:**
```
POST /api/todos/update {"todos": [...]}  # Full sync
```

**When Completing Task:**
```
POST /api/action {"action": "TODO", "target": "task_id", "details": "Marked completed"}
```

### 5.5 A2A Communication Workflow (1.0.4)

**Sending a message:**
```
1. Identify target agent: GET /api/agents
2. Send message: POST /api/a2a/send {"from_agent": "...", "to_agent": "...", ...}
3. Message is queued and delivered via A2A hints
```

**Receiving messages:**
```
1. Include agent_name in activity metadata
2. Check hints.a2a in response for pending_count
3. If pending_count > 0: GET /api/a2a/history?to=<my_name>
4. Process messages by type:
   - request: Perform action, send response
   - response: Handle response data
   - notification: Acknowledge and proceed
```

**Example - Request/Response pattern:**
```json
// Agent A sends request
POST /api/a2a/send {
  "from_agent": "Coordinator",
  "to_agent": "Analyzer",
  "type": "request",
  "action": "analyze_dependencies",
  "payload": {"project_path": "/project"}
}

// Agent B receives via hints and responds
POST /api/a2a/send {
  "from_agent": "Analyzer",
  "to_agent": "Coordinator",
  "type": "response",
  "reply_to": "original-msg-id",
  "payload": {"dependencies": [...], "issues": [...]}
}
```

---

## 6. Context Recovery

### 6.1 Purpose

Context recovery allows AI agents to restore session state after:
- Context window compression
- Session restart
- Container restart

### 6.2 Recovery Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                 CONTEXT RECOVERY WORKFLOW                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  AT SESSION START:                                              │
│  1. Check for acp_session_summary.md in upload directory       │
│  2. If found, read it for previous session context             │
│  3. Call GET /api/summary for current session state            │
│  4. Call GET /api/agents to see registered agents (1.0.4)    │
│                                                                 │
│  DURING SESSION:                                                │
│  - Save important notes: POST /api/notes/add                   │
│  - Mark high importance for critical items                      │
│  - Register with agent registry: POST /api/agents/register     │
│                                                                 │
│  BEFORE CONTEXT COMPRESSION:                                    │
│  - POST /api/summary/export to create persistent summary       │
│  - Share acp_session_summary.md with next session              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 6.3 Note Categories

| Category | When to Use | Example |
|----------|-------------|---------|
| `decision` | After making important decisions | "Chose PostgreSQL over SQLite for scalability" |
| `insight` | After discovering something important | "Bug in token estimation - use 3.5 chars/token" |
| `context` | Context that should be preserved | "User prefers functional programming style" |
| `warning` | After encountering issues | "Rate limiting on external API - use caching" |
| `todo` | Things to remember to do | "Need to refactor auth module next session" |

---

## 7. Security

### 7.1 Authentication

- HTTP Basic Authentication required for all endpoints
- Credentials configured via environment variables
- Rate limiting on failed authentication attempts

### 7.2 CSRF Protection

- CSRF protection is **optional** and **disabled by default**
- Enable via `GLMACP_CSRF_ENABLED=true` for production deployments
- When enabled, all POST requests require valid CSRF token
- Tokens expire after configurable timeout (default: 1 hour)
- Tokens are signed with server-side secret

### 7.3 Session Management

- Sessions have configurable timeout (default: 24 hours)
- Activity timestamp updated on each request
- Sessions can be refreshed explicitly

### 7.4 File Access

- Path traversal prevention (all paths must be within base directory)
- File size limits for viewing (configurable)
- Upload size limits (configurable)

### 7.5 Rate Limiting

- Failed authentication attempts tracked per IP
- Configurable window and max attempts
- Blocking cleared on successful authentication

---

## 8. Configuration

### 8.1 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GLMACP_PORT` | `8766` | Server port |
| `GLMACP_USER` | `admin` | Authentication username |
| `GLMACP_PASS` | `secret` | Authentication password |
| `GLMACP_DATA_FILE` | `./agent_activity.json` | Session state storage file path |
| `GLMACP_FILES_DIR` | *(script parent)* | Base directory for file manager |
| `GLMACP_SUMMARY_FILE` | `./acp_session_summary.md` | Context recovery summary file path |
| `GLMACP_QUIET` | `false` | Suppress server log output |
| `GLMACP_CSRF_ENABLED` | `false` | Enable CSRF protection (recommended for production) |
| `GLMACP_CSRF_SECRET` | *(random)* | CSRF signing secret |
| `GLMACP_SESSION_TIMEOUT` | `86400` | Session timeout in seconds |
| `GLMACP_STARTUP_TOKENS` | `3000` | Initial token overhead |
| `GLMACP_CONTEXT_WINDOW` | `200000` | LLM context window size |
| `GLMACP_MAX_UPLOAD_SIZE` | `104857600` | Max upload size (100MB) |
| `GLMACP_MAX_FILE_VIEW_SIZE` | `10485760` | Max file view size (10MB) |
| `GLMACP_TUNNEL` | `false` | **v1.0.3** Auto-start cloudflared tunnel (`auto`, `true`, `yes`) |
| `GLMACP_TUNNEL_URL` | *(none)* | **v1.0.3** Reuse existing tunnel URL |

### 8.2 Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `CONTEXT_WINDOW` | `200000` | LLM context window size |
| `MAX_HISTORY` | `100` | Maximum activity history entries |
| `MAX_NOTES` | `50` | Maximum AI notes |
| `MAX_SHELL_HISTORY` | `50` | Maximum shell history entries |
| `MAX_A2A_MESSAGES` | `100` | **1.0.4** Maximum A2A messages in queue |

### 8.3 Token Estimation

ACP estimates tokens using a character-based heuristic:

```python
def estimate_tokens(text: str) -> int:
    """Estimate tokens using ~3.5 characters per token."""
    return int(len(text) / 3.5)
```

This is tuned for mixed code/prose content and provides a conservative estimate.

### Token Sources

| Source | How Tracked | Notes |
|--------|-------------|-------|
| `/api/action` | Input tokens from action + target + details | Logged BEFORE executing |
| `/api/action` + `content_size` | **v1.0.1** Input tokens from native tool reads | Character count / 3.5 |
| `/api/complete` | Output tokens from result | Logged AFTER executing |
| `/api/complete` + `content_size` | **v1.0.1** Output tokens from native tool writes | Character count / 3.5 |
| `/api/files/view` | File content tokens | Deduplicated per session |

### 8.4 File Deduplication (v1.0.3)

**READ activities with `content_size` automatically deduplicate tokens** for files already read in the session. This prevents token inflation when agents re-read the same file multiple times.

**How it works:**
1. First READ of a file: Tokens counted normally, file path tracked in `files_read_tokens`
2. Subsequent READs of same file: `tokens_deduplicated: true`, content_size NOT counted again
3. Only counts minimal tokens (~4-5) for action/target strings

**Example:**
```json
// First read of /project/main.py
POST /api/action {
  "action": "READ",
  "target": "/project/main.py",
  "content_size": 10000
}
→ activity.tokens_in: 2861 (includes content)
→ activity.tokens_deduplicated: false

// Second read of same file
POST /api/action {
  "action": "READ",
  "target": "/project/main.py",
  "content_size": 10000
}
→ activity.tokens_in: 4 (minimal - content NOT counted)
→ activity.tokens_deduplicated: true
```

**Benefits:**
- Accurate token tracking for context window management
- Prevents token inflation from repeated file reads
- Session reset clears deduplication tracking

### 8.5 Native Tool Token Tracking (v1.0.1)

When agents use native tools (Read, Write, Edit) instead of ACP's `/api/files/*` endpoints, token tracking is not automatic. To ensure accurate tracking, include the `content_size` parameter:

**For READ operations:**
```json
POST /api/action {
  "action": "READ",
  "target": "/path/to/file.py",
  "content_size": 35000
}
```

**For WRITE/EDIT operations:**
```json
POST /api/complete {
  "activity_id": "abc123",
  "result": "File written",
  "content_size": 5000
}
```

**Combined workflow:**
```json
POST /api/action {
  "complete_id": "prev-id",
  "complete_content_size": 5000,
  "action": "READ",
  "target": "/next/file.py",
  "content_size": 35000
}
```

### 8.6 Remote Access via Cloudflared Tunnel (v1.0.3)

ACP can automatically start a cloudflared tunnel for public internet access, eliminating the need to run tunnel and ACP as separate processes.

**Configuration:**

| Variable | Value | Description |
|----------|-------|-------------|
| `GLMACP_TUNNEL` | `auto` | Auto-start cloudflared tunnel on server startup |
| `GLMACP_TUNNEL_URL` | *(optional)* | Reuse an existing tunnel URL instead of creating new |

**Usage:**

```bash
# Single command - ACP manages cloudflared as child process
GLMACP_TUNNEL=auto python3 VTSTech-GLMACP.py
```

**Output:**
```
🤖 Agent Control Panel R7-A2A starting on port 8766
   Auth: admin / secret
   Features: Activity Monitor + File Manager + System Stats + Theme Toggle + A2A
   🌐 Tunnel: https://xxx-xxx-xxx.trycloudflare.com
```

**API Response:**

The `tunnel_url` field is included in `/api/status` and `/api/all` responses:

```json
{
  "success": true,
  "tunnel_url": "https://xxx-xxx-xxx.trycloudflare.com",
  ...
}
```

**Process Management:**
- Cloudflared runs as a child process of ACP
- Automatic cleanup on server shutdown (Ctrl+C or `/api/shutdown`)
- Tunnel URL persists in API responses for agent/agent skill integration

**Requirements:**
- `cloudflared` binary installed in PATH or `~/.local/bin/`
- Internet connectivity for tunnel establishment

---

## 9. Implementation Guide

### 9.1 Server Implementation

A minimal ACP server requires:

1. **HTTP Server**: Handle REST API requests
2. **JSON Storage**: Persist session state
3. **File Access**: Browse workspace files
4. **Token Estimation**: Track context usage
5. **CSRF Protection**: Secure POST requests
6. **Agent Registry**: Track multi-agent presence (1.0.4)
7. **A2A Messaging**: Inter-agent communication queue (1.0.4)

### 9.2 Client Implementation

AI agents should implement:

1. **Status Check**: Call before each action
2. **Agent Registration**: Register name and capabilities at startup (1.0.4)
3. **Action Logging**: Log before executing
4. **Completion Logging**: Log after executing
5. **Error Handling**: Handle stop requests gracefully
6. **Context Recovery**: Save/load notes for session continuity
7. **A2A Integration**: Check hints for pending messages (1.0.4)

### 9.3 Reference Implementation

See `VTSTech-GLMACP.py` for a complete reference implementation in Python.

---

## Appendix A: Response Codes

| Code | Meaning |
|------|---------|
| `200` | Success |
| `400` | Bad Request (missing/invalid parameters) |
| `401` | Unauthorized (authentication required/failed) |
| `403` | Forbidden (invalid CSRF, stop requested) |
| `404` | Not Found (activity, file, endpoint, agent) |
| `413` | Payload Too Large (file size limit exceeded) |
| `429` | Too Many Requests (rate limited) |
| `500` | Internal Server Error |

---

## Appendix B: Changelog

### 1.0.6 (Current)
- **NEW**: `ACP-API.ts` — TypeScript type definition file providing AI-readable API types for all endpoints, request/response interfaces, enums, and data models
- **NEW**: `POST /api/todos/toggle` — Toggle a TODO item's status between pending and completed by ID
- **NEW**: `GET /api/nudge` — Check if a nudge is pending; returns `{nudge, has_pending}` for polling support
- **NEW**: `do_OPTIONS` CORS preflight handler — returns `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, and `Access-Control-Allow-Headers` headers for browser-based cross-origin requests
- **NEW**: `sanitize_path()` function — path traversal prevention using `os.path.realpath()` to validate all file endpoint paths remain within the configured base directory
- **NEW**: `last_agent` and `last_model` session metadata fields — track the most recent agent name and model identifier across all activities
- **NEW**: `shell_history` array in session state and `/api/all` response — persistent shell command history with command, timestamp, status, and output preview
- **NEW**: `GET /api/shell`, `POST /api/shell/add`, `POST /api/shell/clear` — Shell command history management endpoints
- **FIX**: Session State §3.1 `startup_applied` renamed to `startup_tokens` — resolves internal inconsistency with §4.3 API response
- **FIX**: `contexts` auto-created when SendMessage is called without `contextId` (spec §3.8 compliance)
- **FIX**: Agent Card URL now dynamically constructed from request headers (`Host`, `X-Forwarded-Proto`) instead of hardcoded empty string
- **FIX**: Path traversal vulnerability in file manager endpoints (`/api/files/list`, `/api/files/view`, `/api/files/download`, `/api/files/stats`) — all paths now validated against base directory
- **FIX**: `POST /api/nudge/ack` now clears the nudge by setting `d["nudge"] = None` instead of merely marking it `acknowledged`
- **FIX**: `/api/restart` now saves session state and flushes the HTTP response before calling `os.execv`, preventing data loss and connection reset errors
- **FIX**: Missing `import sys` — `/api/restart` crashed with `NameError` when calling `sys.executable`
- **FIX**: Undefined variable `sg` in A2A context creation — `/api/a2a/send` and JSON-RPC `SendMessage` crashed with `NameError`; corrected to `msg`
- **DOC**: Added Session Metadata Fields table documenting `last_agent` and `last_model`
- **DOC**: Updated `/api/all` response schema with `last_agent`, `last_model`, and `shell_history` fields
- **DOC**: Added `POST /api/todos/toggle` endpoint documentation with TypeScript interfaces in OpenAPI.yaml
- **DOC**: All files synchronized to v1.0.6 (acp-minimal.py, OpenAPI.yaml, ACP-API.ts, sub-agent-acp-template.md, README.md, SKILL.md)
- **SEC**: Path traversal prevention added to all file manager endpoints (§7.4 compliance)
- **SEC**: CORS preflight support enables browser-based API consumption from different origins

### 1.0.5
- **NEW**: `primary_agent` field in `/api/whoami` response - agents can check if they own the context
- **NEW**: Nudges delivered only to primary agent - prevents context pollution in multi-agent environments
- **NEW**: §4.11 Primary Agent Delivery section - documents nudge delivery behavior
- **DOC**: Updated `/api/whoami` response schema with `primary_agent` field
- **DOC**: Added Response Fields table to `/api/whoami` documentation
- **DOC**: Updated Agent workflow integration to include primary_agent check
- **FIX**: Secondary agents now receive `nudge: null` instead of duplicate nudges

### 1.0.4
- **NEW**: A2A Agent Registry API - agent discovery and presence tracking
- **NEW**: `POST /api/agents/register` - Register agent with capabilities
- **NEW**: `POST /api/agents/unregister` - Unregister an agent
- **NEW**: `GET /api/agents` - List all registered agents
- **NEW**: `GET /api/agents/{name}` - Get specific agent details
- **NEW**: A2A Messaging API - lightweight inter-agent communication
- **NEW**: `POST /api/a2a/send` - Send message to another agent
- **NEW**: `GET /api/a2a/history` - Get message history with filters
- **NEW**: `A2A` action type for inter-agent communication logging
- **NEW**: Agent Object in data model (name, capabilities, model_name, endpoint, status)
- **NEW**: A2A Message Object in data model (from_agent, to_agent, type, action, payload)
- **NEW**: A2A hints in activity response - notifies agents of pending messages
- **NEW**: `agents` and `a2a_messages` fields in session state
- **NEW**: `POST /api/reset` - Full session reset including agents and A2A messages
- **NEW**: Agent online status computed from last_seen timestamp (< 60s = online)
- **NEW**: POST /api/reset — Added a full session reset endpoint that clears all state, including agents and A2A messages, while resetting tokens to startup values.
- **NEW**: A2A Action Type — A new activity type that automatically logs inter-agent communication events, capturing the sender, recipient, and message type for audit history.
- **NEW**: A2A Context Support — Support for contextId mapping, enabling the grouping of related tasks into sessions for multi-turn inter-agent interactions.
- **NEW**: Agent Registry Data Models — Formalized the Agent, AgentSkill, and AgentCard objects to standardize how capabilities and status are discovered and shared across the network.
- **NEW**: A2A Message Schema — Defined the A2AMessage object, including mandatory fields for ttl (time-to-live), expires_at, and message priority.
- **NEW**: A2A Hints — Integration of pending message notifications directly into the hints field of /api/action and /api/complete responses.
- **NEW**: Multi-turn Interaction Tracking — Added A2AContext to the session state to track session-id to agent-activity mappings.
- **DOC**: Added §3.7 Agent Object section
- **DOC**: Added §3.8 A2A Message Object section
- **DOC**: Added §4.12 Agent Registry API section
- **DOC**: Added §4.13 A2A Messaging API section
- **DOC**: Added §5.5 A2A Communication Workflow section
- **DOC**: Updated architecture diagram to show A2A components
- **DOC**: Updated comparison table with Agent Registry and Inter-Agent Messaging
- **FIX**: Metadata model separation — Clarified the separation of agent_name (identity) and model_name (execution engine) within the standard metadata fields to improve UI filtering and usage tracking.
- **FIX**: Orphan Filtering — The orphan_warning logic now strictly filters tasks based on the agent_name provided in the request metadata, preventing agents from seeing each other's "stuck" tasks.
- **UI**: GLMACP displays registered agents with online status
- **UI**: A2A message indicator in activity responses


### v1.0.3
- **NEW**: `model_name` metadata field - separates agent identity from model identifier for clean UI display
- **NEW**: File Deduplication - READ activities track files already read, avoiding token double-counting
- **NEW**: `tokens_deduplicated` field in activity - indicates if tokens were skipped due to previous read
- **NEW**: `files_read_tokens` session data - tracks which files have been counted
- **NEW**: `GET /api/stats/duration` - activity duration statistics for performance analysis
- **NEW**: Duration stats by action type, slow activity detection, performance trends
- **NEW**: `POST /api/activity/batch` - process multiple activity operations in single request
- **NEW**: Batch `start` and `complete` operations for efficiency
- **NEW**: Built-in cloudflared tunnel support - auto-start with `GLMACP_TUNNEL=auto`
- **NEW**: `tunnel_url` field in `/api/status` and `/api/all` responses
- **NEW**: Per-agent token tracking - `primary_agent`, `agent_tokens`, `other_agents_tokens` fields
- **DOC**: Added `model_name` to Standard Metadata Fields table (§3.2.2)
- **DOC**: Added §4.8 Duration Statistics API section
- **DOC**: Added §4.9 Batch Operations API section
- **DOC**: Added §8.6 Remote Access via Cloudflared Tunnel section
- **DOC**: Updated token tracking to document deduplication behavior
- **DOC**: Documented `GLMACP_TUNNEL` and `GLMACP_TUNNEL_URL` environment variables
- **UI**: GLMACP renderActivity() displays `agent_name · model_name` format
- **UI**: Tunnel status display in sidebar with copy URL button

### v1.0.2
- **NEW**: Synchronous Nudge API - human guidance delivered on next `/api/action` call
- **NEW**: `POST /api/nudge` - Create mid-task guidance message
- **NEW**: `GET /api/nudge` - Check pending nudge status
- **NEW**: `POST /api/nudge/ack` - Acknowledge and clear nudge
- **NEW**: `nudge` field in `/api/action` response - delivers pending nudge synchronously
- **NEW**: Nudge priority levels: `normal`, `high`, `urgent`
- **NEW**: `requires_ack` option to block until acknowledged
- **NEW**: `orphan_warning` field in `/api/action` response - alerts about orphan running tasks
- **DOC**: Added §4.11 Nudge API section
- **DOC**: Added Orphan Warning documentation in §4.3
- **DOC**: Documented `GLMACP_DATA_FILE`, `GLMACP_FILES_DIR`, `GLMACP_SUMMARY_FILE`, `GLMACP_QUIET` environment variables
- **FIX**: Corrected `/api/summary/export` HTTP method from POST to GET in documentation
- **UI**: Added Nudge button and modal in GLMACP web interface

### v1.0.1
- **NEW**: `CHAT` action type for conversational/informational exchanges
- **NEW**: `content_size` parameter for `/api/start`, `/api/complete`, `/api/action`
- **NEW**: `complete_content_size` parameter for `/api/action` (combined endpoint)
- **NEW**: Activity `priority` field (`high` | `medium` | `low`)
- **NEW**: Activity `metadata` field for arbitrary key-value pairs
- **NEW**: `GET /api/activity/{id}` endpoint for single activity lookup
- **NEW**: `GET /api/whoami` endpoint for agent self-awareness and identity attribution
- **NEW**: Activity Hints - contextual information returned in `/api/action` response
- **NEW**: Standard metadata fields: `agent_name`, `source`, `tool_name`, `skill`
- **DOC**: Added §3.2.1 Priority Levels section
- **DOC**: Added §3.2.2 Metadata section with Standard Metadata Fields table
- **DOC**: Added §3.3.1 CHAT Action Type section
- **DOC**: Added §5.1 Session Start workflow step (whoami, summary, todos)
- **FIX**: Accurate token tracking for agents using native Read/Write/Edit tools
- **FIX**: Token tracking now captures cognitive work without tool execution
- **FIX**: File upload CSRF token missing (drag-drop and button upload)
- **DOC**: Added parameter tables to API endpoint documentation
- **DOC**: Updated architecture diagram to show `/api/action` as recommended endpoint
- **DOC**: Added CHAT to `activity_breakdown` example in `/api/summary` response
- **CHG**: CSRF protection now optional (disabled by default) - enable via `GLMACP_CSRF_ENABLED=true`

### v1.0.0
- Initial specification release
- Activity monitoring with LOG → DO → COMPLETE workflow
- Token estimation and context window tracking
- STOP ALL emergency control
- TODO management
- Shell history
- Context recovery with AI notes
- File manager with upload/download
- CSRF protection
- Session management with timeout
- Rate limiting

---

## License

MIT License - Free for personal and commercial use.

---

*This specification is maintained by VTSTech and the ACP community.*