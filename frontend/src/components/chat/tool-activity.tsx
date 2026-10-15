"use client";

import { Check, ChevronDown, Search, Wrench } from "lucide-react";
import { useState } from "react";

import { Cheo } from "@/components/chat/cheo";
import type { ActivityStep } from "@/lib/chat/types";
import { cn } from "@/lib/utils";

interface ToolActivityProps {
  steps: ActivityStep[];
  /** True while the turn is still running. */
  streaming?: boolean;
}

/**
 * What the agent did before answering, as a quiet timeline above the reply.
 *
 * Two states, and the transition between them is the whole point:
 *
 * - **While the turn runs** it is open, so you can watch each step land. The
 *   running step pulses; finished ones settle.
 * - **Once the reply is in** it collapses to a one-line summary, because the
 *   answer is what matters afterwards. Click to reopen.
 *
 * Expansion is `userChoice ?? streaming` rather than state synced in an effect:
 * React 19's `react-hooks/set-state-in-effect` rule forbids that, and deriving
 * it means the collapse happens in the same render as the last token.
 */
export function ToolActivity({ steps, streaming = false }: ToolActivityProps) {
  const [userChoice, setUserChoice] = useState<boolean | null>(null);
  const expanded = userChoice ?? streaming;

  if (steps.length === 0) return null;

  return (
    <div className="mb-3 text-sm">
      <button
        type="button"
        onClick={() => setUserChoice(!expanded)}
        aria-expanded={expanded}
        className="group flex items-center gap-1 rounded text-muted-foreground transition-colors duration-150 hover:text-foreground/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {/* Streaming here means no reply text yet: Cheo is still at work. */}
        {streaming && <Cheo mood="working" size={24} className="mr-1.5" />}
        <span className={cn(streaming && "text-shimmer")}>
          {summarize(steps, streaming)}
        </span>
        <ChevronDown
          className={cn(
            "size-3.5 transition-transform duration-200",
            expanded && "rotate-180",
          )}
        />
      </button>

      {expanded && (
        // border-l draws the connector; each icon sits on top of it with the
        // page background, which is what makes the line look segmented.
        <ol className="mt-2 ml-[9px] border-l border-border">
          {steps.map((step) => (
            <Row
              key={step.id}
              icon={step.kind === "memory" ? Search : Wrench}
              label={step.label}
              running={step.status === "running"}
            />
          ))}
          {!streaming && <Row icon={Check} label="Listo" />}
        </ol>
      )}
    </div>
  );
}

function Row({
  icon: Icon,
  label,
  running = false,
}: {
  icon: typeof Search;
  label: string;
  running?: boolean;
}) {
  return (
    <li className="relative flex items-center gap-2.5 py-1 pl-5">
      <span className="absolute -left-[9px] flex size-[18px] items-center justify-center rounded-full bg-background text-muted-foreground/70">
        <Icon className="size-3.5" />
      </span>
      {/* text-shimmer paints the text with a moving gradient, so it sets its
          own color — the zinc-500 below only applies once it settles. */}
      <span className={running ? "text-shimmer" : "text-muted-foreground"}>{label}</span>
    </li>
  );
}

/** The collapsed one-liner: what was done, in the tools' own words —
 *  "Consulté tus órdenes · Revisé la orden" — never a count of "tools". */
function summarize(steps: ActivityStep[], streaming: boolean): string {
  if (streaming) {
    // Name what is happening right now, falling back to the last thing done.
    const running = steps.find((s) => s.status === "running");
    return running?.label ?? steps[steps.length - 1]?.label ?? "Trabajando";
  }

  const done = [...new Set(steps.filter((s) => s.kind === "tool").map((s) => s.label))];
  if (done.length === 0) return "Revisé lo que hablamos";
  if (done.length <= 2) return done.join(" · ");
  return `${done[0]} y ${done.length - 1} más`;
}
