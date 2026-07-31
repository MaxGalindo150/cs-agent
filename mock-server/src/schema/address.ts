import { z } from "zod";
import { AddressType, IsoDate } from "./common.js";

export const Address = z.object({
  id: z.string(),
  userId: z.string(),
  type: AddressType,
  line1: z.string(),
  line2: z.string().nullable(),
  city: z.string(),
  state: z.string(),
  zip: z.string(),
  country: z.string(),
  isDefault: z.boolean(),
  createdAt: IsoDate,
});

export type Address = z.infer<typeof Address>;
