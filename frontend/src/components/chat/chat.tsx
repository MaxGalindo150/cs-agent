"use client";

import { useCallback, useEffect, useRef } from "react";

import { ChatHeader } from "@/components/chat/chat-header";
import { ChatInput } from "@/components/chat/chat-input";
import type { CheoMood } from "@/components/chat/cheo";
import { ConversationSidebar } from "@/components/chat/conversation-sidebar";
import { MessageList } from "@/components/chat/message-list";
import { isRunningTool } from "@/components/chat/tool-activity";
import { useChat } from "@/hooks/use-chat";
import { useConversations } from "@/hooks/use-conversations";
import { deleteConversation } from "@/lib/chat/api";
import { cn } from "@/lib/utils";
import type { ChatAuth } from "@/lib/chat/auth";
import type { Message } from "@/lib/chat/types";

/** The words that change with who the chat is for. */
export interface ChatCopy {
  title: string;
  /** Under the title in the header, e.g. "Soporte Cashea". */
  headerSubtitle?: string;
  greeting: string;
  subtitle: string;
  suggestions: string[];
  /** The composer's placeholder. */
  placeholder?: string;
}

/** Who the chat is talking as. Supplied by the surface hosting it: the demo
 *  page's simulated login, or the host app's identity in the embed. */
export interface ChatIdentity {
  /** Omit for an anonymous visitor. Must be stable across renders. */
  auth?: ChatAuth;
  /** Shown in the header, e.g. "Alice Johnson" or "Invitado". */
  label: string;
  /** Changes when a different person takes over; starts a fresh conversation. */
  key: string | null;
}

const ANONYMOUS: ChatIdentity = { label: "Invitado", key: null };

const DEFAULT_COPY: ChatCopy = {
  title: "Soporte Cashea",
  greeting: "¿En qué puedo ayudarte?",
  subtitle: "Escríbenos y te respondemos al momento.",
  suggestions: [
    "¿Dónde está mi orden?",
    "¿Cómo pago mi cuota?",
    "Olvidé mi contraseña",
    "Hablar con una persona",
  ],
};

interface ChatProps {
  /**
   * "page": standalone full-screen chat with the conversation sidebar
   * (default). "widget": embedded in the floating support bubble — no
   * sidebar (there's no room, and Tailwind's `sm:` breakpoint checks the
   * browser viewport, not this panel's own width, so it can't be hidden by
   * CSS alone in a narrow container).
   */
  variant?: "page" | "widget";
  /** localStorage key for the active conversation — see UseChatOptions. */
  storageKey?: string;
  copy?: ChatCopy;
  identity?: ChatIdentity;
  /** Show who the chat is talking as in the header (the demo's identity
   *  harness). The embed turns it off: the host's user knows who they are. */
  showIdentity?: boolean;
  /** Offer image attachments in the composer. */
  allowAttachments?: boolean;
  /** Open an order card in the host app; cards aren't clickable without it. */
  onOpenOrder?: (orderUuid: string) => void;
}

/** Top-level chat screen: sidebar, header, scrollable transcript, and composer. */
export function Chat({
  variant = "page",
  storageKey,
  copy = DEFAULT_COPY,
  identity = ANONYMOUS,
  showIdentity = true,
  allowAttachments = true,
  onOpenOrder,
}: ChatProps) {
  const isWidget = variant === "widget";
  const { auth } = identity;
  const { conversations, refresh } = useConversations(auth);
  const { messages, isStreaming, conversationId, send, sendChoice, stop, reset, load, rate } =
    useChat({ onConversationUpdate: refresh, storageKey, auth });

  // A different person taking over starts a fresh conversation — the old
  // thread belongs to the previous identity, and agent-service would refuse
  // to continue it anyway. Skip the mount run so it doesn't clobber the
  // conversation useChat is restoring from localStorage.
  const skipFirstIdentityChange = useRef(true);
  useEffect(() => {
    if (skipFirstIdentityChange.current) {
      skipFirstIdentityChange.current = false;
      return;
    }
    reset();
  }, [identity.key, reset]);

  const cheoMood = moodFor(messages[messages.length - 1], isStreaming);

  const handleDelete = useCallback(
    (id: string) => {
      if (!window.confirm("¿Eliminar esta conversación?")) return;
      deleteConversation(id, auth)
        .then(() => {
          if (id === conversationId) reset();
          refresh();
        })
        .catch(() => {
          // Non-fatal: leave the list as-is if the delete fails.
        });
    },
    [conversationId, reset, refresh, auth],
  );

  return (
    <div className={cn("flex h-full bg-background text-foreground", isWidget && "chat-compact")}>
      {!isWidget && (
        <ConversationSidebar
          conversations={conversations}
          activeId={conversationId}
          onSelect={load}
          onNewChat={reset}
          onDelete={handleDelete}
        />
      )}

      <div className="flex h-full min-w-0 flex-1 flex-col">
        <ChatHeader
          title={copy.title}
          subtitle={copy.headerSubtitle}
          onNewChat={reset}
          alwaysShowNewChat={isWidget}
          identityLabel={showIdentity ? identity.label : undefined}
          busy={isStreaming}
          mood={cheoMood}
        />

        <div className="flex-1 overflow-y-auto">
          <div
            className={cn(
              "mx-auto flex h-full w-full max-w-3xl flex-col px-4",
              isWidget ? "py-4" : "py-6",
            )}
          >
            <MessageList
              messages={messages}
              copy={copy}
              onSuggestion={send}
              onChoice={sendChoice}
              disableChoices={isStreaming}
              onOpenOrder={onOpenOrder}
              onRate={rate}
            />
          </div>
        </div>

        <div className="shrink-0">
          <div className={cn("mx-auto w-full max-w-3xl px-4", isWidget ? "pb-4" : "pb-6")}>
            <ChatInput
              isStreaming={isStreaming}
              onSend={send}
              onStop={stop}
              placeholder={copy.placeholder}
              allowAttachments={allowAttachments}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

/** Cheo in the header: working while a tool runs, attentive until the reply
 *  starts to show, then back to floating while it's written out. */
function moodFor(last: Message | undefined, isStreaming: boolean): CheoMood {
  if (!isStreaming || !last) return "idle";
  const parts = last.parts;
  if (parts.some((p) => p.type === "steps" && p.steps.some(isRunningTool))) return "working";
  if (!parts.some((p) => p.type === "text" && p.text.trim())) return "attentive";
  return "idle";
}
