import { SquarePen } from "lucide-react";
import { useEffect, useState } from "react";

import { Cheo, type CheoMood } from "@/components/chat/cheo";
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
  /** A reply is on its way; Cheo cheers (^^) when it lands. */
  busy?: boolean;
  /** How Cheo looks meanwhile: attentive, working on a tool, or idle. */
  mood?: CheoMood;
}

/** How long Cheo stays ^^ after a reply lands. */
const HAPPY_MS = 1400;

/** Top bar: Cheo as the avatar, the name and subtitle, and a new-chat
 *  button. */
export function ChatHeader({
  title,
  subtitle,
  onNewChat,
  identityLabel,
  alwaysShowNewChat,
  busy = false,
  mood = "idle",
}: ChatHeaderProps) {
  // Happy on the busy → idle edge. Adjusted during render rather than in an
  // effect (react-hooks/set-state-in-effect); the effect only times it out.
  const [prevBusy, setPrevBusy] = useState(busy);
  const [happy, setHappy] = useState(false);
  if (busy !== prevBusy) {
    setPrevBusy(busy);
    setHappy(!busy);
  }
  useEffect(() => {
    if (!happy) return;
    const timer = setTimeout(() => setHappy(false), HAPPY_MS);
    return () => clearTimeout(timer);
  }, [happy]);

  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-border px-4">
      <div className="flex min-w-0 items-center gap-3">
        <Cheo
          mood={happy ? "happy" : mood}
          className="h-9 w-11 shrink-0"
        />
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
