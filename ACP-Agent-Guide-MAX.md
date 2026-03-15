# ACP Agent Quick Reference

**Version:** 1.0.4 | **Spec:** See [ACP-Specification.md](https://github.com/VTSTech/ACP-Agent-Control-Panel/blob/main/ACP-Specification.md) for full details

---

## 🧠 IF YOU REMEMBER NOTHING ELSE

```
┌─────────────────────────────────────────────────────────────────┐
│  THE ACP PATTERN (MEMORIZE THIS)                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐                 │
│   │   LOG    │ →  │ EXECUTE  │ →  │ COMPLETE │                 │
│   │/api/action│    │Tool/Bash │    │/api/complete│              │
│   └──────────┘    └──────────┘    └──────────┘                 │
│                                                                 │
│   BEFORE        NOW           AFTER                            │
│                                                                 │
│   ⚠️ NEVER execute before logging ⚠️                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Your mental state should always be:** "I have 0 running activities" between tasks.
If `activity_id` is set in your context, you MUST complete it before starting new work.

---

## 📋 QUICK DECISION TREE

```
┌─────────────────────────────────────────────────────────────────┐
│  WHAT SHOULD I DO RIGHT NOW?                                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Q: Is this a new session?                                      │
│     → Run: curl localhost:8766/api/status                       │
│     → If active, bootstrap: GET /api/whoami, POST register      │
│     → Restore: GET /api/todos, GET /api/summary                 │
│                                                                 │
│  Q: Am I about to use Read/Write/Edit/Bash/Grep/Glob/LS?        │
│     → STOP! POST /api/action FIRST, get activity_id             │
│     → Then execute the tool                                     │
│     → Then POST /api/complete                                   │
│                                                                 │
│  Q: Did I just finish an action?                                │
│     → POST /api/complete with result                            │
│     → Or use complete_id in next /api/action                    │
│                                                                 │
│  Q: Did I see stop_flag=true?                                   │
│     → STOP all work immediately                                 │
│     → Tell user, wait for resume                                │
│                                                                 │
│  Q: Did I see a nudge in the response?                          │
│     → Read it, adjust behavior                                  │
│     → If requires_ack=true, POST /api/nudge/ack                 │
│                                                                 │
│  Q: Did I see hints.a2a.pending_count > 0?                      │
│     → GET /api/a2a/history?to=<my_name>                         │
│     → Process pending messages from other agents                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## ⚠️ SESSION START PROTOCOL (DO THIS FIRST)

**Before doing ANYTHING else in this session:**

```
┌─────────────────────────────────────────────────────────────────┐
│  SESSION START CHECKLIST (MANDATORY)                            │
├─────────────────────────────────────────────────────────────────┤
│  1. Check if ACP server is running:                             │
│     curl -s -u admin:secret http://localhost:8766/api/status    │
│                                                                 │
│  2. Establish identity:                                         │
│     GET /api/whoami                                             │
│                                                                 │
│  3. Register with Agent Registry (v1.0.4):                      │
│     POST /api/agents/register {"agent_name": "...", ...}        │
│                                                                 │
│  4. Log bootstrap activity:                                     │
│     POST /api/action {"action": "CHAT", "target": "bootstrap"}  │
│                                                                 │
│  5. If running, you MUST follow ACP Workflow for ALL actions    │
│  6. If not running, proceed normally (no ACP integration)       │
└─────────────────────────────────────────────────────────────────┘
```

**ACP is ACTIVE if:** Response contains `{"success": true, ...}`  
**ACP is INACTIVE if:** Connection refused or no response

---

## 🔌 SESSION END PROTOCOL

**Trigger phrases from user:**
- "End this session"
- "We're done for now"
- "Kill ACP"
- "Shutdown"

**When you hear these, the human may use the SHUTDOWN button in the ACP UI.**

**What happens on shutdown:**
```
1. Server exports session summary (for next session recovery)
2. All running activities are cancelled
3. You receive a shutdown nudge with type: "shutdown"
4. Server stops after 2 seconds
```

**Your response to shutdown:**
```bash
# If you see a nudge with type: "shutdown":
# 1. Acknowledge it
POST /api/nudge/ack {}
→ {"success": true, "message": "Nudge acknowledged"}

# 2. Inform user that session is ending
"The ACP session has ended. The server has stopped."

# 3. DO NOT attempt any more actions via ACP
# The server is no longer running
```

**Important:** After shutdown, don't try to log more actions. The server is gone.

---

## 🔄 EVERY-ACTION TRIGGER (MOST IMPORTANT SECTION)

**This section is the core of ACP integration. Read it twice.**

```
┌─────────────────────────────────────────────────────────────────┐
│  🛑 STOP! READ THIS BEFORE EVERY ACTION 🛑                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  BEFORE using Read/Write/Edit/Bash/Grep/Glob/LS:                │
│                                                                 │
│  □ STEP 1: POST /api/action {"action": "READ|WRITE|EDIT|BASH",  │
│           "target": "...", "details": "...",                    │
│           "metadata": {"agent_name": "..."}}                    │
│  □ STEP 2: Receive activity_id from response                    │
│  □ STEP 3: Check hints.a2a for pending messages (v1.0.4)        │
│  □ STEP 4: NOW execute the tool (Read/Write/Edit/Bash)          │
│  □ STEP 5: POST /api/complete {"activity_id": "...", "result":  │
│           "..."}                                               │
│                                                                 │
│  ⚠️ STEPS 1-3 MUST happen BEFORE STEP 4 ⚠️                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### The Combined Pattern (Recommended)

Use `complete_id` to chain activities - complete previous AND start new in one call:

```bash
POST /api/action {
  "complete_id": "prev_activity_id",   # Complete previous (if any)
  "result": "Previous result",
  "action": "READ",                     # New action
  "target": "/path/to/file",
  "details": "Purpose of this action",
  "metadata": {"agent_name": "Super Z"}
}
→ {activity_id, stop_flag, session_tokens, hints}
```

This pattern ensures you never forget to complete - it's automatic!

---

## ❌ COMMON MISTAKES (AVOID THESE)

| Mistake | What Happens | Correct Approach |
|---------|--------------|------------------|
| **Forgetting to log before executing** | Activity not tracked, tokens inaccurate | ALWAYS call `/api/action` BEFORE using Read/Write/Edit/Bash |
| **Using native tools without logging** | Context window estimation wrong | Include `content_size` parameter |
| **Starting work without checking ACP status** | May miss stop_flag or nudge | Check `/api/status` at session start |
| **Not completing activities** | Orphan tasks pile up | Always call `/api/complete` when done |
| **Multiple agents without attribution** | Can't tell who did what | Use `agent_name` in metadata |
| **Ignoring A2A hints** (v1.0.4) | Miss messages from other agents | Check `hints.a2a` in every response |
| **Not registering with Agent Registry** (v1.0.4) | Not discoverable for A2A | `POST /api/agents/register` at startup |

---

## MANDATORY INTEGRATION REQUIREMENTS

**All agents using ACP MUST:**

1. **Log bootstrap as FIRST message** - Every agent MUST send bootstrap before any other ACP interaction
2. **Register with Agent Registry** - Register agent name and capabilities (v1.0.4)
3. **Log every action** via `/api/action` BEFORE executing
4. **Log every shell command** via `/api/shell/add` AFTER executing
5. **Sync TODO state** via `/api/todos/update` when TODOs change
6. **Check stop flag** before starting any new activity
7. **Check A2A hints** for pending inter-agent messages (v1.0.4)

---

## ACTIVITY LOGGING (MANDATORY)

### Basic Workflow

```
1. CHECK STATUS → GET /api/status (if stop_flag=true, STOP)
2. LOG ACTION   → POST /api/action {action, target, details, content_size, metadata}
3. CHECK A2A    → hints.a2a.pending_count > 0? GET /api/a2a/history (v1.0.4)
4. EXECUTE      → Do the action
5. COMPLETE     → POST /api/complete {activity_id, result, content_size}
```

### Combined Workflow (Recommended)

```bash
# Complete previous + start new in ONE call
POST /api/action {
  "complete_id": "prev_activity_id",   # Complete previous
  "result": "Previous result here",     # Previous result
  "complete_content_size": 5000,        # v1.0.1: Chars written in prev
  "action": "READ",                     # New action
  "target": "/path/to/file",
  "details": "Purpose of this action",
  "content_size": 35000,                # v1.0.1: Chars to be read
  "metadata": {"agent_name": "Super Z"}
}
→ {activity_id, stop_flag, session_tokens, tokens_remaining, hints}
```

### Action Types

| Type | When to Use | Token Impact |
|------|-------------|--------------|
| `READ` | Reading files, API GETs, viewing content | Input tokens |
| `WRITE` | Creating new files | Output tokens |
| `EDIT` | Modifying existing files | Output tokens |
| `BASH` | Terminal commands, CLI tools | Count command + output |
| `SKILL` | Invoking skills (VLM, TTS, etc.) | Varies |
| `API` | External API calls | Request + response |
| `SEARCH` | Web search, grep, find | Query + results |
| `TODO` | TODO state changes | Minimal |
| `CHAT` | Conversational exchanges, Q&A, planning | Input tokens |
| `A2A` | **v1.0.4** Agent-to-agent communication | Minimal |

### Nudge Handling (v1.0.2)

Check for nudges in every `/api/action` response. Humans can send synchronous guidance:

```bash
POST /api/action {"action": "READ", "target": "file.py"}
→ {
    "activity_id": "...",
    "nudge": {                    # ← Check this field!
      "message": "Focus on the API first",
      "priority": "high",
      "requires_ack": true,
      "from": "human"
    }
  }
```

**When nudge received:**
```bash
# 1. Read the message and adjust behavior
# 2. If requires_ack=true, acknowledge it:
POST /api/nudge/ack {}
→ {"success": true}
```

**Why it matters:** Unlike async WebSockets, nudges are delivered synchronously on your next API call - you WILL see them. Use them for mid-task course corrections from humans.

### Activity Priority (v1.0.1)

Mark activities with priority for better organization:

```bash
POST /api/action {
  "action": "READ",
  "target": "/critical/config.py",
  "priority": "high"  # high | medium (default) | low
}
```

### Activity Metadata (v1.0.1)

Attach arbitrary context to activities:

```bash
POST /api/action {
  "action": "READ",
  "target": "/file.py",
  "metadata": {
    "agent_name": "Super Z",      # Who performed this action
    "model_name": "gpt-4o",       # v1.0.3: Model identifier
    "source": "user_request",     # Origin of action
    "file_hash": "abc123",
    "related_to": "issue-42"
  }
}

# Metadata can be added on complete too
POST /api/complete {
  "activity_id": "abc123",
  "result": "Done",
  "metadata": {"bytes_written": 5000}
}
```

**Standard metadata fields:**

| Field | Description | Example |
|-------|-------------|---------|
| `agent_name` | Name of agent/subagent | `"Super Z"`, `"LocalClaw"` |
| `model_name` | **v1.0.3** Model identifier | `"qwen2.5-coder:0.5b-instruct-q4_k_m"`, `"gpt-4o"` |
| `source` | Origin of action | `"user_request"`, `"auto"`, `"subagent"` |
| `tool_name` | Native tool used | `"Read"`, `"Write"`, `"Bash"` |
| `skill` | Skill invoked (SKILL actions) | `"image-generation"` |

### Example: File Read

```bash
# 1. Log the action FIRST
POST /api/action {
  "action": "READ",
  "target": "/src/config.py",
  "details": "Loading application configuration",
  "priority": "high",
  "content_size": 5000,
  "metadata": {"agent_name": "Super Z"}
}
→ {"activity_id": "143052-a1b2c3", "hints": {...}}

# 2. Execute the read
[Use native Read tool to read /src/config.py]

# 3. Complete the activity
POST /api/complete {
  "activity_id": "143052-a1b2c3",
  "result": "Read 150 lines, found 3 config sections"
}
```

---

## A2A AGENT REGISTRY (v1.0.4)

### Overview

The Agent Registry enables multi-agent discovery and presence tracking. Every agent MUST register at startup.

### Register Agent

```bash
POST /api/agents/register {
  "agent_name": "Super Z",
  "capabilities": ["code-generation", "file-editing", "web-development"],
  "model_name": "gpt-4o",
  "endpoint": "http://localhost:8080"  # Optional, for remote agents
}
→ {
  "success": true,
  "agent": {
    "name": "Super Z",
    "capabilities": [...],
    "status": "online",
    "registered_at": "2025-03-14T10:00:00",
    "last_seen": "2025-03-14T10:00:00"
  }
}
```

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

### Unregister Agent

```bash
POST /api/agents/unregister {"agent_name": "LocalClaw"}
→ {"success": true, "message": "Agent 'LocalClaw' unregistered"}
```

---

## A2A MESSAGING (v1.0.4)

### Overview

A2A Messaging enables lightweight inter-agent communication through a message queue pattern.

### Send Message

```bash
POST /api/a2a/send {
  "from_agent": "Super Z",
  "to_agent": "LocalClaw",
  "type": "request",           # request | response | notification
  "action": "analyze_file",    # Action identifier
  "payload": {
    "file_path": "/project/main.py",
    "analysis_type": "complexity"
  },
  "priority": "high",          # normal | high | urgent
  "ttl": 3600                  # Time-to-live in seconds
}
→ {
  "success": true,
  "message": {
    "id": "143052-abc123",
    "from_agent": "Super Z",
    "to_agent": "LocalClaw",
    "type": "request",
    "action": "analyze_file",
    "created_at": "2025-03-14T10:30:00",
    "expires_at": "2025-03-14T11:30:00"
  }
}
```

### Get Message History

```bash
# All messages
GET /api/a2a/history

# Messages to specific agent
GET /api/a2a/history?to=LocalClaw

# Messages from specific agent
GET /api/a2a/history?from=SuperZ

# Filter by type
GET /api/a2a/history?type=request
```

### A2A Hints (Automatic Notification)

When you include `agent_name` in activity metadata, A2A hints notify you of pending messages:

```bash
POST /api/action {"action": "READ", "target": "file.py", "metadata": {"agent_name": "LocalClaw"}}
→ {
  "activity_id": "...",
  "hints": {
    "a2a": {
      "pending_count": 3,
      "senders": ["Super Z", "DataProcessor"],
      "preview": {
        "from": "Super Z",
        "action": "file_analysis_complete",
        "msg_id": "143000-xyz789"
      }
    }
  }
}
```

**Agent workflow for A2A hints:**
```
1. Check hints.a2a in response
2. If pending_count > 0:
   a. GET /api/a2a/history?to=<my_agent_name>
   b. Process each message based on type and action
   c. Send response if needed via POST /api/a2a/send
3. Continue with task
```

### A2A Message Flow Example

```
1. Agent registers: POST /api/agents/register
2. Agent sends request: POST /api/a2a/send {"type": "request", ...}
3. Recipient discovers via hints.a2a.pending_count
4. Recipient retrieves: GET /api/a2a/history?to=<name>
5. Recipient processes and responds: POST /api/a2a/send {"type": "response", ...}
```

---

## SHELL LOGGING (MANDATORY)

**Log ALL shell/terminal commands EXCEPT ACP API calls.**

| Log These | Don't Log |
|-----------|-----------|
| `git clone`, `npm install`, `ls`, `python script.py` | `curl ... localhost:8766/api/...` (ACP calls) |
| `pip install`, `make build`, `docker run` | ACP communication is monitoring overhead |
| Any actual work command | |

### Pipelines with ACP Calls

When a command pipeline mixes ACP calls with processing, split them:

**Don't:**
```bash
curl localhost:8766/api/history | python3 -c "import json; ..."  # Mixed - unclear what to log
```

**Do:**
```bash
# Step 1: ACP call (don't log)
curl localhost:8766/api/history > /tmp/data.json

# Step 2: Process data (LOG THIS)
python3 -c "import json; d=json.load(open('/tmp/data.json')); print(len(d['history']))"
# → POST /api/shell/add {"command": "python3 -c ...", "status": "completed", ...}
```

**Why split?** Separating ACP calls from work makes Terminal history cleaner and shows actual agent activity.

### Workflow

```
1. LOG ACTION   → POST /api/action {action: "BASH", target: "<command>"}
2. EXECUTE      → Run the command
3. LOG SHELL    → POST /api/shell/add {command, status, output_preview}
4. COMPLETE     → POST /api/complete {activity_id, result}
```

### Shell Log Format

```bash
POST /api/shell/add {
  "command": "npm install express",
  "status": "completed",        # "running" | "completed" | "error"
  "output_preview": "added 57 packages in 3s",  # First 200 chars
  "metadata": {"agent_name": "Super Z"}
}
```

---

## TODO SYNC (MANDATORY)

**TODO state must be synchronized with ACP.**

### Session Start

```bash
# 1. Establish identity (optional but recommended)
GET /api/whoami
→ {"identity": {"hint": "You are an AI agent. Identify yourself..."}}

# 2. Restore TODO state from ACP
GET /api/todos
→ {"todos": [{"id": "1", "content": "Task 1", "status": "pending"}, ...]}
```

### Agent Identity (v1.0.1)

Use `agent_name` in metadata to attribute actions to yourself:

```bash
POST /api/action {
  "action": "READ",
  "target": "/file.py",
  "metadata": {
    "agent_name": "Super Z",     # Your identity
    "source": "user_request"     # Origin of action
  }
}
```

**Why it matters:** In multi-agent scenarios or when invoking subagents, attribution helps track who did what. Call `/api/whoami` at session start to establish identity context.

### TODO State Changes

```bash
# Full sync (replace all)
POST /api/todos/update {
  "todos": [
    {"id": "1", "content": "Task 1", "status": "completed"},
    {"id": "2", "content": "Task 2", "status": "in_progress"}
  ]
}

# Add single TODO
POST /api/todos/add {
  "todo": {"content": "New task", "status": "pending", "priority": "high"},
  "agent_name": "Super Z"
}

# Clear completed
POST /api/todos/clear
```

---

## STOP ALL HANDLING

If `stop_flag=true` in any response:

1. **STOP** all work immediately
2. **DO NOT** start new activities
3. **INFORM** user of stop reason
4. **WAIT** for user to clear stop flag or provide new instructions

```bash
# User clears stop flag
POST /api/resume
→ {"success": true, "message": "Resumed"}
```

---

## TOKEN TRACKING

| Metric | Value | Notes |
|--------|-------|-------|
| Context Window | 200,000 tokens | Configurable via GLMACP_CONTEXT_WINDOW |
| Startup Overhead | ~3,000 tokens | Session initialization cost |
| Estimation | 3.5 chars/token | Conservative for code |
| Warning Threshold | 90% usage | `overflow_warning` in response |

### Token Sources

| Source | How Tracked |
|--------|-------------|
| `/api/action` | Input tokens from action + target + details |
| `/api/action` + `content_size` | **v1.0.1** Native tool reads (chars / 3.5) |
| `/api/complete` | Output tokens from result |
| `/api/complete` + `content_size` | **v1.0.1** Native tool writes (chars / 3.5) |
| `/api/files/view` | File content tokens (deduplicated per session) |

### File Deduplication (v1.0.3)

**READ activities with `content_size` automatically deduplicate** tokens for files already read:

```bash
# First read of file.py
POST /api/action {"action": "READ", "target": "/file.py", "content_size": 10000}
→ tokens_in: 2861 (includes content)

# Second read of same file
POST /api/action {"action": "READ", "target": "/file.py", "content_size": 10000}
→ tokens_in: 4 (minimal - content NOT counted again)
→ activity.tokens_deduplicated: true
```

**Why it matters:** Re-reading files won't inflate your token count. Session reset clears deduplication tracking.

### Per-Agent Token Tracking

**Context Isolation:** The first agent to log an activity becomes the "primary agent" and owns the main context. Other agents (subagents, LocalClaw, etc.) are tracked separately.

**Status Response:**
```bash
GET /api/status
→ {
    "session_tokens": 52529,        # Primary agent's context only
    "primary_agent": "Super Z",     # Who owns the context
    "agent_tokens": {
      "Super Z": 84,                # Primary agent tokens
      "LocalClaw": 93               # Other agent tokens (not in session_tokens)
    },
    "other_agents_tokens": 93       # Sum of non-primary tokens
  }
```

**Why it matters:** Subagents and other agents won't pollute your context window estimation. You get accurate context tracking for the primary agent only.

---

## CONTEXT RECOVERY

### Session Start

```bash
1. Read acp_session_summary.md if present
2. GET /api/summary     # Condensed session state
3. GET /api/todos       # Restore TODO state
4. GET /api/notes       # Review saved notes
5. GET /api/agents      # See registered agents (v1.0.4)
```

### Before Context Compression

```bash
1. POST /api/notes/add  # Save decisions, insights, warnings
2. POST /api/summary/export  # Export to markdown
3. Share acp_session_summary.md with next session
```

### Note Categories

| Category | Use For | Example |
|----------|---------|---------|
| `decision` | Important choices | "Using PostgreSQL over MySQL for X reason" |
| `insight` | Key discoveries | "API rate limit is 100/min, not 1000" |
| `context` | Preserve state | "User prefers tabs over spaces" |
| `warning` | Issues found | "auth.py has deprecated function call" |
| `todo` | Future tasks | "Remember to update docs after deploy" |

---

## AUTHENTICATION

```bash
# HTTP Basic Auth
Authorization: Basic base64(user:pass)

# CSRF Token (optional - check if enabled)
X-CSRF-Token: <timestamp>:<signature>

# Check CSRF status and get token
GET /api/csrf-token
→ {"csrf_enabled": true, "csrf_token": "1234567890:abc123...", "expires_in": 3600}
# OR if disabled:
→ {"csrf_enabled": false, "message": "CSRF protection is disabled. Token not required."}
```

**Note:** CSRF protection is **disabled by default** for development convenience. Check `/api/csrf-token` to determine if tokens are required.

---

## ERROR RESPONSES

| Code | Meaning | Action |
|------|---------|--------|
| 401 | Auth failed | Check credentials, retry |
| 403 | Stop requested / Invalid CSRF (if enabled) | STOP if stop_flag, else refresh CSRF |
| 404 | Not found | Activity, file, or agent doesn't exist |
| 413 | File too large | Use download instead of view |
| 429 | Rate limited | Wait before retrying |

---

## COMPLETE EXAMPLE SEQUENCE

```bash
# === SESSION START ===
→ GET /api/whoami
← {identity: {hint: "You are an AI agent. Identify yourself..."}}

→ GET /api/status
← {stop_flag: false, tokens_percent: 15}

→ POST /api/agents/register {"agent_name": "Super Z", "capabilities": ["code-generation"]}
← {success: true, agent: {...}}

→ POST /api/action {"action": "CHAT", "target": "Session bootstrap", "metadata": {"agent_name": "Super Z", "source": "bootstrap"}}
← {activity_id: "143000-boot01"}

→ GET /api/todos
← {todos: [{"id": "1", "content": "Review code", "status": "pending"}]}

→ GET /api/agents
← {agents: [...], count: 1, primary_agent: "Super Z"}

# === FILE READ ===
→ POST /api/action {"action": "READ", "target": "config.py", "details": "Load config", "metadata": {"agent_name": "Super Z"}}
← {activity_id: "143052-a1b2c3", stop_flag: false, hints: {...}}

→ [Read config.py using native tool]

→ POST /api/complete {"activity_id": "143052-a1b2c3", "result": "50 lines, 3 sections"}
← {success: true}

# === SHELL COMMAND ===
→ POST /api/action {"action": "BASH", "target": "pip install requests", "details": "Install dependency"}
← {activity_id: "143055-d4e5f6"}

→ [Execute: pip install requests]

→ POST /api/shell/add {"command": "pip install requests", "status": "completed", "output_preview": "Successfully installed"}
← {success: true}

→ POST /api/complete {"activity_id": "143055-d4e5f6", "result": "requests 2.31.0 installed"}
← {success: true}

# === A2A MESSAGING (v1.0.4) ===
→ POST /api/a2a/send {"from_agent": "Super Z", "to_agent": "LocalClaw", "type": "request", "action": "analyze", "payload": {...}}
← {success: true, message: {...}}

# (Later, when LocalClaw responds)
→ POST /api/action {"action": "READ", "target": "...", "metadata": {"agent_name": "Super Z"}}
← {hints: {a2a: {pending_count: 1, senders: ["LocalClaw"]}}}

→ GET /api/a2a/history?to=SuperZ
← {messages: [{from_agent: "LocalClaw", type: "response", ...}]}

# === TODO UPDATE ===
→ POST /api/todos/update {"todos": [{"id": "1", "content": "Review code", "status": "completed"}]}
← {success: true}

# === CONTEXT RECOVERY (before compression) ===
→ POST /api/notes/add {"category": "decision", "content": "Chose REST over GraphQL", "importance": "high"}
← {success: true}

→ POST /api/summary/export
← {filepath: "/home/z/my-project/upload/acp_session_summary.md"}
```

---

## FILES

| File | Purpose |
|------|---------|
| `ACP-Specification.md` | Full specification (human-readable) |
| `ACP-Agent-Guide-MIN.md` | Quick reference (minimal) |
| `ACP-Agent-Guide-MAX.md` | This file (detailed) |
| `acp_session_summary.md` | Persistent session state |
| `agent_activity.json` | Session data storage |
| `acp_restart.log` | Restart debugging logs |

---

## QUICK REFERENCE CARD

```
┌─────────────────────────────────────────────────────────────┐
│  ACP MANDATORY CHECKLIST                                     │
├─────────────────────────────────────────────────────────────┤
│  □ Register with Agent Registry at startup (v1.0.4)         │
│  □ Log bootstrap activity as FIRST message                   │
│  □ Check status before starting (GET /api/status)           │
│  □ Log action BEFORE executing (POST /api/action)           │
│  □ Check hints.a2a for pending messages (v1.0.4)            │
│  □ Include content_size for native tools (v1.0.1)           │
│  □ Include agent_name and model_name in metadata            │
│  □ Log shell commands AFTER executing (POST /api/shell/add) │
│  □ Complete activity when done (POST /api/complete)         │
│  □ Sync TODOs on change (POST /api/todos/update)            │
│  □ Save notes for recovery (POST /api/notes/add)            │
│  □ Export summary before compression                        │
└─────────────────────────────────────────────────────────────┘
```

---

## APPENDIX: VERSION FEATURES

### v1.0.4 Features

```
┌─────────────────────────────────────────────────────────────┐
│  NEW IN v1.0.4                                               │
├─────────────────────────────────────────────────────────────┤
│  • A2A Agent Registry API - agent discovery/tracking        │
│  • POST /api/agents/register - Register with capabilities   │
│  • POST /api/agents/unregister - Remove from registry       │
│  • GET /api/agents - List all registered agents             │
│  • A2A Messaging API - inter-agent communication            │
│  • POST /api/a2a/send - Send message to another agent       │
│  • GET /api/a2a/history - Get message history               │
│  • A2A action type for communication logging                │
│  • hints.a2a field - notification of pending messages       │
│  • POST /api/reset - Full session reset (agents + A2A)      │
│  • Agent online status (last_seen < 60s)                    │
│  • Primary agent owns context window                        │
│  • Per-agent token tracking in agent_tokens{}               │
└─────────────────────────────────────────────────────────────┘
```

### v1.0.3 Features

```
┌─────────────────────────────────────────────────────────────┐
│  NEW IN v1.0.3                                               │
├─────────────────────────────────────────────────────────────┤
│  • model_name metadata field - separate agent from model     │
│  • File Deduplication: READ auto-skips tokens for re-reads   │
│  • tokens_deduplicated field in activity                     │
│  • GET /api/stats/duration - Performance analysis            │
│  • Slow activity detection (>30s threshold)                  │
│  • POST /api/activity/batch - Bulk operations                │
│  • Max 50 operations per batch                               │
│  • Performance trend tracking (last 20 activities)           │
└─────────────────────────────────────────────────────────────┘
```

### v1.0.2 Features

```
┌─────────────────────────────────────────────────────────────┐
│  NEW IN v1.0.2                                               │
├─────────────────────────────────────────────────────────────┤
│  • Nudge API: Human guidance via /api/nudge                  │
│  • Synchronous delivery: nudge field in /api/action response │
│  • POST /api/nudge/ack - Acknowledge received nudges         │
│  • Priority levels: normal | high | urgent                   │
│  • requires_ack: Block until agent acknowledges              │
│  • orphan_warning: Detects running tasks before starting new │
│  • TODO/Shell metadata: agent_name, tool, skill attribution  │
│  • Per-agent tokens: primary_agent, agent_tokens{}           │
│  • Context isolation from subagents and other agents         │
│  • POST /api/shutdown: Graceful session termination          │
│  • Shutdown nudge: type: "shutdown" notifies agent           │
└─────────────────────────────────────────────────────────────┘
```

### v1.0.1 Features

```
┌─────────────────────────────────────────────────────────────┐
│  NEW IN v1.0.1                                               │
├─────────────────────────────────────────────────────────────┤
│  • priority: "high" | "medium" | "low"                       │
│  • metadata: {arbitrary: "key-value pairs"}                  │
│  • agent_name: Identify yourself in activity metadata       │
│  • GET /api/whoami - Self-awareness/identity endpoint       │
│  • GET /api/activity/{id} - Single activity lookup           │
│  • content_size: Character count for token tracking          │
│  • hints: Contextual hints in /api/action response           │
│  • CHAT: New action type for conversational exchanges        │
└─────────────────────────────────────────────────────────────┘
```

---

*ACP Agent Guide v1.0.4*