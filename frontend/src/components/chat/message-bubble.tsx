import { Markdown } from "@/components/chat/markdown";
import { ToolActivity } from "@/components/chat/tool-activity";
import type { Message } from "@/lib/chat/types";

interface MessageBubbleProps {
  message: Message;
}

/** A single chat turn. User messages are right-aligned bubbles; assistant
 *  messages flow full-width (no bubble) like ChatGPT / Claude.ai. */
export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const isEmptyStreaming = message.streaming && message.content.length === 0;

  if (isUser) {
    return (
      <div className="flex w-full justify-end">
        <div className="max-w-[75%] rounded-2xl bg-zinc-100 px-4 py-2.5 text-[15px] leading-7 break-words whitespace-pre-wrap text-zinc-900">
          {message.content}
        </div>
      </div>
    );
  }

  const hasSteps = (message.steps?.length ?? 0) > 0;

  return (
    <div className="w-full text-zinc-200">
      {hasSteps && (
        <ToolActivity steps={message.steps ?? []} streaming={message.streaming} />
      )}

      {/* Once activity is on screen there is something to look at, so the
          typing dots would just be noise stacked under it. */}
      {isEmptyStreaming ? (
        hasSteps ? null : (
          <TypingDots />
        )
      ) : (
        <>
          <Markdown>{message.content}</Markdown>
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
