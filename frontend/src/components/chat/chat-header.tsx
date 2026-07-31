import { SquarePen } from "lucide-react";

import { Button } from "@/components/ui/button";

interface ChatHeaderProps {
  /** Start a new conversation. When omitted, the button is hidden. */
  onNewChat?: () => void;
}

/** Slim top bar: title with a live status dot, and a new-chat button. */
export function ChatHeader({ onNewChat }: ChatHeaderProps) {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-zinc-800 px-4">
      <div className="flex items-center gap-2.5">
        <span className="relative flex size-2" aria-hidden>
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-500 opacity-60" />
          <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
        </span>
        <span className="text-sm font-medium tracking-tight text-zinc-100">
          Customer Support
        </span>
      </div>

      {onNewChat && (
        <Button
          variant="ghost"
          size="icon-sm"
          className="text-zinc-400 transition-colors duration-150 hover:text-zinc-100 sm:hidden"
          onClick={onNewChat}
          aria-label="New conversation"
          title="New conversation"
        >
          <SquarePen />
        </Button>
      )}
    </header>
  );
}
