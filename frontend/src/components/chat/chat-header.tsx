import { SquarePen } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ChatHeaderProps {
  /** Start a new conversation. When omitted, the button is hidden. */
  onNewChat?: () => void;
  /** Who the widget thinks it's talking to, e.g. "Alice Johnson" or "Guest"
   *  (see lib/identity/). Shown as a small subtitle for verifying the
   *  identity harness without opening devtools. */
  identityLabel?: string;
  /**
   * Show the inline new-chat button regardless of viewport width. Normally
   * it only appears below the `sm` breakpoint (the sidebar's own button
   * covers wider screens) — but that breakpoint checks the *browser*
   * viewport, not this header's container, so it can't auto-show correctly
   * inside the floating widget's narrow panel. Pass true wherever there's no
   * sidebar to fall back on.
   */
  alwaysShowNewChat?: boolean;
}

/** Slim top bar: title with a live status dot, and a new-chat button. */
export function ChatHeader({
  onNewChat,
  identityLabel,
  alwaysShowNewChat,
}: ChatHeaderProps) {
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
        {identityLabel && (
          <span className="rounded-full bg-zinc-900 px-2 py-0.5 text-xs text-zinc-400">
            as {identityLabel}
          </span>
        )}
      </div>

      {onNewChat && (
        <Button
          variant="ghost"
          size="icon-sm"
          className={cn(
            "text-zinc-400 transition-colors duration-150 hover:text-zinc-100",
            !alwaysShowNewChat && "sm:hidden",
          )}
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
