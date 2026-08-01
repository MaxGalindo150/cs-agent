import { Markdown } from "@/components/chat/markdown";
import { ToolActivity } from "@/components/chat/tool-activity";
import type { Message } from "@/lib/chat/types";

interface MessageBubbleProps {
  message: Message;
}

/** A single chat turn. User messages are right-aligned bubbles; assistant
 *  messages flow full-width (no bubble) like ChatGPT / Claude.ai.
 *
 *  An assistant turn renders its `parts` in the order they happened — text,
 *  then a tool's activity, then more text — rather than hoisting every tool
 *  call above the whole reply. That is what lets "I'll escalate this" ->
 *  [escalating…] -> "Done" read as one sequence instead of the agent
 *  seemingly talking to itself. */
export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  if (isUser) {
    const text = message.parts.find((p) => p.type === "text")?.text ?? "";
    return (
      <div className="flex w-full justify-end">
        <div className="max-w-[75%] rounded-2xl bg-zinc-800/60 px-4 py-2.5 text-[15px] leading-7 break-words whitespace-pre-wrap text-zinc-100 shadow-md shadow-black/20 ring-1 ring-white/10 backdrop-blur-sm">
          {text}
        </div>
      </div>
    );
  }

  const isEmptyStreaming = message.streaming && message.parts.length === 0;
  const lastIndex = message.parts.length - 1;

  return (
    <div className="w-full text-zinc-200">
      {isEmptyStreaming ? (
        <TypingDots />
      ) : (
        <>
          {message.parts.map((part, i) =>
            part.type === "steps" ? (
              <ToolActivity
                key={i}
                steps={part.steps}
                streaming={message.streaming && i === lastIndex}
              />
            ) : (
              <Markdown key={i}>{part.text}</Markdown>
            ),
          )}
          {message.streaming && <StreamingCursor />}
        </>
      )}

      {message.error && (
        <p className="mt-1 text-xs text-destructive">{message.error}</p>
      )}
    </div>
  );
}

/** Blinking caret shown at the tail of a reply while it streams. */
function StreamingCursor() {
  return (
    <span className="ml-0.5 inline-block h-4 w-1.5 translate-y-0.5 animate-pulse rounded-sm bg-zinc-400 align-baseline" />
  );
}

/** Three bouncing dots shown before the first token arrives. */
function TypingDots() {
  return (
    <span className="flex items-center gap-1 py-2">
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="size-2 animate-bounce rounded-full bg-zinc-500"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </span>
  );
}
