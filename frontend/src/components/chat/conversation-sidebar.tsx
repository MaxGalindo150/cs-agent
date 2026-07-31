"use client";

import { SquarePen, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { ConversationSummary } from "@/lib/chat/types";
import { cn } from "@/lib/utils";

interface ConversationSidebarProps {
  conversations: ConversationSummary[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNewChat: () => void;
  onDelete: (id: string) => void;
}

/** Compact relative timestamp (e.g. "now", "5m", "3h", "2d"). Runs client-side
 *  only (the list is fetched in an effect), so no SSR/hydration mismatch. */
function formatTime(iso: string): string {
  const then = new Date(iso).getTime();
  const diffSec = Math.max(0, (Date.now() - then) / 1000);
  if (diffSec < 60) return "now";
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h`;
  if (diffSec < 604800) return `${Math.floor(diffSec / 86400)}d`;
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

/** Left rail listing past conversations. Hidden on small screens. */
export function ConversationSidebar({
  conversations,
  activeId,
  onSelect,
  onNewChat,
  onDelete,
}: ConversationSidebarProps) {
  return (
    <aside className="hidden w-72 shrink-0 flex-col border-r border-zinc-800 bg-zinc-950 sm:flex">
      <div className="flex h-14 shrink-0 items-center justify-between border-b border-zinc-800 px-3">
        <span className="text-sm font-medium tracking-tight text-zinc-100">
          Conversations
        </span>
        <Button
          variant="ghost"
          size="icon-sm"
          className="text-zinc-400 transition-colors duration-150 hover:text-zinc-100"
          onClick={onNewChat}
          aria-label="New conversation"
          title="New conversation"
        >
          <SquarePen />
        </Button>
      </div>

      <nav className="flex-1 overflow-y-auto p-2">
        {conversations.length === 0 ? (
          <p className="px-2 py-4 text-xs text-zinc-500">No conversations yet.</p>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {conversations.map((c) => {
              const active = activeId === c.id;
              return (
                <li
                  key={c.id}
                  className={cn(
                    "group flex items-center gap-1 rounded-lg pr-1 transition-colors duration-150",
                    active ? "bg-zinc-900" : "hover:bg-zinc-900",
                  )}
                >
                  <button
                    type="button"
                    onClick={() => onSelect(c.id)}
                    className="min-w-0 flex-1 rounded-lg px-2.5 py-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-700"
                  >
                    <div className="flex items-baseline justify-between gap-2">
                      <p
                        className={cn(
                          "truncate text-sm",
                          active
                            ? "font-medium text-zinc-100"
                            : "text-zinc-300",
                        )}
                      >
                        {c.title || "New conversation"}
                      </p>
                      <span className="shrink-0 text-xs text-zinc-500">
                        {formatTime(c.last_activity_at)}
                      </span>
                    </div>
                  </button>
                  <Button
                    variant="ghost"
                    size="icon-xs"
                    onClick={() => onDelete(c.id)}
                    aria-label="Delete conversation"
                    title="Delete conversation"
                    className="shrink-0 text-zinc-500 opacity-0 transition-opacity duration-150 hover:text-zinc-100 group-hover:opacity-100 focus-visible:opacity-100"
                  >
                    <Trash2 />
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </nav>
    </aside>
  );
}
