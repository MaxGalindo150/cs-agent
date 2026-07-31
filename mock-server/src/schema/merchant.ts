import { z } from "zod";
import { MerchantStatus, IsoDate } from "./common.js";

export const Merchant = z.object({
  id: z.string(),
  name: z.string(),
  category: z.string(),
  logoUrl: z.string().nullable(),
  status: MerchantStatus,
  createdAt: IsoDate,
});

export type Merchant = z.infer<typeof Merchant>;
