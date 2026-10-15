import { CheoOrb, type CheoMood as OrbMood } from "@cashea/cheo/react";

/** idle: resting · attentive: waiting on a reply, listening · working: a tool
 *  is running, thinking with the ring pulsing · happy: ^^ */
export type CheoMood = "idle" | "attentive" | "working" | "happy";

interface CheoProps {
  mood?: CheoMood;
  /** Diameter in px. 16, 24 and 56 keep the orb's tuned eye geometry. */
  size?: number;
  className?: string;
}

const ORB_MOOD: Record<CheoMood, OrbMood> = {
  idle: "idle",
  attentive: "listening",
  working: "thinking",
  happy: "happy",
};

/** Cheo, the Cashea orb (the @cashea/cheo package). Decorative: every
 *  placement already says who's talking in text. */
export function Cheo({ mood = "idle", size = 24, className }: CheoProps) {
  return (
    <CheoOrb
      size={size}
      mood={ORB_MOOD[mood]}
      live={mood === "working"}
      className={className}
    />
  );
}
