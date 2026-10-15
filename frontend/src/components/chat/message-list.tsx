"use client";

import { useEffect, useRef } from "react";

import { MessageBubble } from "@/components/chat/message-bubble";
import type { ChatCopy } from "@/components/chat/chat";
import type { Message } from "@/lib/chat/types";

interface MessageListProps {
  messages: Message[];
  copy: ChatCopy;
  /** Send a suggested prompt from the empty state. */
  onSuggestion?: (text: string) => void;
  /** Resolve a pending `present_choice` by option id. */
  onChoice?: (optionId: string) => void;
  /** True while any turn is in flight — disables live choice buttons. */
  disableChoices?: boolean;
  /** Open an order card in the host app. */
  onOpenOrder?: (orderUuid: string) => void;
}

/** Scrollable list of messages. Auto-scrolls to the bottom as content grows. */
export function MessageList({
  messages,
  copy,
  onSuggestion,
  onChoice,
  disableChoices,
  onOpenOrder,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Re-run whenever the last message's parts grow (a new delta, a new tool
  // group) so the view tracks the streaming reply — steps included, since
  // they render as soon as a tool starts, before any text arrives.
  const last = messages[messages.length - 1];
  const lastPartCount = last?.parts.length ?? 0;
  const lastPart = last?.parts[last.parts.length - 1];
  const lastPartSize =
    lastPart?.type === "text"
      ? lastPart.text.length
      : lastPart?.type === "steps"
        ? lastPart.steps.length
        : lastPart?.type === "choice"
          ? lastPart.options.length
          : 0;
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, lastPartCount, lastPartSize]);

  if (messages.length === 0) {
    return <EmptyState copy={copy} onSuggestion={onSuggestion} />;
  }

  return (
    <div className="flex flex-col gap-[calc(var(--chat-block-gap)*2)]">
      {messages.map((message, i) => (
        <MessageBubble
          key={message.id}
          message={message}
          onChoice={onChoice}
          disableChoices={disableChoices}
          isLatest={i === messages.length - 1}
          onSuggestion={onSuggestion}
          onOpenOrder={onOpenOrder}
        />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}

function EmptyState({
  copy,
  onSuggestion,
}: {
  copy: ChatCopy;
  onSuggestion?: (text: string) => void;
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-6 text-center">
      <div className="space-y-2">
        <h2 className="text-2xl font-medium tracking-tight text-foreground">
          {copy.greeting}
        </h2>
        <p className="text-sm text-muted-foreground">
          {copy.subtitle}
        </p>
      </div>

      <div className="flex max-w-md flex-wrap justify-center gap-2">
        {copy.suggestions.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => onSuggestion?.(s)}
            className="rounded-full border border-border px-3.5 py-1.5 text-sm text-muted-foreground transition-colors duration-150 hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
