import { z } from "zod";
import { Money, CreditAccountStatus, IsoDate } from "./common.js";

export const CreditAccount = z.object({
  id: z.string(),
  userId: z.string(),
  creditLimit: Money,
  outstandingBalance: Money,
  availableCredit: Money,        // creditLimit - outstandingBalance
  interestRate: z.number(),       // APR %
  utilizationPct: z.number(),     // outstanding / limit * 100
  status: CreditAccountStatus,
  createdAt: IsoDate,
  updatedAt: IsoDate,
});

export type CreditAccount = z.infer<typeof CreditAccount>;
