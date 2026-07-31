"use client";

import { useEffect, useRef } from "react";

import { MessageBubble } from "@/components/chat/message-bubble";
import type { Message } from "@/lib/chat/types";

interface MessageListProps {
  messages: Message[];
  /** Send a suggested prompt from the empty state. */
  onSuggestion?: (text: string) => void;
}

const SUGGESTIONS = [
  "How do I reset my password?",
  "Where is my order?",
  "Cancel my subscription",
  "Talk to a human",
];

/** Scrollable list of messages. Auto-scrolls to the bottom as content grows. */
export function MessageList({ messages, onSuggestion }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Re-run on every content change so the view tracks the streaming reply.
  // Activity steps count too: they render before the first token, so without
  // them the timeline would appear below the fold on a long transcript.
  const last = messages[messages.length - 1];
  const lastContent = last?.content;
  const lastSteps = last?.steps?.length ?? 0;
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, lastContent, lastSteps]);

  if (messages.length === 0) {
    return <EmptyState onSuggestion={onSuggestion} />;
  }

  return (
    <div className="flex flex-col gap-8">
      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}

function EmptyState({ onSuggestion }: { onSuggestion?: (text: string) => void }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-6 text-center">
      <div className="space-y-2">
        <h2 className="text-2xl font-medium tracking-tight text-zinc-100">
          How can I help?
        </h2>
        <p className="text-sm text-zinc-500">
          Ask anything and the assistant will reply in real time.
        </p>
      </div>

      <div className="flex max-w-md flex-wrap justify-center gap-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => onSuggestion?.(s)}
            className="rounded-full border border-zinc-800 px-3.5 py-1.5 text-sm text-zinc-400 transition-colors duration-150 hover:bg-zinc-900 hover:text-zinc-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-700"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
