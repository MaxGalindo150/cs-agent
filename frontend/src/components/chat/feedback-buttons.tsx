import { ThumbsDown, ThumbsUp } from "lucide-react";

import type { Feedback } from "@/lib/chat/types";
import { cn } from "@/lib/utils";

interface FeedbackButtonsProps {
  value?: Feedback;
  /** Pick a rating, or null to withdraw it (tapping the chosen one again). */
  onChange: (feedback: Feedback | null) => void;
}

/** Thumbs up/down under a finished reply. Quiet until used; the chosen one
 *  stays filled, and a short thanks appears once rated. */
export function FeedbackButtons({ value, onChange }: FeedbackButtonsProps) {
  return (
    <div className="mt-2 flex items-center gap-1 text-muted-foreground">
      <Thumb
        label="Me sirvió"
        active={value === "up"}
        onClick={() => onChange(value === "up" ? null : "up")}
      >
        <ThumbsUp className={cn("size-3.5", value === "up" && "fill-current")} />
      </Thumb>
      <Thumb
        label="No me sirvió"
        active={value === "down"}
        onClick={() => onChange(value === "down" ? null : "down")}
      >
        <ThumbsDown className={cn("size-3.5", value === "down" && "fill-current")} />
      </Thumb>
      {value && (
        <span className="ml-1 text-xs" role="status">
          Gracias por tu opinión
        </span>
      )}
    </div>
  );
}

function Thumb({
  label,
  active,
  onClick,
  children,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      aria-pressed={active}
      title={label}
      className={cn(
        "flex size-7 items-center justify-center rounded-md transition-colors duration-150 hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        active && "text-foreground",
      )}
    >
      {children}
    </button>
  );
}
