import { z } from "zod";
import { Money, TxnType, TxnDirection, IsoDate } from "./common.js";

export const Transaction = z.object({
  id: z.string(),
  userId: z.string(),
  type: TxnType,
  direction: TxnDirection,
  amount: Money,
  description: z.string(),
  referenceType: z.string().nullable(),
  referenceId: z.string().nullable(),
  createdAt: IsoDate,
});

export type Transaction = z.infer<typeof Transaction>;
