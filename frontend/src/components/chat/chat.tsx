"use client";

import { useCallback, useEffect, useRef } from "react";

import { ChatHeader } from "@/components/chat/chat-header";
import { ChatInput } from "@/components/chat/chat-input";
import { ConversationSidebar } from "@/components/chat/conversation-sidebar";
import { MessageList } from "@/components/chat/message-list";
import { useChat } from "@/hooks/use-chat";
import { useConversations } from "@/hooks/use-conversations";
import { deleteConversation } from "@/lib/chat/api";
import { useIdentity } from "@/lib/identity/context";

interface ChatProps {
  /**
   * "page": standalone full-screen chat with the conversation sidebar
   * (default). "widget": embedded in the floating support bubble — no
   * sidebar (there's no room, and Tailwind's `sm:` breakpoint checks the
   * browser viewport, not this panel's own width, so it can't be hidden by
   * CSS alone in a narrow container). Which conversations belong to an
   * anonymous widget visitor isn't tracked yet (needs a cookie or similar) —
   * hiding the sidebar sidesteps that for now rather than showing everyone's.
   */
  variant?: "page" | "widget";
}

/** Top-level chat screen: sidebar, header, scrollable transcript, and composer. */
export function Chat({ variant = "page" }: ChatProps) {
  const isWidget = variant === "widget";
  const { conversations, refresh } = useConversations();
  const { activeUser } = useIdentity();
  const { messages, isStreaming, conversationId, send, sendChoice, stop, reset, load } =
    useChat({
      onConversationUpdate: refresh,
      principal: activeUser
        ? { userId: activeUser.id, email: activeUser.email }
        : undefined,
    });

  // Switching who's "logged in" starts a fresh conversation — continuing an
  // existing thread under a different identity would be confusing (the
  // session was minted under the previous one) and makes it easy to test the
  // authenticated/anonymous branches cleanly, one at a time. Skip the first
  // run: IdentityProvider restores the last logged-in user asynchronously
  // after mount, and that initial hydration must not clobber the conversation
  // useChat is simultaneously restoring from its own localStorage key.
  const skipFirstIdentityChange = useRef(true);
  useEffect(() => {
    if (skipFirstIdentityChange.current) {
      skipFirstIdentityChange.current = false;
      return;
    }
    reset();
  }, [activeUser?.id, reset]);

  const handleDelete = useCallback(
    (id: string) => {
      if (!window.confirm("Delete this conversation?")) return;
      deleteConversation(id)
        .then(() => {
          if (id === conversationId) reset();
          refresh();
        })
        .catch(() => {
          // Non-fatal: leave the list as-is if the delete fails.
        });
    },
    [conversationId, reset, refresh],
  );

  return (
    <div className="flex h-full bg-background text-foreground">
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
          onNewChat={reset}
          alwaysShowNewChat={isWidget}
          identityLabel={
            activeUser ? `${activeUser.firstName} ${activeUser.lastName}` : "Guest"
          }
        />

        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto flex h-full w-full max-w-3xl flex-col px-4 py-6">
            <MessageList
              messages={messages}
              onSuggestion={send}
              onChoice={sendChoice}
              disableChoices={isStreaming}
            />
          </div>
        </div>

        <div className="shrink-0">
          <div className="mx-auto w-full max-w-3xl px-4 pb-6">
            <ChatInput isStreaming={isStreaming} onSend={send} onStop={stop} />
          </div>
        </div>
      </div>
    </div>
  );
}
