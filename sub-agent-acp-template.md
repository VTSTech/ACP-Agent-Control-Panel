# Sub-Agent ACP Integration Template

**Version:** 1.0.0
**Purpose:** Enable sub-agents to log activities to ACP for multi-agent attribution

---

## Template for Sub-Agent Prompts

When spawning a sub-agent that should log to ACP, include this in the prompt:

```
## ACP Integration (MANDATORY)

You are a sub-agent. You MUST log your activities to the ACP server.

### Credentials
- ACP_URL: {ACP_URL}
- ACP_USER: {ACP_USER}
- ACP_PASS: {ACP_PASS}

### Bootstrap (do this FIRST)
1. GET  {ACP_URL}/api/status - Check stop_flag
2. POST {ACP_URL}/api/agents/register {"agent_name": "{AGENT_NAME}", "capabilities": [...]}
3. POST {ACP_URL}/api/action {"action": "CHAT", "target": "Sub-agent started", "metadata": {"agent_name": "{AGENT_NAME}"}}

### For Each Activity
1. POST {ACP_URL}/api/action BEFORE executing
2. Execute the tool/action
3. POST {ACP_URL}/api/complete AFTER executing

### Shell Commands
Log ALL shell commands via:
POST {ACP_URL}/api/shell/add {"command": "...", "status": "completed", "output_preview": "...", "agent_name": "{AGENT_NAME}"}

### When Done
Return a concise summary of your work. Your activities are logged in ACP history.
```

---

## Example: Spawning an Explore Agent

```javascript
// When using Task tool to spawn a sub-agent
Task({
  subagent_type: "Explore",
  prompt: `
## ACP Integration (MANDATORY)

You are an Explore sub-agent. Log activities to ACP.

### Credentials
- ACP_URL: https://xxx.trycloudflare.com
- ACP_USER: admin
- ACP_PASS: secret

### Your Agent Name
Use agent_name: "Explore" in all metadata.

### Bootstrap
1. GET /api/status - check stop_flag
2. POST /api/agents/register {"agent_name": "Explore", "capabilities": ["search", "file_read"]}
3. POST /api/action {"action": "CHAT", "target": "Explore agent started", "metadata": {"agent_name": "Explore"}}

### Task
Find all files related to "authentication" in the codebase and summarize the auth flow.

### Workflow
1. Log each search/read via /api/action
2. Complete each via /api/complete
3. Return concise summary when done
`
})
```

---

## Agent Name Conventions

| Agent Type | agent_name |
|------------|------------|
| Explore (quick) | `Explore-quick` |
| Explore (medium) | `Explore-medium` |
| Explore (thorough) | `Explore-thorough` |
| Frontend Styling | `Frontend-styler` |
| Full-stack Developer | `Fullstack-dev` |
| General Purpose | `General-agent` |
| Custom | `{Purpose}-{id}` |

---

## Parent Agent Workflow

When spawning a sub-agent with ACP integration:

```
1. Log delegation:
   POST /api/action {
     "action": "CHAT",
     "target": "Delegating to {sub-agent-name}",
     "details": "Task description",
     "metadata": {"agent_name": "Super Z"}
   }

2. Spawn sub-agent with ACP credentials in prompt

3. Wait for sub-agent to return

4. Complete delegation:
   POST /api/complete {
     "activity_id": "...",
     "result": "Sub-agent completed: {summary}"
   }
```

---

## Benefits

- **Clean attribution**: Each agent's activities are logged under their own name
- **Token tracking**: Per-agent token usage in ACP
- **Audit trail**: Full history of who did what
- **Orphan detection**: Sub-agent orphans are tracked separately
- **Context efficiency**: Sub-agent burns its own tokens, returns summary only

---

## Checklist for Sub-Agent Prompts

- [ ] Include ACP_URL, ACP_USER, ACP_PASS
- [ ] Specify agent_name for sub-agent
- [ ] Include bootstrap instructions
- [ ] Include activity logging pattern (action → execute → complete)
- [ ] Include shell logging instruction
- [ ] Request concise summary on completion
