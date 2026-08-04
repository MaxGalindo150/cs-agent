"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { fetchMessages, streamChat } from "@/lib/chat/api";
import type {
  ActivityStep,
  AttachedImage,
  ChoiceOption,
  Message,
  MessagePart,
} from "@/lib/chat/types";

// Remembers the active conversation across reloads.
const STORAGE_KEY = "csa:conversationId";

function newId(): string {
  // crypto.randomUUID is available in all modern browsers.
  return crypto.randomUUID();
}

export interface UseChatOptions {
  /** Called after a send settles (reply persisted) so callers can refresh the
   *  conversation list. */
  onConversationUpdate?: () => void;
  /** The simulated host-app identity to attach to every sent message (see
   *  lib/identity/). Omit for an anonymous/guest visitor. */
  principal?: { userId: string; email?: string };
}

export interface UseChat {
  messages: Message[];
  /** True while a reply is streaming in. */
  isStreaming: boolean;
  /** Id of the active conversation, or null for a fresh (unsent) one. */
  conversationId: string | null;
  /** Send a user message, optionally with images attached as context, and
   *  stream the assistant reply. */
  send: (text: string, images?: AttachedImage[]) => void;
  /** Resolve a pending `present_choice` by clicking one of its options,
   *  instead of typing. */
  sendChoice: (optionId: string) => void;
  /** Cancel the in-flight stream, keeping whatever text arrived so far. */
  stop: () => void;
  /** Start a fresh conversation: clear the transcript and forget the thread. */
  reset: () => void;
  /** Load an existing conversation's transcript into the view. */
  load: (id: string) => void;
}

/**
 * Owns the chat conversation state and the streaming lifecycle.
 *
 * The backend threads messages by session id: the first send mints a session
 * and announces its id in the stream's opening `session` frame, which we
 * remember and send on every subsequent message so the server rebuilds the
 * full history. The active id is persisted to localStorage so a reload reopens
 * the same conversation. `reset` starts a new thread; `load` opens an existing.
 */
export function useChat(options: UseChatOptions = {}): UseChat {
  const { onConversationUpdate, principal } = options;

  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  // Mirrors conversationId for reads inside async callbacks (no stale closure).
  const conversationIdRef = useRef<string | null>(null);

  const setConversation = useCallback((id: string | null) => {
    conversationIdRef.current = id;
    setConversationId(id);
  }, []);

  const patch = useCallback((id: string, changes: Partial<Message>) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, ...changes } : m)),
    );
  }, []);

  /** Append an activity step to the assistant message being built. Joins the
   *  trailing `steps` part if the last thing that happened was also a step
   *  (a tool batch), else opens a new one — so a step that starts after some
   *  text becomes its own group, in place, rather than merging into an
   *  unrelated earlier group above the text. */
  const addStep = useCallback((id: string, step: ActivityStep) => {
    setMessages((prev) =>
      prev.map((m) => {
        if (m.id !== id) return m;
        const last = m.parts[m.parts.length - 1];
        if (last?.type === "steps") {
          const parts = m.parts.slice(0, -1);
          return { ...m, parts: [...parts, { ...last, steps: [...last.steps, step] }] };
        }
        const part: MessagePart = { type: "steps", steps: [step] };
        return { ...m, parts: [...m.parts, part] };
      }),
    );
  }, []);

  /** Close the oldest still-running step for `tool`, across every `steps`
   *  part (not just the last one). Tools run in batches and results arrive
   *  in completion order, not call order, so matching by name (rather than
   *  by position) is what keeps a batch of two `get_order` calls from
   *  marking the same row done twice. */
  const finishStep = useCallback((id: string, tool: string) => {
    setMessages((prev) =>
      prev.map((m) => {
        if (m.id !== id) return m;
        let closed = false;
        return {
          ...m,
          parts: m.parts.map((part) => {
            if (closed || part.type !== "steps") return part;
            return {
              ...part,
              steps: part.steps.map((s) => {
                if (closed || s.tool !== tool || s.status !== "running") return s;
                closed = true;
                return { ...s, status: "done" as const };
              }),
            };
          }),
        };
      }),
    );
  }, []);

  /** Append a `present_choice` prompt to the assistant message being built —
   *  always its own part (never joined with an adjacent one), since a choice
   *  widget is never merged with surrounding text or tool steps. */
  const addChoice = useCallback(
    (id: string, prompt: string, options: ChoiceOption[]) => {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === id
            ? { ...m, parts: [...m.parts, { type: "choice" as const, prompt, options }] }
            : m,
        ),
      );
    },
    [],
  );

  /** Settle the most recent still-open `choice` part — so answering visibly
   *  resolves it right away, without waiting for a reload to show it settled.
   *  Called with an `optionId` when the customer clicked a button (highlights
   *  that option); called with none when they typed free text instead
   *  (settles the widget with nothing highlighted — mirrors the backend's
   *  `mark_choice_resolved(..., resolved_option_id=None)`). */
  const resolveChoice = useCallback((optionId?: string) => {
    setMessages((prev) => {
      const target = [...prev]
        .reverse()
        .find((m) => m.parts.some((p) => p.type === "choice" && !p.resolved));
      if (!target) return prev;
      return prev.map((m) =>
        m.id !== target.id
          ? m
          : {
              ...m,
              parts: m.parts.map((p) =>
                p.type === "choice" && !p.resolved
                  ? {
                      ...p,
                      resolved: true,
                      ...(optionId ? { resolvedOptionId: optionId } : {}),
                    }
                  : p,
              ),
            },
      );
    });
  }, []);

  /** Append a text delta to the assistant message being built. Joins the
   *  trailing `text` part if the last thing that happened was also text,
   *  else opens a new part — so text that resumes after a tool call becomes
   *  its own segment, positioned after that tool's activity. */
  const appendDelta = useCallback((id: string, delta: string) => {
    setMessages((prev) =>
      prev.map((m) => {
        if (m.id !== id) return m;
        const last = m.parts[m.parts.length - 1];
        if (last?.type === "text") {
          const parts = m.parts.slice(0, -1);
          return { ...m, parts: [...parts, { type: "text", text: last.text + delta }] };
        }
        const part: MessagePart = { type: "text", text: delta };
        return { ...m, parts: [...m.parts, part] };
      }),
    );
  }, []);

  const send = useCallback(
    (text: string, images?: AttachedImage[]) => {
      const trimmed = text.trim();
      if (!trimmed || isStreaming) return;

      // Typing instead of clicking still resolves any open choice widget —
      // the backend clears the suspension either way, so the live UI must
      // not keep showing those buttons as answerable.
      resolveChoice();

      // Images render above the caption, like most chat apps — read as
      // "here's the picture, and here's what I'm saying about it".
      const userParts: MessagePart[] = (images ?? []).map((img) => ({
        type: "image",
        previewUrl: img.previewUrl,
      }));
      userParts.push({ type: "text", text: trimmed });

      const userMessage: Message = {
        id: newId(),
        role: "user",
        parts: userParts,
      };
      const assistantId = newId();
      const assistantMessage: Message = {
        id: assistantId,
        role: "assistant",
        parts: [],
        streaming: true,
      };

      setMessages((prev) => [...prev, userMessage, assistantMessage]);
      setIsStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      streamChat({
        message: trimmed,
        conversationId: conversationIdRef.current ?? undefined,
        images,
        principal,
        signal: controller.signal,
        onConversationId: (id) => setConversation(id),
        onGate: (decision) => {
          // Recorded as already done: the search that follows the gate emits no
          // completion event of its own (it is a fast local query), so a
          // "running" row here would never resolve.
          if (decision === "retrieve") {
            addStep(assistantId, {
              id: newId(),
              kind: "memory",
              label: "Searched memory",
              status: "done",
            });
          }
        },
        onToolStart: (tool, label) =>
          addStep(assistantId, {
            id: newId(),
            kind: "tool",
            tool,
            label,
            status: "running",
          }),
        onTool: (event) => finishStep(assistantId, event.tool),
        onChoice: (prompt, options) => addChoice(assistantId, prompt, options),
        onDelta: (delta) => appendDelta(assistantId, delta),
        onNeedsHuman: () => patch(assistantId, { needsHuman: true }),
      })
        .then(() => patch(assistantId, { streaming: false }))
        .catch((err: unknown) => {
          // A user-triggered abort is not an error.
          if (controller.signal.aborted) {
            patch(assistantId, { streaming: false });
            return;
          }
          const detail = err instanceof Error ? err.message : "unknown error";
          patch(assistantId, { streaming: false, error: detail });
        })
        .finally(() => {
          setIsStreaming(false);
          abortRef.current = null;
          onConversationUpdate?.();
        });
    },
    [
      isStreaming,
      patch,
      addStep,
      finishStep,
      addChoice,
      resolveChoice,
      appendDelta,
      setConversation,
      onConversationUpdate,
      principal,
    ],
  );

  /** Resolve a pending `present_choice` by option id — the button-click
   *  sibling of `send`. No new user bubble: the choice widget itself settles
   *  in place (`resolveChoice`) to show what was picked. */
  const sendChoice = useCallback(
    (optionId: string) => {
      if (isStreaming) return;
      resolveChoice(optionId);

      const assistantId = newId();
      const assistantMessage: Message = {
        id: assistantId,
        role: "assistant",
        parts: [],
        streaming: true,
      };
      setMessages((prev) => [...prev, assistantMessage]);
      setIsStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      streamChat({
        choiceId: optionId,
        conversationId: conversationIdRef.current ?? undefined,
        principal,
        signal: controller.signal,
        onConversationId: (id) => setConversation(id),
        onGate: (decision) => {
          if (decision === "retrieve") {
            addStep(assistantId, {
              id: newId(),
              kind: "memory",
              label: "Searched memory",
              status: "done",
            });
          }
        },
        onToolStart: (tool, label) =>
          addStep(assistantId, {
            id: newId(),
            kind: "tool",
            tool,
            label,
            status: "running",
          }),
        onTool: (event) => finishStep(assistantId, event.tool),
        onChoice: (prompt, options) => addChoice(assistantId, prompt, options),
        onDelta: (delta) => appendDelta(assistantId, delta),
        onNeedsHuman: () => patch(assistantId, { needsHuman: true }),
      })
        .then(() => patch(assistantId, { streaming: false }))
        .catch((err: unknown) => {
          if (controller.signal.aborted) {
            patch(assistantId, { streaming: false });
            return;
          }
          const detail = err instanceof Error ? err.message : "unknown error";
          patch(assistantId, { streaming: false, error: detail });
        })
        .finally(() => {
          setIsStreaming(false);
          abortRef.current = null;
          onConversationUpdate?.();
        });
    },
    [
      isStreaming,
      patch,
      addStep,
      finishStep,
      addChoice,
      resolveChoice,
      appendDelta,
      setConversation,
      onConversationUpdate,
      principal,
    ],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setConversation(null);
    setMessages([]);
    setIsStreaming(false);
  }, [setConversation]);

  const load = useCallback(
    (id: string) => {
      abortRef.current?.abort();
      abortRef.current = null;
      setIsStreaming(false);
      setConversation(id);
      fetchMessages(id)
        .then((msgs) => setMessages(msgs))
        .catch(() => {
          // The conversation is gone (e.g. deleted) or unreachable: drop it so
          // we don't keep a broken active thread around.
          setConversation(null);
          setMessages([]);
        });
    },
    [setConversation],
  );

  // Restore the last active conversation on mount (once). We fetch first and set
  // state in the async callback (not synchronously in the effect body).
  const didRestore = useRef(false);
  useEffect(() => {
    if (didRestore.current) return;
    didRestore.current = true;
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (!stored) return;
    fetchMessages(stored)
      .then((msgs) => {
        setConversation(stored);
        setMessages(msgs);
      })
      .catch(() => {
        // Stored conversation is gone (e.g. deleted) — forget it.
        window.localStorage.removeItem(STORAGE_KEY);
      });
  }, [setConversation]);

  // Persist the active conversation. Skip the first run so mount doesn't wipe
  // the stored id before the restore effect reads it.
  const firstPersist = useRef(true);
  useEffect(() => {
    if (firstPersist.current) {
      firstPersist.current = false;
      return;
    }
    if (conversationId) {
      window.localStorage.setItem(STORAGE_KEY, conversationId);
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  }, [conversationId]);

  return { messages, isStreaming, conversationId, send, sendChoice, stop, reset, load };
}
