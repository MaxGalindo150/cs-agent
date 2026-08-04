"use client";

import { Check } from "lucide-react";

import type { ChoiceOption } from "@/lib/chat/types";
import { cn } from "@/lib/utils";

interface ChoicePromptProps {
  prompt: string;
  options: ChoiceOption[];
  /** Set once the customer has answered (by button or by typing instead) —
   *  renders the picked option as settled instead of live buttons. Undefined
   *  while still pending. */
  resolvedOptionId?: string;
  /** Called with the picked option's id. Absent (or `disabled`) while a turn
   *  is already streaming, so a double-click can't submit twice. */
  onSelect?: (optionId: string) => void;
  disabled?: boolean;
}

/**
 * `present_choice`'s clickable options — the sibling of `ToolActivity` for a
 * paused turn instead of a running one.
 *
 * Two states, same idea as `ToolActivity`'s expanded/collapsed: **pending**
 * shows every option as a live button; **resolved** (`resolvedOptionId` set —
 * live right after a click, or replayed from `chat_messages.meta` on reload)
 * shows only the picked one, settled, with the others gone. This is what
 * keeps a stale tab or an old scroll position from re-submitting a choice
 * that was already answered elsewhere.
 */
export function ChoicePrompt({
  prompt,
  options,
  resolvedOptionId,
  onSelect,
  disabled = false,
}: ChoicePromptProps) {
  const resolved = options.find((o) => o.id === resolvedOptionId);

  return (
    <div className="mb-3 max-w-sm">
      <p className="mb-2 text-[15px] leading-7 text-zinc-200">{prompt}</p>
      {resolved ? (
        <div className="flex items-center gap-2 rounded-xl border border-zinc-800 bg-zinc-900/40 px-3.5 py-2 text-sm text-zinc-300">
          <Check className="size-3.5 shrink-0 text-zinc-500" />
          {resolved.label}
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
