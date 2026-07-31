import { z } from "zod";
import { PointsTxnType, PointsTxnSource, IsoDate } from "./common.js";

export const PointsTransaction = z.object({
  id: z.string(),
  userId: z.string(),
  type: PointsTxnType,
  amount: z.number().int(),     // positivo = ganado, negativo = canjeado
  source: PointsTxnSource,
  referenceId: z.string().nullable(),
  description: z.string(),
  createdAt: IsoDate,
});

export type PointsTransaction = z.infer<typeof PointsTransaction>;
