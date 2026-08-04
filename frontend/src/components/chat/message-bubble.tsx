import { ChoicePrompt } from "@/components/chat/choice-prompt";
import { Markdown } from "@/components/chat/markdown";
import { ToolActivity } from "@/components/chat/tool-activity";
import type { Message } from "@/lib/chat/types";

interface MessageBubbleProps {
  message: Message;
  /** Resolve a pending `present_choice` by option id. Omitted (or ignored via
   *  `disableChoices`) while a turn is already streaming. */
  onChoice?: (optionId: string) => void;
  /** True while any turn is in flight — disables live choice buttons so a
   *  double-click can't submit twice. */
  disableChoices?: boolean;
}

/** A single chat turn. User messages are right-aligned bubbles; assistant
 *  messages flow full-width (no bubble) like ChatGPT / Claude.ai.
 *
 *  An assistant turn renders its `parts` in the order they happened — text,
 *  then a tool's activity, then more text — rather than hoisting every tool
 *  call above the whole reply. That is what lets "I'll escalate this" ->
 *  [escalating…] -> "Done" read as one sequence instead of the agent
 *  seemingly talking to itself. */
export function MessageBubble({ message, onChoice, disableChoices }: MessageBubbleProps) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex w-full justify-end">
        <div className="flex max-w-[75%] flex-col items-end gap-2">
          {message.parts.map((part, i) =>
            part.type === "image" ? (
              // blob: object URL, only ever rendered for the turn just sent
              // (never persisted/reloaded — see AttachedImage) — not a
              // static/remote asset next/image is meant to optimize.
              // eslint-disable-next-line @next/next/no-img-element
              <img
                key={i}
                src={part.previewUrl}
                alt="Attached"
                className="max-h-64 rounded-2xl object-cover shadow-md shadow-black/20 ring-1 ring-white/10"
              />
            ) : part.type === "text" ? (
              <div
                key={i}
                className="rounded-2xl bg-zinc-800/60 px-4 py-2.5 text-[15px] leading-7 break-words whitespace-pre-wrap text-zinc-100 shadow-md shadow-black/20 ring-1 ring-white/10 backdrop-blur-sm"
              >
                {part.text}
              </div>
            ) : null,
          )}
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
          {message.parts.map((part, i) => {
            // `image` parts only ever occur on a user turn (see AttachedImage) —
            // an assistant turn never attaches one, so there's nothing to render.
            if (part.type === "image") return null;
            if (part.type === "steps") {
              return (
                <ToolActivity
                  key={i}
                  steps={part.steps}
                  streaming={message.streaming && i === lastIndex}
                />
              );
            }
            if (part.type === "choice") {
              return (
                <ChoicePrompt
                  key={i}
                  prompt={part.prompt}
                  options={part.options}
                  resolvedOptionId={part.resolvedOptionId}
                  resolved={part.resolved}
                  onSelect={onChoice}
                  disabled={disableChoices}
                />
              );
            }
            return <Markdown key={i}>{part.text}</Markdown>;
          })}
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
