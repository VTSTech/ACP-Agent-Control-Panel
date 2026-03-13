# ACP Agent Quick Reference

**Version:** Draft 1.0.2 | **Spec:** See ACP-Specification.md for full details

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
│  2. If running, you MUST follow ACP Workflow for ALL actions    │
│  3. If not running, proceed normally (no ACP integration)       │
└─────────────────────────────────────────────────────────────────┘
```

**ACP is ACTIVE if:** Response contains `{"success": true, ...}`  
**ACP is INACTIVE if:** Connection refused or no response

---

## ❌ COMMON MISTAKES (AVOID THESE)

| Mistake | What Happens | Correct Approach |
|---------|--------------|------------------|
| **Forgetting to log before executing** | Activity not tracked, tokens inaccurate | ALWAYS call `/api/action` BEFORE using Read/Write/Edit/Bash |
| **Using native tools without logging** | Context window estimation wrong | Include `content_size` parameter |
| **Starting work without checking ACP status** | May miss stop_flag or nudge | Check `/api/status` at session start |
| **Not completing activities** | Orphan tasks pile up | Always call `/api/complete` when done |
| **Multiple agents without attribution** | Can't tell who did what | Use `agent_name` in metadata |

---

## 🔄 EVERY-ACTION TRIGGER

**Before EVERY file read, write, edit, or bash command:**

```
┌─────────────────────────────────────────────────────────────────┐
│  STOP! Did you log this action to ACP?                          │
├─────────────────────────────────────────────────────────────────┤
│  □ POST /api/action {"action": "READ|WRITE|EDIT|BASH", ...}   │
│  □ Get activity_id from response                                │
│  □ NOW you can execute the action                               │
│  □ POST /api/complete when done                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## MANDATORY INTEGRATION REQUIREMENTS

**All agents using ACP MUST:**

1. **Log every action** via `/api/action` BEFORE executing
2. **Log every shell command** via `/api/shell/add` AFTER executing
3. **Sync TODO state** via `/api/todos/update` when TODOs change
4. **Check stop flag** before starting any new activity

---

## ACTIVITY LOGGING (MANDATORY)

### Basic Workflow

```
1. CHECK STATUS → GET /api/status (if stop_flag=true, STOP)
2. LOG ACTION   → POST /api/action {action, target, details, content_size}
3. EXECUTE      → Do the action
4. COMPLETE     → POST /api/complete {activity_id, result, content_size}
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
  "content_size": 35000                 # v1.0.1: Chars to be read
}
→ {activity_id, stop_flag, session_tokens, tokens_remaining}
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
|-------|-------------|--------|
| `agent_name` | Name of agent/subagent | `"Super Z"`, `"full-stack-developer"` |
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
  "content_size": 5000
}
→ {"activity_id": "143052-a1b2c3", ...}

# 2. Execute the read
[Use native Read tool to read /src/config.py]

# 3. Complete the activity
POST /api/complete {
  "activity_id": "143052-a1b2c3",
  "result": "Read 150 lines, found 3 config sections"
}
```

---

## SHELL LOGGING (MANDATORY)

**Every shell/terminal command MUST be logged to ACP.**

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
  "output_preview": "added 57 packages in 3s"  # First 200 chars
}
```

### Example: Shell Command

```bash
# 1. Log the BASH action
POST /api/action {
  "action": "BASH",
  "target": "npm install express",
  "details": "Installing express dependency"
}
→ {"activity_id": "143055-d4e5f6", ...}

# 2. Execute the command
[Run: npm install express]

# 3. Log to shell history
POST /api/shell/add {
  "command": "npm install express",
  "status": "completed",
  "output_preview": "added 57 packages in 3s"
}

# 4. Complete the activity
POST /api/complete {
  "activity_id": "143055-d4e5f6",
  "result": "Express installed successfully"
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
  "todo": {"content": "New task", "status": "pending", "priority": "high"}
}

# Clear completed
POST /api/todos/clear
```

### Example: TODO Workflow

```bash
# 1. At session start - restore state
GET /api/todos
→ {"todos": [...]}

# 2. When completing a task - update ACP
POST /api/todos/update {
  "todos": [
    {"id": "1", "content": "Setup project", "status": "completed"},
    {"id": "2", "content": "Write tests", "status": "in_progress"}
  ]
}

# 3. Also log as activity
POST /api/action {
  "action": "TODO",
  "target": "1",
  "details": "Marked 'Setup project' as completed"
}
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

### Native Tool Tracking (v1.0.1)

When using native Read/Write/Edit tools, include `content_size` for accurate tracking:

```bash
# After reading 35,000 chars with native Read tool:
POST /api/action {
  "action": "READ",
  "target": "/file.py",
  "content_size": 35000   # 35,000 / 3.5 = 10,000 tokens
}

# After writing 5,000 chars with native Write tool:
POST /api/complete {
  "activity_id": "abc123",
  "result": "Written",
  "content_size": 5000    # 5,000 / 3.5 = 1,428 tokens
}
```

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
| 404 | Not found | Activity or file doesn't exist |
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

→ GET /api/todos
← {todos: [{"id": "1", "content": "Review code", "status": "pending"}]}

# === FILE READ ===
→ POST /api/action {"action": "READ", "target": "config.py", "details": "Load config", "metadata": {"agent_name": "Super Z"}}
← {activity_id: "143052-a1b2c3", stop_flag: false}

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

# === TODO UPDATE ===
→ POST /api/todos/update {"todos": [{"id": "1", "content": "Review code", "status": "completed"}]}
← {success: true}

→ POST /api/action {"action": "TODO", "target": "1", "details": "Marked completed"}
← {activity_id: "143058-g7h8i9"}

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
| `ACP-Agent-Guide.md` | This file (agent-optimized) |
| `acp_session_summary.md` | Persistent session state |
| `agent_activity.json` | Session data storage |
| `acp_restart.log` | Restart debugging logs |

---

## QUICK REFERENCE CARD

```
┌─────────────────────────────────────────────────────────────┐
│  ACP MANDATORY CHECKLIST                                     │
├─────────────────────────────────────────────────────────────┤
│  □ Check status before starting (GET /api/status)           │
│  □ Log action BEFORE executing (POST /api/action)           │
│  □ Include content_size for native tools (v1.0.1)           │
│  □ Include agent_name in metadata for attribution           │
│  □ Log shell commands AFTER executing (POST /api/shell/add) │
│  □ Complete activity when done (POST /api/complete)         │
│  □ Sync TODOs on change (POST /api/todos/update)            │
│  □ Save notes for recovery (POST /api/notes/add)            │
│  □ Export summary before compression (POST /api/summary/export) │
└─────────────────────────────────────────────────────────────┘
```

### v1.0.1 Quick Additions

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

### v1.0.2 Quick Additions

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
│  • Check for nudge AND orphan_warning in EVERY response!     │
└─────────────────────────────────────────────────────────────┘
```

### Orphan Detection (v1.0.2)

Before starting a new task, check if there are orphan running tasks:

```bash
POST /api/action {"action": "READ", "target": "new_file.py"}
→ {
    "activity_id": "...",
    "running_count": 2,
    "orphan_warning": {               # ← Check this field!
      "count": 2,
      "tasks": [
        {"id": "abc123", "action": "READ", "target": "old_file.py"},
        {"id": "def456", "action": "WRITE", "target": "another.py"}
      ],
      "suggestion": "Complete or acknowledge orphan tasks"
    }
  }
```

**When orphan_warning present:**
```bash
# Complete each orphan task:
POST /api/complete {"activity_id": "abc123", "result": "Completed late"}
POST /api/complete {"activity_id": "def456", "result": "Completed late"}

# Or use combined endpoint to complete and proceed:
POST /api/action {
  "complete_id": "abc123",
  "result": "Completed",
  "action": "READ",
  "target": "new_file.py"
}
```

**Why it matters:** Starting multiple tasks without completing them causes "task leakage" - activities stuck in running state. Always check `orphan_warning` and `running_count` before starting new work.

### TODO Metadata

TODOs support metadata for agent attribution:

```bash
POST /api/todos/add {
  "todo": {
    "content": "Implement API endpoint",
    "status": "pending",
    "priority": "high"
  },
  "agent_name": "Super Z",      # Who created this TODO
  "tool": "planning",           # Which tool created it
  "skill": "fullstack-dev"      # Which skill (if applicable)
}

# Response includes metadata
→ {
    "success": true,
    "todo": {
      "id": "143052-abc123",
      "content": "Implement API endpoint",
      "status": "pending",
      "priority": "high",
      "created": "2026-03-13T19:59:00",
      "metadata": {
        "agent_name": "Super Z",
        "tool": "planning",
        "skill": "fullstack-dev"
      }
    }
  }
```

**Why it matters:** In multi-agent scenarios, knowing which agent created a TODO helps with task ownership and debugging workflow issues.

### Shell History Metadata

Shell commands support metadata for agent attribution:

```bash
POST /api/shell/add {
  "command": "npm install express",
  "status": "completed",
  "output_preview": "added 57 packages",
  "agent_name": "LocalClaw",    # Who ran this command
  "tool": "shell",              # Which tool executed it
  "metadata": {                 # Or pass full metadata object
    "agent_name": "LocalClaw",
    "tool": "shell",
    "working_dir": "/home/z/my-project"
  }
}

# Response includes metadata
→ {
    "success": true,
    "entry": {
      "id": "143055-def456",
      "command": "npm install express",
      "timestamp": "2026-03-13T19:59:30",
      "status": "completed",
      "output_preview": "added 57 packages",
      "metadata": {
        "agent_name": "LocalClaw",
        "tool": "shell",
        "working_dir": "/home/z/my-project"
      }
    }
  }
```

**Why it matters:** When multiple agents share a session, seeing who ran each command helps understand the workflow and debug issues.



### Activity Hints (v1.0.1)

When you call `/api/action`, the response may include `hints`:

```bash
POST /api/action {"action": "EDIT", "target": "/file.py"}
→ {
  "activity_id": "xxx",
  "hints": {
    "modified_this_session": true,      # File already touched
    "modification_count": 3,             # Accessed 3 times
    "last_action": "READ",               # Last was READ
    "related_todos": [{"id": "1", "content": "Fix file.py"}],
    "loop_detected": true,               # Same action repeated 3+ times
    "suggestion": "Consider if this is intentional"
  }
}
```

**Use hints to:**
- Avoid redundant operations (check `modified_this_session`)
- Find related TODOs (check `related_todos`)
- Break out of loops (check `loop_detected`)
- Learn from past errors (check `recent_errors`, `last_error`)

---

*ACP Agent Guide - Draft 1.0.2*
