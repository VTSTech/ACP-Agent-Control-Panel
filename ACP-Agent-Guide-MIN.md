# ACP Agent Quick Reference

**Version:** 1.0.3 | **Spec:** [ACP-Specification.md](https://github.com/VTSTech/ACP-Agent-Control-Panel/blob/main/ACP-Specification.md)

---

## THE ACP PATTERN (MEMORIZE)

```
LOG → EXECUTE → COMPLETE
/api/action → Tool → /api/complete
BEFORE → NOW → AFTER
```

**NEVER execute before logging.**

---

## SESSION START

```bash
curl -s -u admin:secret http://localhost:8766/api/status
# If running: follow ACP workflow for ALL actions
# If not: proceed normally (no ACP)
```

---

## EVERY ACTION

**Before Read/Write/Edit/Bash/Grep/Glob/LS:**
```bash
POST /api/action {"action": "READ|WRITE|EDIT|BASH|SEARCH", "target": "...", "details": "..."}
→ {activity_id, stop_flag, session_tokens, nudge?, orphan_warning?}
```

**After execution:**
```bash
POST /api/complete {"activity_id": "...", "result": "..."}
```

**Combined (recommended):**
```bash
POST /api/action {"complete_id": "prev_id", "result": "prev result", "action": "READ", "target": "file.py"}
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
| CHAT | Conversational Q&A, planning |

---

## NUDGE HANDLING (v1.0.2)

Check `nudge` field in every `/api/action` response:
```json
{"nudge": {"message": "...", "priority": "high", "requires_ack": true, "type": "shutdown"}}
```

If `requires_ack: true`:
```bash
POST /api/nudge/ack {}
```

**Shutdown nudge** (`type: "shutdown"`): Session ending, acknowledge and stop.

---

## STOP ALL

If `stop_flag: true`: STOP immediately, inform user, wait for resume.

---

## SHELL LOGGING (MANDATORY)

**Log ALL shell/terminal commands EXCEPT ACP API calls.**

```bash
POST /api/shell/add {"command": "...", "status": "completed|error", "output_preview": "first 200 chars"}
```

| Log These | Don't Log |
|-----------|-----------|
| `git clone`, `npm install`, `ls`, `python script.py` | `curl ... localhost:8766/api/...` (ACP calls) |
| `pip install`, `make build`, `docker run` | ACP communication is monitoring overhead |
| Any actual work command | |

---

## TODO SYNC

```bash
GET /api/todos                          # Restore state
POST /api/todos/update {"todos": [...]} # Full sync
POST /api/todos/add {"todo": {...}}     # Add single
POST /api/todos/clear                   # Clear completed
```

---

## TOKEN TRACKING

- Context window: 200,000 tokens (configurable)
- Estimation: 3.5 chars/token
- Warning at 90% usage

**Native tools** - include `content_size`:
```bash
POST /api/action {"action": "READ", "target": "file.py", "content_size": 35000}
POST /api/complete {"activity_id": "...", "result": "...", "content_size": 5000}
```

**File deduplication** (v1.0.3): READ activities auto-deduplicate files already read.

**Per-agent tracking** (v1.0.2): First agent = primary, owns `session_tokens`. Others tracked in `agent_tokens{}`.

---

## CONTEXT RECOVERY

**Session start:**
```bash
GET /api/summary     # Session state
GET /api/todos       # Restore TODOs
GET /api/notes       # Saved notes
```

**Before compression:**
```bash
POST /api/notes/add {"category": "decision|insight|context|warning|todo", "content": "..."}
GET /api/summary/export  # Export to markdown
```

---

## ORPHAN DETECTION (v1.0.2)

Check `orphan_warning` in response. If present, complete orphan tasks first:
```bash
POST /api/complete {"activity_id": "orphan_id", "result": "Completed late"}
```

---

## DURATION STATS (v1.0.3)

```bash
GET /api/stats/duration    # Performance analysis by action type
```

Returns: avg duration per action, slow activities (>30s), trends.

---

## BATCH OPERATIONS (v1.0.3)

```bash
POST /api/activity/batch {"operations": [
  {"type": "start", "action": "READ", "target": "file1.py"},
  {"type": "start", "action": "READ", "target": "file2.py"},
  {"type": "complete", "activity_id": "prev-id", "result": "Done"}
]}
```
Max 50 operations per batch.

---

## METADATA (v1.0.1)

```bash
POST /api/action {"action": "READ", "target": "file.py", "priority": "high|medium|low", "metadata": {"agent_name": "Super Z", "model_name": "gpt-4o"}}
```

| Field | Description |
|-------|-------------|
| `agent_name` | Agent/subagent name (e.g., "Super Z", "LocalClaw") |
| `model_name` | Model identifier (v1.0.3) (e.g., "qwen2.5-coder:0.5b-instruct-q4_k_m") |
| `source` | Origin (e.g., "user_request", "auto", "subagent") |
| `skill` | Skill invoked for SKILL actions |

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
| 404 | Activity/file not found |
| 429 | Rate limited, wait |

---

## QUICK EXAMPLE

```bash
# Session start
GET /api/status
GET /api/todos

# File read
POST /api/action {"action": "READ", "target": "config.py", "metadata": {"agent_name": "Super Z"}}
# [Read file]
POST /api/complete {"activity_id": "...", "result": "50 lines"}

# Shell command
POST /api/action {"action": "BASH", "target": "npm install"}
# [Run command]
POST /api/shell/add {"command": "npm install", "status": "completed", "output_preview": "added 57 packages"}
POST /api/complete {"activity_id": "...", "result": "Installed"}

# TODO update
POST /api/todos/update {"todos": [{"id": "1", "content": "Task", "status": "completed"}]}
```

---

## CHECKLIST

- [ ] Check status before starting
- [ ] Log action BEFORE executing
- [ ] Include `content_size` for native tools
- [ ] Include `agent_name` and `model_name` in metadata
- [ ] Log shell commands to `/api/shell/add` (except ACP calls)
- [ ] Complete activity when done
- [ ] Sync TODOs on change
- [ ] Check `nudge` and `orphan_warning` in responses
- [ ] Use batch ops for multiple activities (v1.0.3)
- [ ] Save notes before compression

---

*ACP Agent Guide v1.0.3*