import { SquarePen } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ChatHeaderProps {
  title: string;
  /** A short line under the title, e.g. "Soporte Cashea". */
  subtitle?: string;
  /** Start a new conversation. When omitted, the button is hidden. */
  onNewChat?: () => void;
  /** Who the widget thinks it's talking to, e.g. "Alice Johnson" or "Invitado"
   *  (see lib/identity/). Shown as a small chip for verifying the identity
   *  harness without opening devtools; omit it where the user already knows
   *  who they are (the embed). */
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

/** Top bar: the assistant's avatar with a live dot, its name and subtitle,
 *  and a new-chat button. */
export function ChatHeader({
  title,
  subtitle,
  onNewChat,
  identityLabel,
  alwaysShowNewChat,
}: ChatHeaderProps) {
  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-border px-4">
      <div className="flex min-w-0 items-center gap-3">
        <span className="relative shrink-0" aria-hidden>
          <span className="flex size-9 items-center justify-center rounded-full bg-brand text-sm font-bold text-brand-foreground">
            {title.charAt(0)}
          </span>
          <span className="absolute -right-0.5 -bottom-0.5 size-3 rounded-full border-2 border-background bg-emerald-500" />
        </span>
        <div className="flex min-w-0 flex-col leading-tight">
          <span className="truncate text-sm font-semibold tracking-tight text-foreground">
            {title}
          </span>
          {subtitle && (
            <span className="truncate text-xs text-muted-foreground">{subtitle}</span>
          )}
        </div>
        {identityLabel && (
          <span className="truncate rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
            como {identityLabel}
          </span>
        )}
      </div>

      {onNewChat && (
        <Button
          variant="ghost"
          size="icon-sm"
          className={cn(
            "text-muted-foreground transition-colors duration-150 hover:text-foreground",
            !alwaysShowNewChat && "sm:hidden",
          )}
          onClick={onNewChat}
          aria-label="Nueva conversación"
          title="Nueva conversación"
        >
          <SquarePen />
        </Button>
      )}
    </header>
  );
}
