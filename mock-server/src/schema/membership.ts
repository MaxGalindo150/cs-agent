import { z } from "zod";
import { Tier, Money, IsoDate } from "./common.js";

export const TierProgress = z.object({
  current: z.number().int(),
  needed: z.number().int(),
  pct: z.number(),
});

export const Membership = z.object({
  id: z.string(),
  userId: z.string(),
  pointsBalance: z.number().int(),
  tier: Tier,
  tierProgress: TierProgress,
  totalSpent: Money,
  joinedAt: IsoDate,
  updatedAt: IsoDate,
});

export type Membership = z.infer<typeof Membership>;
export type TierProgress = z.infer<typeof TierProgress>;
