"use client";

import { Check } from "lucide-react";

import type { ChoiceOption } from "@/lib/chat/types";
import { cn } from "@/lib/utils";

interface ChoicePromptProps {
  prompt: string;
  options: ChoiceOption[];
  /** Set once a specific option was clicked — renders that option as settled
   *  instead of live buttons. Undefined while still pending or while settled
   *  without a specific option (see `resolved`). */
  resolvedOptionId?: string;
  /** Set once the question is settled at all — by a click (alongside
   *  `resolvedOptionId`) or by the customer typing free text instead (on its
   *  own, no option to highlight). Renders a generic "answered" row instead
   *  of live buttons either way. */
  resolved?: boolean;
  /** Called with the picked option's id. Absent (or `disabled`) while a turn
   *  is already streaming, so a double-click can't submit twice. */
  onSelect?: (optionId: string) => void;
  disabled?: boolean;
}

/**
 * `present_choice`'s clickable options — the sibling of `ToolActivity` for a
 * paused turn instead of a running one.
 *
 * Three states, same idea as `ToolActivity`'s expanded/collapsed: **pending**
 * shows every option as a live button; **resolved with an option**
 * (`resolvedOptionId` set — live right after a click, or replayed from
 * `chat_messages.meta` on reload) shows only the picked one, settled, with
 * the others gone; **resolved without one** (`resolved` set but no
 * `resolvedOptionId` — the customer typed instead of clicking) shows a
 * generic settled row with nothing highlighted. This is what keeps a stale
 * tab or an old scroll position from re-submitting a choice that was already
 * answered elsewhere, by button or by text.
 */
export function ChoicePrompt({
  prompt,
  options,
  resolvedOptionId,
  resolved,
  onSelect,
  disabled = false,
}: ChoicePromptProps) {
  const picked = options.find((o) => o.id === resolvedOptionId);
  const settled = picked !== undefined || resolved === true;

  return (
    <div className="mb-3 max-w-sm">
      <p className="mb-2 text-[15px] leading-7 text-zinc-200">{prompt}</p>
      {settled ? (
        <div className="flex items-center gap-2 rounded-xl border border-zinc-800 bg-zinc-900/40 px-3.5 py-2 text-sm text-zinc-300">
          <Check className="size-3.5 shrink-0 text-zinc-500" />
          {picked ? picked.label : "Respondido"}
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          {options.map((option) => (
            <button
              key={option.id}
              type="button"
              disabled={disabled}
              onClick={() => onSelect?.(option.id)}
              className={cn(
                "rounded-xl border border-zinc-700 px-3.5 py-2 text-sm text-zinc-200 transition-colors duration-150",
                "hover:bg-zinc-800 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-600",
                "disabled:cursor-not-allowed disabled:opacity-50",
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
