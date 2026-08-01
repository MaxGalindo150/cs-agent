// Domain types for the chat feature. Kept framework-agnostic so they can be
// shared by the API client, hooks, and UI as the project grows.
//
// Naming note: what the UI calls a "conversation" the agent-service calls a
// "session" — same thing, and `id` here is the session id the API expects back
// on later turns. The wire-level name only appears in lib/chat/api.ts.

export type Role = "user" | "assistant";

/**
 * A chunk of an assistant turn, in the order it actually happened: some text,
 * then maybe a group of tool calls, then maybe more text ("I'll escalate
 * this" -> escalate_to_human -> "Done, someone will follow up"). Rendering
 * `parts` in order is what lets a tool's activity widget sit between the two
 * sentences instead of every tool call being hoisted above the whole reply.
 */
export type MessagePart =
  | { type: "text"; text: string }
  | { type: "steps"; steps: ActivityStep[] };

export interface Message {
  id: string;
  role: Role;
  /** The turn's text and tool-activity groups, in the order they happened.
   *  A user message is always a single text part. */
  parts: MessagePart[];
  /** True while the assistant reply is still streaming in. */
  streaming?: boolean;
  /** Set when this message failed to complete. */
  error?: string;
}

/** One line in a `steps` part's activity timeline. */
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
