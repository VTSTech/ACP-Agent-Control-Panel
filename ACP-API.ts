/**
 * ACP (Agent Control Panel) API Definition
 * Version: 1.0.6
 * Status: Draft
 * Authors: VTSTech, Community Contributors
 * A2A Compliance: JSON-RPC 2.0, Agent Card, contextId support
 *
 * This file is the AI-readable companion to ACP-Specification.md and OpenAPI.yaml.
 * All types and endpoints in one flat file - no $ref chasing, no nesting gymnastics.
 */

// ============================================================================
// SECTION 1: ENUMS & LITERALS
// ============================================================================

/** Actions an agent can perform. Logged via POST /api/action. */
type ActionType =
  | "READ"      // Reading files, viewing content, API GETs
  | "WRITE"     // Creating new files
  | "EDIT"      // Modifying existing files
  | "BASH"      // Terminal commands, scripts, CLI tools
  | "TODO"      // TODO state changes
  | "SKILL"     // Invoking skills (VLM, TTS, image-generation, etc.)
  | "API"       // External API calls
  | "SEARCH"    // Web search, grep, find operations
  | "CHAT"      // Conversational/informational exchanges (v1.0.1)
  | "A2A";      // Agent-to-agent communication (v1.0.4)

/** Status of an activity. */
type ActivityStatus = "running" | "completed" | "error" | "cancelled";

/** Priority levels for activities and messages. */
type Priority = "high" | "medium" | "low"; // medium is default

/** Status of a TODO item. */
type TODOStatus = "pending" | "in_progress" | "completed";

/** Status of a shell command. */
type ShellStatus = "running" | "completed" | "error";

/** Categories for AI notes used in context recovery. */
type NoteCategory = "decision" | "insight" | "context" | "warning" | "todo";

/** Importance level for notes. */
type Importance = "normal" | "high";

/** Agent online/offline status. Computed: online if last_seen < 60s ago. */
type AgentStatus = "online" | "offline";

/** A2A task states - maps from ACP ActivityStatus. */
type A2ATaskState = "RUNNING" | "COMPLETED" | "FAILED" | "CANCELED";

/** A2A message types for inter-agent communication. */
type MessageType = "request" | "response" | "notification";

/** A2A message priority (note: different from Activity priority - adds "urgent"). */
type MessagePriority = "normal" | "high" | "urgent";

/** Nudge priority levels. */
type NudgePriority = "normal" | "high" | "urgent";

// ============================================================================
// SECTION 2: CORE DATA TYPES
// ============================================================================

/** Standard metadata fields attached to activities, TODOs, and shell entries. */
interface ActivityMetadata {
  /** Name of the agent/subagent performing the action (e.g., "Super Z", "LocalClaw") */
  agent_name?: string;
  /** Model identifier used by the agent (v1.0.3, e.g., "gpt-4o", "qwen2.5-coder:0.5b-instruct-q4_k_m") */
  model_name?: string;
  /** Origin of the action: "user_request", "auto", "subagent" */
  source?: string;
  /** Native tool used: "Read", "Write", "Edit", "Bash" */
  tool_name?: string;
  /** Skill invoked (for SKILL actions): "image-generation", "VLM" */
  skill?: string;
  /** Arbitrary additional fields */
  [key: string]: unknown;
}

/** Core activity object - the fundamental unit of ACP tracking. */
interface Activity {
  id: string;                // "HHMMSS-abc123" format
  action: ActionType;
  target: string;            // File path, command, or resource identifier
  details: string;           // Human-readable description
  status: ActivityStatus;
  started: string;           // ISO 8601 timestamp
  completed?: string;        // ISO 8601 timestamp
  tokens_in: number;         // Estimated input tokens
  tokens_out?: number;       // Estimated output tokens
  result?: string;           // Result summary (max 500 chars)
  error?: string;            // Error message (max 200 chars)
  duration_ms?: number;      // Duration in milliseconds
  priority?: Priority;       // v1.0.1: high | medium | low (default: medium)
  metadata?: ActivityMetadata;
  /** Owner agent name - set by server from metadata.agent_name (v1.0.4) */
  _owner?: string;
  /** Whether token counting was skipped due to file deduplication (v1.0.3) */
  tokens_deduplicated?: boolean;
}

/** TODO item for task tracking. */
interface TODO {
  id: string;                // "HHMMSS-abc123" format
  content: string;           // Task description
  status: TODOStatus;
  priority: Priority;
  created: string;           // ISO 8601 timestamp
  metadata?: {
    agent_name?: string;     // Agent that created this TODO
    tool?: string;           // Tool that created it
    skill?: string;          // Skill that created it
  };
}

/** Shell command log entry. */
interface ShellEntry {
  id: string;                // "HHMMSS-abc123" format
  command: string;           // Command executed (max 500 chars)
  timestamp: string;         // ISO 8601 timestamp
  status: ShellStatus;
  output_preview: string;    // Output snippet (max 200 chars)
  metadata?: {
    agent_name?: string;     // Agent that ran this command
    tool?: string;           // Tool that executed it
  };
}

/** AI note for context recovery. */
interface Note {
  id: string;                // "HHMMSS-abc123" format
  timestamp: string;         // ISO 8601 timestamp
  category: NoteCategory;
  content: string;           // Note content (max 500 chars)
  importance: Importance;
}

/** Nudge - synchronous human-to-agent guidance delivered on next /api/action call. */
interface Nudge {
  message: string;           // Guidance message for the agent
  priority: NudgePriority;   // normal | high | urgent
  requires_ack: boolean;     // If true, agent must call POST /api/nudge/ack
  timestamp: string;         // ISO 8601 timestamp
  from: string;              // Usually "human" or "system"
  acknowledged?: boolean;
  /** "shutdown" for session-ending nudges (v1.0.2) */
  type?: string;
}

/** Orphan warning - alerts when starting new tasks with unfinished running tasks. */
interface OrphanWarning {
  count: number;
  tasks: Array<{
    id: string;
    action: ActionType;
    target: string;
  }>;
  suggestion: string;
}

/** Activity hints - contextual information to help agents make better decisions (v1.0.1). */
interface ActivityHints {
  modified_this_session: boolean;
  modification_count: number;
  last_action: ActionType | null;
  recent_errors: number;
  last_error: string | null;
  related_todos: Array<{ id: string; content: string; status: TODOStatus }>;
  loop_detected: boolean;
  loop_count: number;
  suggestion: string | null;
  active_todos: number;
  /** A2A hints for pending messages (v1.0.4) */
  a2a?: A2AHints;
}

/** A2A hints - notification of pending inter-agent messages. */
interface A2AHints {
  pending_count: number;
  senders: string[];
  preview: {
    from: string;
    action: string | null;
    msg_id: string;
  };
}

// ============================================================================
// SECTION 3: A2A / AGENT-TO-AGENT TYPES (v1.0.4)
// ============================================================================

/** Registered agent in the Agent Registry. */
interface Agent {
  name: string;
  capabilities: string[];
  model_name?: string;
  endpoint?: string;         // Remote endpoint URL for remote agents
  status: AgentStatus;
  registered_at: string;     // ISO 8601 timestamp
  last_seen: string;         // ISO 8601 timestamp
  tokens_used: number;
  /** Computed: true if last_seen < 60 seconds ago */
  online?: boolean;
}

/** A2A message for inter-agent communication. */
interface A2AMessage {
  id: string;                // "HHMMSS-abc123" format
  from_agent: string;
  to_agent: string;
  type: MessageType;
  action?: string;           // Action to perform (for requests)
  payload?: object;
  priority: MessagePriority;
  reply_to?: string;         // Message ID this is replying to
  created_at: string;        // ISO 8601 timestamp
  expires_at: string;        // ISO 8601 expiration timestamp
  ttl: number;               // Time-to-live in seconds (default: 3600)
}

/** A2A context for grouping related multi-turn interactions. */
interface A2AContext {
  contextId: string;         // "ctx-<uuid>" format
  created: number;           // Unix timestamp
  last_activity: number;     // Unix timestamp
  agents: string[];
  tasks: string[];
  metadata?: object;
}

/** A2A Task representation (maps from ACP Activity for protocol compliance). */
interface A2ATask {
  id: string;                // Activity ID
  contextId?: string;
  status: {
    state: A2ATaskState;
    timestamp: string;
  };
  history: object[];         // Future use
  artifacts: object[];       // Future use
  metadata: {
    action: ActionType;
    target: string;
    tokens_in: number;
    tokens_out: number;
    duration_ms?: number;
  };
}

/** Agent skill for capability discovery (used in Agent Card). */
interface AgentSkill {
  id: string;
  name: string;
  description: string;
  tags?: string[];
  examples?: string[];
  inputModes?: string[];     // MIME types
  outputModes?: string[];    // MIME types
}

/** Agent Card served at /.well-known/agent-card.json for A2A discovery. */
interface AgentCard {
  name: string;
  description: string;
  url: string;
  version: string;
  capabilities: {
    streaming: boolean;
    pushNotifications: boolean;
  };
  defaultInputModes: string[];
  defaultOutputModes: string[];
  skills: AgentSkill[];
  authentication: {
    schemes: string[];
  };
  metadata?: object;
}

// ============================================================================
// SECTION 4: SESSION & SYSTEM TYPES
// ============================================================================

/** Session information returned by multiple endpoints. */
interface SessionInfo {
  session_start: number;         // Unix timestamp
  last_activity: number;        // Unix timestamp
  elapsed_seconds: number;
  idle_seconds: number;
  timeout_seconds: number;
  remaining_seconds: number;
  is_expired: boolean;
  expires_at: string;           // ISO 8601
}

/** Token summary fields returned in status and action responses. */
interface TokenSummary {
  session_tokens: number;       // Primary agent's context consumption
  startup_tokens: number;       // Session initialization overhead (~3000)
  activity_tokens: number;      // session_tokens - startup_tokens
  tokens_remaining: number;     // context_window - session_tokens
  tokens_percent: number;       // (session_tokens / context_window) * 100
  overflow_warning: string | null; // "Context window over 90% full" or null
  other_agents_tokens: number;  // Sum of non-primary agent tokens
  tunnel_url: string | null;    // Active cloudflared tunnel URL (v1.0.3)
}

/** Structured session summary for context recovery. */
interface SessionSummary {
  session_overview: {
    duration: string;           // Formatted: "15m 30s"
    duration_seconds: number;
    total_activities: number;
    activity_breakdown: Record<ActionType, number>;
    currently_running: number;
    stop_flag: boolean;
    stop_reason: string | null;
    primary_agent: string | null;
  };
  token_usage: {
    session_tokens: number;
    tokens_percent: number;
    context_window: number;
    tokens_remaining: number;
  };
  file_interactions: {
    files_read: string[];
    files_written: string[];
    files_edited: string[];
  };
  ai_notes: Note[];
  todos: TODO[];
  recent_activities: Activity[];
}

/** Duration statistics for performance analysis (v1.0.3). */
interface DurationStats {
  by_action: Record<string, {
    count: number;
    total_ms: number;
    average_ms: number;
    average_str: string;
    min_ms: number;
    max_ms: number;
  }>;
  slow_activities: Array<{
    id: string;
    action: ActionType;
    target: string;
    duration_ms: number;
    duration_str: string;
  }>;
  total_duration_ms: number;
  activities_with_duration: number;
  average_duration_ms: number;
  slow_threshold_ms: number;    // Default: 30000
  trend: Array<{
    action: ActionType;
    duration_ms: number;
    timestamp: string;
  }>;
}

/** Complete session state stored in agent_activity.json. */
interface SessionState {
  running: Activity[];
  history: Activity[];
  stop_flag: boolean;
  stop_reason: string | null;
  session_tokens: number;
  startup_tokens: number;
  todos: TODO[];
  shell_history: ShellEntry[];
  ai_notes: Note[];
  session_start: number;
  last_activity: number;
  nudge: Nudge | null;
  primary_agent: string | null;
  /** Name of the agent that most recently logged an activity (default: "Unknown") */
  last_agent?: string;
  /** Model identifier from the most recent activity's metadata (default: "Unknown") */
  last_model?: string;
  agent_tokens: Record<string, number>;
  files_read_tokens: Record<string, number>;
  // v1.0.4 fields
  agents: Record<string, Agent>;
  a2a_messages: A2AMessage[];
  contexts: Record<string, A2AContext>;
  agent_skills: Record<string, AgentSkill[]>;
}

// ============================================================================
// SECTION 5: REQUEST TYPES
// ============================================================================

/** POST /api/start */
interface StartActivityRequest {
  action: ActionType;
  target: string;
  details?: string;
  content_size?: number;     // v1.0.1: Character count of content to be read
  priority?: Priority;       // v1.0.1
  metadata?: ActivityMetadata;
}

/** POST /api/complete */
interface CompleteActivityRequest {
  activity_id: string;
  result?: string;           // Max 500 chars
  error?: string;            // Max 200 chars
  content_size?: number;     // v1.0.1: Character count written
  metadata?: ActivityMetadata;
}

/** POST /api/action (combined: complete previous + start new) */
interface CombinedActionRequest extends StartActivityRequest {
  // Complete previous activity
  complete_id?: string;
  result?: string;
  error?: string;
  complete_content_size?: number;
  complete_metadata?: ActivityMetadata;
}

/** POST /api/stop */
interface StopRequest {
  reason?: string;           // Default: "User requested"
}

/** POST /api/shutdown */
interface ShutdownRequest {
  reason?: string;           // Default: "Session ended by user"
  export_summary?: boolean;  // Default: true
}

/** POST /api/todos/update */
interface UpdateTodosRequest {
  todos: Array<{
    content: string;
    status?: TODOStatus;     // Default: "pending"
    priority?: Priority;     // Default: "medium"
  }>;
}

/** POST /api/todos/toggle */
interface ToggleTodoRequest {
  id: string;
}

/** POST /api/todos/toggle */
interface ToggleTodoResponse {
  success: true;
  todo: TODO;
  toggled: boolean;
}

/** POST /api/todos/add */
interface AddTodoRequest {
  todo: {
    content: string;
    status?: TODOStatus;
    priority?: Priority;
  };
  agent_name?: string;
  tool?: string;
  skill?: string;
}

/** POST /api/shell/add */
interface AddShellEntryRequest {
  command: string;           // Max 500 chars
  status?: ShellStatus;      // Default: "completed"
  output_preview?: string;   // Max 200 chars
  agent_name?: string;
  tool?: string;
  metadata?: ActivityMetadata;
}

/** POST /api/notes/add */
interface AddNoteRequest {
  category?: NoteCategory;   // Default: "context"
  content: string;           // Max 500 chars
  importance?: Importance;    // Default: "normal"
}

/** POST /api/nudge */
interface CreateNudgeRequest {
  message: string;
  priority?: NudgePriority;  // Default: "normal"
  requires_ack?: boolean;    // Default: true
}

/** POST /api/agents/register */
interface RegisterAgentRequest {
  agent_name: string;
  capabilities?: string[];
  model_name?: string;
  endpoint?: string;
}

/** POST /api/agents/unregister */
interface UnregisterAgentRequest {
  agent_name: string;
}

/** POST /api/a2a/send */
interface SendA2AMessageRequest {
  from_agent: string;
  to_agent: string;
  type?: MessageType;        // Default: "notification"
  action?: string;
  payload?: object;
  priority?: MessagePriority; // Default: "normal"
  ttl?: number;               // Default: 3600
  reply_to?: string;
}

/** POST /api/activity/batch (v1.0.3) */
interface BatchOperationsRequest {
  operations: Array<
    | { type: "start"; action: ActionType; target?: string; content_size?: number; metadata?: ActivityMetadata }
    | { type: "complete"; activity_id: string; result?: string; content_size?: number }
  >; // Max 50 operations
}

/** POST /api/files/save */
interface SaveFileRequest {
  path: string;
  content: string;
}

/** POST /api/files/delete */
interface DeleteFileRequest {
  path: string;
}

/** POST /api/files/mkdir */
interface MkdirRequest {
  path: string;
  name: string;
}

/** POST /api/files/extract */
interface ExtractRequest {
  path: string;
}

/** POST /api/files/compress */
interface CompressRequest {
  path: string;
  name: string;
  items: string[];
}

// ============================================================================
// SECTION 6: RESPONSE TYPES
// ============================================================================

/** Generic success response. */
interface SuccessResponse {
  success: true;
  message?: string;
}

/** Generic error response. */
interface ErrorResponse {
  success: false;
  error: string;
}

/** GET /api/status */
interface StatusResponse {
  success: true;
  stop_flag: boolean;
  stop_reason: string | null;
  running_count: number;
  running: Activity[];
  session_tokens: number;
  startup_tokens: number;
  activity_tokens: number;
  context_window: number;
  tokens_remaining: number;
  tokens_percent: number;
  overflow_warning: string | null;
  primary_agent: string | null;
  agent_tokens: Record<string, number>;
  other_agents_tokens: number;
  tunnel_url: string | null;
  session: SessionInfo;
}

/** GET /api/running */
interface RunningResponse {
  success: true;
  running: Activity[];
}

/** GET /api/history */
interface HistoryResponse {
  success: true;
  history: Activity[];
}

/** GET /api/all */
interface AllResponse {
  success: true;
  stop_flag: boolean;
  stop_reason: string | null;
  running: Activity[];
  history: Activity[];
  session_tokens: number;
  context_window: number;
  tokens_remaining: number;
  tokens_percent: number;
  tunnel_url: string | null;
  /** Extended fields returned by the implementation's polling endpoint */
  primary_agent?: string | null;
  last_agent?: string;
  agent_tokens?: Record<string, number>;
  session?: SessionInfo;
  todos?: TODO[];
  shell_history?: ShellEntry[];
  errors?: Array<{message: string; timestamp: string}>;
  agents?: Record<string, Agent>;
  hints?: ActivityHints;
  nudge?: Nudge | null;
  orphan_warning?: OrphanWarning | null;
  current_files?: string[];
  base_dir?: string;
}

/** GET /api/activity/{id} */
interface ActivityLookupResponse {
  success: true;
  activity: Activity;
}
// Also returns ErrorResponse on 404.

/** POST /api/start */
interface StartActivityResponse {
  success: true;
  activity_id: string;
  session_tokens: number;
  context_window: number;
  tokens_remaining: number;
  hints: ActivityHints;
}
// Also returns ErrorResponse with { error: "Stop requested" } on stop.

/** POST /api/complete */
interface CompleteActivityResponse {
  success: true;
  activity: Activity;
  session_tokens: number;
  context_window: number;
  tokens_remaining: number;
  hints: ActivityHints;
}
// Also returns ErrorResponse on 404 and 403 (ownership violation).

/** POST /api/action (the big one) */
interface CombinedActionResponse {
  success: true;
  activity_id: string;
  completed?: Activity;         // Previous activity (if complete_id provided)
  stop_flag: boolean;
  session_tokens: number;
  context_window: number;
  tokens_remaining: number;
  tokens_percent: number;
  overflow_warning: string | null;
  session: SessionInfo;
  running_count: number;
  hints: ActivityHints;
  nudge: Nudge | null;           // Only delivered to primary agent (v1.0.5)
  orphan_warning: OrphanWarning | null;
}
// Also returns ErrorResponse on 403 (stop requested, CSRF, or ownership violation).

/** POST /api/shutdown */
interface ShutdownResponse {
  success: true;
  message: string;
  summary_exported: boolean;
  summary_path: string;
  cancelled_activities: number;
  note: string;
}

/** POST /api/reset */
interface ResetResponse {
  success: true;
  message: string;
  stats: {
    history_cleared: number;
    shell_cleared: number;
    todos_cleared: number;
    agents_cleared: number;
    a2a_cleared: number;
    tokens_reset: number;
  };
}

/** GET/POST /api/todos */
interface TodosResponse {
  success: true;
  todos: TODO[];
}

/** GET/POST /api/shell */
interface ShellResponse {
  success: true;
  shell_history: ShellEntry[];
}

/** GET /api/summary */
interface SummaryResponse {
  success: true;
  summary: SessionSummary;
}

/** GET /api/summary/export */
interface ExportSummaryResponse {
  success: true;
  message: string;
  filepath: string;
  note?: string;
}

/** GET/POST /api/notes */
interface NotesResponse {
  success: true;
  notes: Note[];
}

/** GET/POST /api/nudge */
interface NudgeResponse {
  success: true;
  nudge: Nudge | null;
  has_pending?: boolean;
  message?: string;
}

/** GET /api/whoami */
interface WhoamiResponse {
  success: true;
  identity: {
    hint: string;
    suggestion: string;
    example: object;
    purpose: string;
  };
  primary_agent: string | null;
  session: SessionInfo;
}

/** GET /api/agents */
interface AgentsListResponse {
  success: true;
  agents: Agent[];
  count: number;
  primary_agent: string | null;
}

/** GET /api/agents/{name} */
interface AgentDetailResponse {
  success: true;
  agent: Agent;
}

/** POST /api/agents/register */
interface RegisterAgentResponse {
  success: true;
  agent: Agent;
  message: string;
}

/** POST /api/a2a/send */
interface SendA2AMessageResponse {
  success: true;
  message: A2AMessage;
}

/** GET /api/a2a/history */
interface A2AHistoryResponse {
  success: true;
  messages: A2AMessage[];
  count: number;
}

/** GET /api/stats/duration */
interface DurationStatsResponse {
  success: true;
  stats: DurationStats;
  slow_threshold_seconds: number;
}

/** POST /api/activity/batch */
interface BatchOperationsResponse {
  success: boolean;
  results: Array<{
    success: boolean;
    operation: string;
    activity_id?: string;
    error?: string;
  }>;
  count: number;
  session_tokens: number;
  context_window: number;
  tokens_remaining: number;
}

/** GET /api/csrf-token */
interface CsrfTokenResponse {
  success: true;
  csrf_enabled: boolean;
  csrf_token: string | null;
  expires_in: number | null;
  message: string | null;
}

/** GET /api/files/view */
interface FileViewResponse {
  content: string;
  path: string;
  lines: number;
  tokens: number;
  session_tokens: number;
}

/** GET /api/files/stats */
interface FileStatsResponse {
  success: true;
  total_files: number;
  total_directories: number;
  total_size_bytes: number;
}

// ============================================================================
// SECTION 7: JSON-RPC 2.0 TYPES (v1.0.4)
// ============================================================================

/** JSON-RPC 2.0 request envelope. */
interface JsonRpcRequest {
  jsonrpc: "2.0";
  method: string;
  params?: object;
  id?: number | string | null;
}

/** JSON-RPC 2.0 response envelope. */
interface JsonRpcResponse {
  jsonrpc: "2.0";
  result?: unknown;
  error?: JsonRpcError;
  id: number | string | null;
}

/** JSON-RPC 2.0 error object. */
interface JsonRpcError {
  code: number;
  message: string;
  data?: unknown;
}

/** JSON-RPC error codes used by ACP. */
const JsonRpcErrorCodes = {
  PARSE_ERROR:        -32700,
  INVALID_REQUEST:    -32600,
  METHOD_NOT_FOUND:   -32601,
  INVALID_PARAMS:     -32602,
  INTERNAL_ERROR:     -32603,
  TASK_NOT_FOUND:     -32001,
  TASK_NOT_RUNNING:   -32002,
  STOP_REQUESTED:     -32003,
} as const;

/** JSON-RPC methods supported by ACP. */
type JsonRpcMethod =
  | "GetAgents"
  | "RegisterAgent"
  | "SendMessage"
  | "GetTask"
  | "CancelTask"
  | "activity/start"
  | "activity/complete"
  | "todos/get"
  | "todos/update"
  | "status/get"
  | "nudge/set"
  | "stop/set"
  | "session/reset";

// ============================================================================
// SECTION 8: CONFIGURATION (Environment Variables)
// ============================================================================

/**
 * All ACP configuration is via environment variables.
 * No config files, no CLI flags - just env vars.
 */
interface AcpConfig {
  // Common to minimal and full
  ACP_PORT?: string;              // or GLMACP_PORT    | "8766"
  ACP_USER?: string;              // or GLMACP_USER    | "admin"
  ACP_PASS?: string;              // or GLMACP_PASS    | "secret"
  ACP_DATA_FILE?: string;         //                    | "./agent_activity.json"
  ACP_SUMMARY_FILE?: string;      //                    | "./acp_session_summary.md"
  ACP_CONTEXT_WINDOW?: string;    //                    | "200000"
  ACP_SESSION_TIMEOUT?: string;   //                    | "86400"
  ACP_ORPHAN_TIMEOUT?: string;    // (minimal only)    | "300"

  // Full version only (GLMACP_* prefix)
  GLMACP_CSRF_ENABLED?: string;   //                    | "false"
  GLMACP_MAX_UPLOAD_SIZE?: string; //                    | "104857600" (100MB)
  GLMACP_MAX_FILE_VIEW_SIZE?: string; //                  | "10485760" (10MB)
  GLMACP_TUNNEL?: string;         //                    | "false"
  GLMACP_TUNNEL_URL?: string;     //                    | (none)
  GLMACP_FILES_DIR?: string;      //                    | (script parent)
  GLMACP_QUIET?: string;          //                    | "false"
}

// ============================================================================
// SECTION 9: ENDPOINT REFERENCE (Flat List)
// ============================================================================

/**
 * Complete ACP API endpoint reference.
 * Base URL: http://localhost:8766 (configurable via ACP_PORT)
 * Auth: HTTP Basic (username:password)
 *
 * Legend:
 *   [G] = GET    [P] = POST
 *   since vX.X = version when endpoint was added
 */

const ENDPOINTS = {
  // --- Activity Monitor (§4.3) ---
  "GET    /api/status":              "Full session status (stop_flag, tokens, running)",
  "GET    /api/running":             "List currently running activities",
  "GET    /api/history":             "List completed activity history (newest first)",
  "GET    /api/all":                 "Combined: status + running + history + tokens",
  "GET    /api/activity/{id}":       "Get single activity by ID [since v1.0.1]",
  "POST   /api/start":               "Start a new activity",
  "POST   /api/complete":            "Complete an activity",
  "POST   /api/action":              "Combined: complete previous + start new (RECOMMENDED)",
  "POST   /api/stop":                "Set stop_flag, cancel all running",
  "POST   /api/resume":              "Clear stop_flag, resume operations",
  "POST   /api/shutdown":            "Graceful session end + summary export [since v1.0.2]",
  "POST   /api/clear_history":       "Clear activity history",
  "POST   /api/reset_session":       "Reset tokens to startup value",
  "POST   /api/reset":               "Full session reset (incl. agents, A2A) [since v1.0.4]",

  // --- TODO (§4.4) ---
  "GET    /api/todos":               "Get current TODO list",
  "POST   /api/todos/update":        "Replace entire TODO list",
  "POST   /api/todos/add":           "Add single TODO item",
  "POST   /api/todos/toggle":        "Toggle TODO status (minimal only)",
  "POST   /api/todos/clear":         "Clear completed TODOs",

  // --- Shell History (§4.5) ---
  "GET    /api/shell":               "Get shell command history",
  "POST   /api/shell/add":           "Add shell command to history",
  "POST   /api/shell/clear":         "Clear shell history",

  // --- Context Recovery (§4.6) ---
  "GET    /api/summary":             "Get condensed session summary",
  "GET    /api/summary/export":      "Export summary to persistent markdown",
  "GET    /api/notes":               "Get all saved notes",
  "POST   /api/notes/add":           "Add a context recovery note",
  "POST   /api/notes/clear":         "Clear all notes",

  // --- File Manager (§4.7) ---
  "GET    /api/files/list":          "List directory (headers: X-Path, X-Sort-By, X-Sort-Dir)",
  "GET    /api/files/view":          "View text file content (header: X-Path)",
  "GET    /api/files/download":      "Download file (query: path)",
  "GET    /api/files/image":         "Get image file (query: path)",
  "GET    /api/files/stats":         "Get file statistics",
  "POST   /api/files/upload":        "Upload file (headers: X-Path, X-Filename, body: binary)",
  "POST   /api/files/save":          "Save text file {path, content}",
  "POST   /api/files/delete":        "Delete file or directory {path}",
  "POST   /api/files/mkdir":         "Create directory {path, name}",
  "POST   /api/files/extract":       "Extract archive {path}",
  "POST   /api/files/compress":      "Create zip {path, name, items[]}",

  // --- Duration & Batch (§4.8-4.9) ---
  "GET    /api/stats/duration":      "Activity duration statistics [since v1.0.3]",
  "POST   /api/activity/batch":      "Batch start/complete operations [since v1.0.3]",

  // --- System (§4.10) ---
  "GET    /api/system":              "CPU, RAM, Disk statistics",
  "GET    /api/session":             "Session info and timeout",
  "POST   /api/session/refresh":      "Extend session timeout",
  "POST   /api/restart":             "Restart ACP server",
  "GET    /api/csrf-token":          "Get CSRF token (indicates if enabled)",
  "GET    /api/whoami":              "Agent self-awareness + identity [since v1.0.1]",

  // --- Nudge API (§4.11) ---
  "POST   /api/nudge":               "Create nudge (human → agent guidance) [since v1.0.2]",
  "GET    /api/nudge":               "Check pending nudge",
  "POST   /api/nudge/ack":           "Acknowledge nudge (clears it)",

  // --- Agent Registry (§4.12) ---
  "GET    /api/agents":              "List all registered agents [since v1.0.4]",
  "GET    /api/agents/{name}":       "Get specific agent details",
  "POST   /api/agents/register":     "Register agent with capabilities",
  "POST   /api/agents/unregister":   "Unregister an agent",

  // --- A2A Messaging (§4.13) ---
  "POST   /api/a2a/send":           "Send message to another agent [since v1.0.4]",
  "GET    /api/a2a/history":         "Get A2A message history (query: from, to, type)",

  // --- JSON-RPC 2.0 (v1.0.4) ---
  "POST   /jsonrpc":                "JSON-RPC 2.0 endpoint",
  "POST   /a2a":                    "Alternative JSON-RPC endpoint",
  "POST   /api/jsonrpc":            "JSON-RPC under /api namespace",
  "GET    /.well-known/agent-card.json": "A2A Agent Card discovery",
} as const;

// ============================================================================
// SECTION 10: ACP STATE MAPPING
// ============================================================================

/**
 * Maps ACP ActivityStatus to A2A TaskState.
 */
const ACP_TO_A2A_STATUS: Record<ActivityStatus, A2ATaskState> = {
  running:   "RUNNING",
  completed: "COMPLETED",
  error:      "FAILED",
  cancelled: "CANCELED",
};

// ============================================================================
// SECTION 11: AGENT WORKFLOW (Quick Reference)
// ============================================================================

/**
 * THE ACP PATTERN (MEMORIZE):
 *
 *   CHECK → LOG → EXECUTE → COMPLETE
 *   /api/status → /api/action → Tool → /api/complete
 *   BEFORE → NOW → AFTER
 *
 * NEVER execute before logging.
 *
 * BOOTSTRAP (mandatory, in order):
 *   1. GET  /api/status            → Check stop_flag
 *   2. GET  /api/whoami            → Establish identity
 *   3. POST /api/agents/register   → Register with Agent Registry
 *   4. GET  /api/todos             → Restore TODO state
 *   5. POST /api/action            → Log bootstrap CHAT activity
 *
 * CHECK ON EVERY RESPONSE:
 *   - stop_flag: true        → STOP immediately, inform user
 *   - nudge                  → Read, adjust behavior, ack if requires_ack
 *   - orphan_warning         → Complete orphan tasks first
 *   - hints.loop_detected    → Change approach
 *   - hints.a2a.pending      → Check A2A messages
 *   - overflow_warning        → Context running low
 *
 * MANDATORY RULES:
 *   1. CHECK status before starting any activity
 *   2. LOG every action BEFORE executing
 *   3. COMPLETE every activity when done
 *   4. LOG every shell command (except ACP API calls)
 *   5. SYNC TODOs on change
 *   6. Include agent_name in all metadata
 *   7. Pass content_size for accurate token tracking (chars / 3.5 = tokens)
 */

export type {
  ActionType,
  ActivityStatus,
  Priority,
  TODOStatus,
  ShellStatus,
  NoteCategory,
  Importance,
  AgentStatus,
  A2ATaskState,
  MessageType,
  MessagePriority,
  NudgePriority,
  ActivityMetadata,
  Activity,
  TODO,
  ShellEntry,
  Note,
  Nudge,
  OrphanWarning,
  ActivityHints,
  A2AHints,
  Agent,
  A2AMessage,
  A2AContext,
  A2ATask,
  AgentSkill,
  AgentCard,
  SessionInfo,
  TokenSummary,
  SessionSummary,
  DurationStats,
  SessionState,
  // Requests
  StartActivityRequest,
  CompleteActivityRequest,
  CombinedActionRequest,
  StopRequest,
  ShutdownRequest,
  UpdateTodosRequest,
  AddTodoRequest,
  ToggleTodoRequest,
  AddShellEntryRequest,
  AddNoteRequest,
  CreateNudgeRequest,
  RegisterAgentRequest,
  UnregisterAgentRequest,
  SendA2AMessageRequest,
  BatchOperationsRequest,
  SaveFileRequest,
  DeleteFileRequest,
  MkdirRequest,
  ExtractRequest,
  CompressRequest,
  // Responses
  SuccessResponse,
  ErrorResponse,
  StatusResponse,
  RunningResponse,
  HistoryResponse,
  AllResponse,
  ActivityLookupResponse,
  StartActivityResponse,
  CompleteActivityResponse,
  CombinedActionResponse,
  ShutdownResponse,
  ResetResponse,
  TodosResponse,
  ToggleTodoResponse,
  ShellResponse,
  SummaryResponse,
  ExportSummaryResponse,
  NotesResponse,
  NudgeResponse,
  WhoamiResponse,
  AgentsListResponse,
  AgentDetailResponse,
  RegisterAgentResponse,
  SendA2AMessageResponse,
  A2AHistoryResponse,
  DurationStatsResponse,
  BatchOperationsResponse,
  CsrfTokenResponse,
  FileViewResponse,
  FileStatsResponse,
  // JSON-RPC
  JsonRpcRequest,
  JsonRpcResponse,
  JsonRpcError,
  JsonRpcMethod,
  // Config
  AcpConfig,
};
