# ACP Agent Quick Reference

**Version:** Draft 1.0 | **Spec:** See ACP-Specification.md for full details

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
2. LOG ACTION   → POST /api/action {action, target, details}
3. EXECUTE      → Do the action
4. COMPLETE     → POST /api/complete {activity_id, result}
```

### Combined Workflow (Recommended)

```bash
# Complete previous + start new in ONE call
POST /api/action {
  "complete_id": "prev_activity_id",   # Complete previous
  "result": "Previous result here",     # Previous result
  "action": "READ",                     # New action
  "target": "/path/to/file",
  "details": "Purpose of this action"
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

### Example: File Read

```bash
# 1. Log the action FIRST
POST /api/action {
  "action": "READ",
  "target": "/src/config.py",
  "details": "Loading application configuration"
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
# Restore TODO state from ACP
GET /api/todos
→ {"todos": [{"id": "1", "content": "Task 1", "status": "pending"}, ...]}
```

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
| `/api/complete` | Output tokens from result |
| `/api/files/view` | File content tokens (deduplicated per session) |

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

# CSRF Token (required for all POST)
X-CSRF-Token: <timestamp>:<signature>

# Get CSRF token
GET /api/csrf-token
→ {"csrf_token": "1234567890:abc123...", "expires_in": 3600}
```

---

## ERROR RESPONSES

| Code | Meaning | Action |
|------|---------|--------|
| 401 | Auth failed | Check credentials, retry |
| 403 | Stop requested / Invalid CSRF | STOP if stop_flag, else refresh CSRF |
| 404 | Not found | Activity or file doesn't exist |
| 413 | File too large | Use download instead of view |
| 429 | Rate limited | Wait before retrying |

---

## COMPLETE EXAMPLE SEQUENCE

```bash
# === SESSION START ===
→ GET /api/status
← {stop_flag: false, tokens_percent: 15}

→ GET /api/todos
← {todos: [{"id": "1", "content": "Review code", "status": "pending"}]}

# === FILE READ ===
→ POST /api/action {"action": "READ", "target": "config.py", "details": "Load config"}
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
│  □ Log shell commands AFTER executing (POST /api/shell/add) │
│  □ Complete activity when done (POST /api/complete)         │
│  □ Sync TODOs on change (POST /api/todos/update)            │
│  □ Save notes for recovery (POST /api/notes/add)            │
│  □ Export summary before compression (POST /api/summary/export) │
└─────────────────────────────────────────────────────────────┘
```

---

*ACP Agent Guide - Draft 1.0*
