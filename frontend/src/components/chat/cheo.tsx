import { useId } from "react";

import { cn } from "@/lib/utils";

/** idle: floats and blinks · attentive: waiting on a reply, eyes up ·
 *  working: a tool is running, little clouds orbit it · happy: ^^ */
export type CheoMood = "idle" | "attentive" | "working" | "happy";

interface CheoProps {
  mood?: CheoMood;
  className?: string;
}

// Puffy all the way round (no flat base) — [cx, cy, r]. Same shape as the
// launcher in public/widget.js; keep the two in sync.
const LOBES: [number, number, number][] = [
  [40, 46, 20],
  [64, 36, 25],
  [88, 48, 18],
  [34, 61, 15],
  [52, 66, 17],
  [74, 66, 18],
  [93, 61, 14],
  [64, 54, 24],
];

/** Cheo, the Cashea cloud. Animations live in globals.css (.cheo-*) and
 *  stop under prefers-reduced-motion. */
export function Cheo({ mood = "idle", className }: CheoProps) {
  // Per-instance ids: several Cheos can be on screen at once.
  const id = useId().replace(/:/g, "");
  const fill = `cheo-fill-${id}`;
  const soft = `cheo-soft-${id}`;

  return (
    <svg
      className={cn("cheo", `cheo-${mood}`, className)}
      viewBox="8 4 112 96"
      // Decorative: every placement already says who's talking in text.
      aria-hidden
    >
      <defs>
        <linearGradient id={fill} gradientUnits="userSpaceOnUse" x1="0" y1="12" x2="0" y2="84">
          <stop offset="0" stopColor="#fffc8a" />
          <stop offset="0.55" stopColor="#fdfa3d" />
          <stop offset="1" stopColor="#f6ec1f" />
        </linearGradient>
        <filter id={soft} x="-50%" y="-200%" width="200%" height="500%">
          <feGaussianBlur stdDeviation="2.4" />
        </filter>
      </defs>
      <ellipse
        className="cheo-ground"
        cx="64"
        cy="94"
        rx="30"
        ry="3.6"
        filter={`url(#${soft})`}
      />
      {/* Two trails of little clouds that orbit the middle while working.
          Each trail leads with its biggest puff (clockwise spin). */}
      <g className="cheo-orbit">
        <circle cx="64" cy="2" r="9" />
        <circle cx="39.6" cy="8.1" r="7" />
        <circle cx="23" cy="22" r="5" />
        <circle cx="64" cy="106" r="9" />
        <circle cx="88.4" cy="99.9" r="7" />
        <circle cx="105" cy="86" r="5" />
      </g>
      <g className="cheo-body">
        {LOBES.map(([cx, cy, r]) => (
          <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r={r} fill={`url(#${fill})`} />
        ))}
        <g className="cheo-eyes">
          {mood === "happy" ? (
            <>
              <path className="cheo-squint" d="M50 58 q6 -8 12 0" />
              <path className="cheo-squint" d="M66 58 q6 -8 12 0" />
            </>
          ) : (
            <>
              <ellipse className="cheo-eye" cx="56" cy="56" rx="4.6" ry="7" />
              <ellipse className="cheo-eye" cx="72" cy="56" rx="4.6" ry="7" />
            </>
          )}
        </g>
      </g>
    </svg>
  );
}
