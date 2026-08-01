// Client for the agent-service HTTP API.
//
// Streaming chat is POST /v1/chat/stream. Unlike a plain text stream, every SSE
// frame here is *named* and its `data:` payload is JSON:
//
//   event: session        data: {"session_id": "<uuid>"}      always the first frame
//   event: gate           data: {"decision": "retrieve"|"skip"}  memory lookup decided
//   event: tool_start     data: {"tool","label"}              a tool is about to run
//   event: tool           data: {"tool","args","output"}      that tool finished
//   event: delta          data: "<text chunk>"                one piece of the reply
//   event: limit_reached  data: {...}                         a budget guard tripped
//   event: done           data: "<full reply>"                finished cleanly
//   event: error          data: "<safe message>"              failed mid-stream
//
// `tool_start` and `tool` pair up by tool name in arrival order: the agent runs
// a batch concurrently, so N starts arrive, then N results as they land.
//
// The browser's native EventSource only supports GET, so we drive the stream
// ourselves with fetch + a ReadableStream reader and parse the SSE frames.
//
// Naming: the API's "session" is the UI's "conversation" (see lib/chat/types.ts).

import type {
  ActivityStep,
  AttachedImage,
  ConversationSummary,
  Message,
  MessagePart,
  ToolEvent,
} from "@/lib/chat/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface StreamChatOptions {
  message: string;
  /** Continue an existing conversation. Omit to start a new one. */
  conversationId?: string;
  /** Images attached as context for this turn only — never replayed on later
   *  turns (see AttachedImage). */
  images?: AttachedImage[];
  /**
   * The simulated host-app identity (see lib/identity/), forwarded as
   * X-User-Id/X-User-Email headers for agent-service's identity harness.
   * Omit for an anonymous/guest visitor.
   */
  principal?: { userId: string; email?: string };
  /** Called for every text delta as it arrives. */
  onDelta: (delta: string) => void;
  /**
   * Called once with the conversation (session) id, before the first delta.
   * For a new conversation this is the freshly minted id.
   */
  onConversationId?: (id: string) => void;
  /** Called when the agent decided whether to search its memory. */
  onGate?: (decision: "retrieve" | "skip") => void;
  /**
   * Called when a tool starts, before it has run. `label` is written by the
   * tool itself on the server, so this client needs no knowledge of which
   * tools exist or what their arguments are called.
   */
  onToolStart?: (tool: string, label: string) => void;
  /** Called when a tool finishes, with its (truncated) result. */
  onTool?: (event: ToolEvent) => void;
  /** Called when the agent hit a budget guard (max turns / tool calls). */
  onLimitReached?: (detail: unknown) => void;
  /** Lets the caller cancel the request (e.g. a stop button or unmount). */
  signal?: AbortSignal;
}

/**
 * Sends a message and resolves once the assistant reply has fully streamed in.
 * Rejects on network errors, non-2xx responses, or a server error event.
 * Throwing on the abort case is left to the caller to interpret via the signal.
 */
export async function streamChat({
  message,
  conversationId,
  images,
  principal,
  onDelta,
  onConversationId,
  onGate,
  onToolStart,
  onTool,
  onLimitReached,
  signal,
}: StreamChatOptions): Promise<void> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (principal?.userId) headers["X-User-Id"] = principal.userId;
  if (principal?.email) headers["X-User-Email"] = principal.email;

  const res = await fetch(`${API_URL}/v1/chat/stream`, {
    method: "POST",
    headers,
    // `session_id: undefined` is dropped by JSON.stringify, so a new
    // conversation sends just `{ message }` and the server mints an id.
    body: JSON.stringify({
      message,
      session_id: conversationId,
      images: images?.map((img) => ({ media_type: img.mediaType, data: img.data })),
    }),
    signal,
  });

  if (!res.ok) {
    throw new Error(`request failed: ${res.status} ${res.statusText}`);
  }
  if (!res.body) {
    throw new Error("response has no body to stream");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  // Tracked so a turn that produced no deltas still renders: `done` carries the
  // full reply, and we fall back to it rather than leaving an empty bubble.
  let sawDelta = false;

  const handleFrame = (raw: string): boolean => {
    const { event, data } = parseSseEvent(raw);
    if (!event || !data) return false;

    // Every payload is JSON — a bare chunk would be a protocol violation, so
    // let a parse failure surface rather than guessing.
    const payload: unknown = JSON.parse(data);

    switch (event) {
      case "session": {
        const id = (payload as { session_id?: string }).session_id;
        if (id) onConversationId?.(id);
        return false;
      }
      case "delta": {
        sawDelta = true;
        onDelta(String(payload));
        return false;
      }
      case "gate": {
        const decision = (payload as { decision?: string }).decision;
        if (decision === "retrieve" || decision === "skip") onGate?.(decision);
        return false;
      }
      case "tool_start": {
        const { tool, label } = payload as { tool: string; label?: string };
        // The server always sends a label (it derives one when the tool
        // declares none); the fallback only covers an older server.
        onToolStart?.(tool, label || tool);
        return false;
      }
      case "tool": {
        onTool?.(payload as ToolEvent);
        return false;
      }
      case "limit_reached": {
        onLimitReached?.(payload);
        return false;
      }
      case "done": {
        const full = String(payload);
        if (!sawDelta && full) onDelta(full);
        return true; // terminal
      }
      case "error":
        throw new Error(String(payload) || "stream error");
      default:
        // Unknown event: ignore it rather than break — the server may add
        // frames (new tool kinds, telemetry) before this client knows them.
        return false;
    }
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // SSE events are separated by a blank line. Process every complete event
      // in the buffer and keep the trailing partial one for the next read.
      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const rawEvent = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        if (handleFrame(rawEvent)) return;
      }
    }
    // The server closed without a blank line after the last frame.
    if (buffer.trim()) handleFrame(buffer);
  } finally {
    reader.releaseLock();
  }
}

/** Lists conversations (most-recently-active first) for the sidebar. */
export async function listConversations(): Promise<ConversationSummary[]> {
  const res = await fetch(`${API_URL}/v1/sessions`);
  if (!res.ok) {
    throw new Error(`request failed: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

/** Fetches the full transcript of a conversation. */
export async function fetchMessages(conversationId: string): Promise<Message[]> {
  const res = await fetch(`${API_URL}/v1/sessions/${conversationId}/messages`);
  if (!res.ok) {
    throw new Error(`request failed: ${res.status} ${res.statusText}`);
  }
  const rows: Array<{
    id: string;
    role: string;
    content: string;
    meta: Record<string, unknown> | null;
  }> = await res.json();
  return rows.map((m) => ({
    id: m.id,
    role: m.role === "user" ? "user" : "assistant",
    parts: partsFromSegments(m.meta?.segments, m.content),
  }));
}

/** Deletes a conversation and its messages. */
export async function deleteConversation(conversationId: string): Promise<void> {
  const res = await fetch(`${API_URL}/v1/sessions/${conversationId}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    throw new Error(`request failed: ${res.status} ${res.statusText}`);
  }
}

/**
 * Rebuilds a reloaded assistant message's ordered parts from
 * `meta.segments` (agent-service's `agent/loop/agent.py::LoopResult.segments`,
 * persisted verbatim). Falls back to one text part built from `content` when
 * there's no usable segments — an older row logged before this existed, or a
 * plain user message, which never has segments.
 *
 * Treated as untrusted wire data (server JSON, not a typed contract): a
 * malformed segment is skipped rather than trusted, so one bad row degrades
 * to the plain-text fallback instead of crashing the whole transcript.
 */
function partsFromSegments(segments: unknown, fallbackContent: string): MessagePart[] {
  const fallback: MessagePart[] = fallbackContent
    ? [{ type: "text", text: fallbackContent }]
    : [];
  if (!Array.isArray(segments) || segments.length === 0) return fallback;

  const parts: MessagePart[] = [];
  for (const raw of segments) {
    if (!raw || typeof raw !== "object") continue;
    const seg = raw as Record<string, unknown>;
    if (seg.type === "text" && typeof seg.text === "string") {
      parts.push({ type: "text", text: seg.text });
    } else if (seg.type === "tools" && Array.isArray(seg.calls)) {
      const steps = stepsFromCalls(seg.calls);
      if (steps.length > 0) parts.push({ type: "steps", steps });
    }
  }
  return parts.length > 0 ? parts : fallback;
}

function stepsFromCalls(calls: unknown[]): ActivityStep[] {
  const steps: ActivityStep[] = [];
  calls.forEach((raw, i) => {
    if (!raw || typeof raw !== "object") return;
    const call = raw as Record<string, unknown>;
    const tool = typeof call.tool === "string" ? call.tool : undefined;
    const label = typeof call.label === "string" ? call.label : (tool ?? "Tool call");
    steps.push({ id: `${tool ?? "tool"}-${i}`, kind: "tool", tool, label, status: "done" });
  });
  return steps;
}

/** Parses a single raw SSE event block into its event name and joined data. */
function parseSseEvent(raw: string): { event: string; data: string } {
  let event = "";
  const dataLines: string[] = [];

  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      // Per the SSE spec, strip a single leading space after the colon.
      dataLines.push(line.slice("data:".length).replace(/^ /, ""));
    }
    // Lines starting with ":" are comments/keepalives — skipped.
  }

  return { event, data: dataLines.join("\n") };
}
