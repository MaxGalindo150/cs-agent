"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { fetchMessages, streamChat } from "@/lib/chat/api";
import type { ActivityStep, Message } from "@/lib/chat/types";

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
}

export interface UseChat {
  messages: Message[];
  /** True while a reply is streaming in. */
  isStreaming: boolean;
  /** Id of the active conversation, or null for a fresh (unsent) one. */
  conversationId: string | null;
  /** Send a user message and stream the assistant reply. */
  send: (text: string) => void;
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
  const { onConversationUpdate } = options;

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

  /** Append an activity step to the assistant message being built. */
  const addStep = useCallback((id: string, step: ActivityStep) => {
    setMessages((prev) =>
      prev.map((m) =>
        m.id === id ? { ...m, steps: [...(m.steps ?? []), step] } : m,
      ),
    );
  }, []);

  /** Close the oldest still-running step for `tool`. Tools run in batches and
   *  results arrive in completion order, not call order, so matching by name
   *  (rather than by position) is what keeps a batch of two `get_order` calls
   *  from marking the same row done twice. */
  const finishStep = useCallback((id: string, tool: string) => {
    setMessages((prev) =>
      prev.map((m) => {
        if (m.id !== id || !m.steps) return m;
        let closed = false;
        return {
          ...m,
          steps: m.steps.map((s) => {
            if (closed || s.tool !== tool || s.status !== "running") return s;
            closed = true;
            return { ...s, status: "done" as const };
          }),
        };
      }),
    );
  }, []);

  const send = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isStreaming) return;

      const userMessage: Message = {
        id: newId(),
        role: "user",
        content: trimmed,
      };
      const assistantId = newId();
      const assistantMessage: Message = {
        id: assistantId,
        role: "assistant",
        content: "",
        streaming: true,
      };

      setMessages((prev) => [...prev, userMessage, assistantMessage]);
      setIsStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      streamChat({
        message: trimmed,
        conversationId: conversationIdRef.current ?? undefined,
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
        onDelta: (delta) =>
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: m.content + delta }
                : m,
            ),
          ),
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
      setConversation,
      onConversationUpdate,
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

  return { messages, isStreaming, conversationId, send, stop, reset, load };
}
