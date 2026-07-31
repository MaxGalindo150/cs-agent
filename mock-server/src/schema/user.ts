import { z } from "zod";
import { UserStatus, KycStatus, ScenarioTag, IsoDate } from "./common.js";

export const User = z.object({
  id: z.string(),
  email: z.string().email(),
  phone: z.string(),
  firstName: z.string(),
  lastName: z.string(),
  dob: IsoDate,
  status: UserStatus,
  kycStatus: KycStatus,
  avatarUrl: z.string().nullable(),
  scenarioTags: z.array(ScenarioTag).default([]),
  createdAt: IsoDate,
});

export type User = z.infer<typeof User>;
