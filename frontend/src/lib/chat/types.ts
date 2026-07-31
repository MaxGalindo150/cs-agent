// Domain types for the chat feature. Kept framework-agnostic so they can be
// shared by the API client, hooks, and UI as the project grows.
//
// Naming note: what the UI calls a "conversation" the agent-service calls a
// "session" — same thing, and `id` here is the session id the API expects back
// on later turns. The wire-level name only appears in lib/chat/api.ts.

export type Role = "user" | "assistant";

export interface Message {
  id: string;
  role: Role;
  content: string;
  /** True while the assistant reply is still streaming in. */
  streaming?: boolean;
  /** Set when this message failed to complete. */
  error?: string;
  /** What the agent did before answering, in the order it happened. Only ever
   *  set on assistant messages, and only for a turn that did something. */
  steps?: ActivityStep[];
}

/** One line in the activity timeline shown above an assistant reply. */
export interface ActivityStep {
  id: string;
  kind: "memory" | "tool";
  /** Raw tool name — how a `tool` completion event finds the step its
   *  `tool_start` opened. Absent on memory steps. */
  tool?: string;
  /** Human-readable label, e.g. "Getting order ord_0001". */
  label: string;
  /** "running" until the matching completion event arrives. A step can stay
   *  "running" forever if the turn errored — the UI must not assume it ends. */
  status: "running" | "done";
}

/** One row in the conversation list (mirrors the backend SessionSummary). */
export interface ConversationSummary {
  id: string;
  /** The opening user message, stamped server-side when the session is created.
   *  Null for sessions created before titles existed. */
  title: string | null;
  created_at: string;
  last_activity_at: string;
}

/** A resolved tool call, surfaced mid-stream for transparency. */
export interface ToolEvent {
  tool: string;
  args: Record<string, unknown>;
  /** Truncated server-side to 500 chars — a preview, not the full result. */
  output: string;
}
