import { Cheo } from "@/components/chat/cheo";
import { ChoicePrompt } from "@/components/chat/choice-prompt";
import { FeedbackButtons } from "@/components/chat/feedback-buttons";
import { Markdown } from "@/components/chat/markdown";
import { OrderCards } from "@/components/chat/order-cards";
import { SuggestionChips } from "@/components/chat/suggestion-chips";
import { ToolActivity } from "@/components/chat/tool-activity";
import type { Feedback, Message } from "@/lib/chat/types";

interface MessageBubbleProps {
  message: Message;
  /** Resolve a pending `present_choice` by option id. Omitted (or ignored via
   *  `disableChoices`) while a turn is already streaming. */
  onChoice?: (optionId: string) => void;
  /** True while any turn is in flight — disables live choice buttons so a
   *  double-click can't submit twice. */
  disableChoices?: boolean;
  /** True for the newest message: only its follow-up suggestions are live. */
  isLatest?: boolean;
  /** Send a follow-up suggestion as the next message. */
  onSuggestion?: (text: string) => void;
  /** Open an order card in the host app. */
  onOpenOrder?: (orderUuid: string) => void;
  /** Rate this reply; the thumbs are hidden without it. */
  onRate?: (messageId: string, feedback: Feedback | null) => void;
}

/** A single chat turn. User messages are right-aligned bubbles; assistant
 *  messages flow full-width (no bubble) like ChatGPT / Claude.ai.
 *
 *  An assistant turn renders its `parts` in the order they happened — text,
 *  then a tool's activity, then more text — rather than hoisting every tool
 *  call above the whole reply. That is what lets "I'll escalate this" ->
 *  [escalating…] -> "Done" read as one sequence instead of the agent
 *  seemingly talking to itself. */
export function MessageBubble({
  message,
  onChoice,
  disableChoices,
  isLatest = false,
  onSuggestion,
  onOpenOrder,
  onRate,
}: MessageBubbleProps) {
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
                alt="Imagen adjunta"
                className="max-h-64 rounded-2xl object-cover shadow-md shadow-black/20 ring-1 ring-border"
              />
            ) : part.type === "text" ? (
              <div
                key={i}
                className="rounded-2xl bg-user-bubble px-4 py-2 text-[length:var(--chat-text)] leading-[var(--chat-leading)] break-words whitespace-pre-wrap text-user-bubble-foreground shadow-md shadow-black/5 ring-1 ring-border"
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
    <div className="w-full text-foreground">
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
            if (part.type === "orders") {
              return <OrderCards key={i} orders={part.orders} onOpen={onOpenOrder} />;
            }
            if (part.type === "suggestions") {
              // Stale once the conversation moved on, and pointless mid-stream.
              if (!isLatest || message.streaming || !onSuggestion) return null;
              return (
                <SuggestionChips
                  key={i}
                  options={part.options}
                  onSelect={onSuggestion}
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

      {onRate && message.serverId && !message.streaming && !message.error && (
        <FeedbackButtons
          value={message.feedback}
          onChange={(feedback) => onRate(message.id, feedback)}
        />
      )}
    </div>
  );
}

/** Blinking caret shown at the tail of a reply while it streams. */
function StreamingCursor() {
  return (
    <span className="ml-0.5 inline-block h-4 w-1.5 translate-y-0.5 animate-pulse rounded-sm bg-muted-foreground align-baseline" />
  );
}

/** Cheo waiting, eyes up, before the first token arrives. */
function TypingDots() {
  return (
    <span className="flex py-1" role="status">
      <Cheo mood="attentive" className="h-8 w-10" />
      <span className="sr-only">Cheo está pensando</span>
    </span>
  );
}
