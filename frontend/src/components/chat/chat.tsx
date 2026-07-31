"use client";

import { useCallback } from "react";

import { ChatHeader } from "@/components/chat/chat-header";
import { ChatInput } from "@/components/chat/chat-input";
import { ConversationSidebar } from "@/components/chat/conversation-sidebar";
import { MessageList } from "@/components/chat/message-list";
import { useChat } from "@/hooks/use-chat";
import { useConversations } from "@/hooks/use-conversations";
import { deleteConversation } from "@/lib/chat/api";

/** Top-level chat screen: sidebar, header, scrollable transcript, and composer. */
export function Chat() {
  const { conversations, refresh } = useConversations();
  const { messages, isStreaming, conversationId, send, stop, reset, load } =
    useChat({ onConversationUpdate: refresh });

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
      <ConversationSidebar
        conversations={conversations}
        activeId={conversationId}
        onSelect={load}
        onNewChat={reset}
        onDelete={handleDelete}
      />

      <div className="flex h-full min-w-0 flex-1 flex-col">
        <ChatHeader onNewChat={reset} />

        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto flex h-full w-full max-w-3xl flex-col px-4 py-6">
            <MessageList messages={messages} onSuggestion={send} />
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
