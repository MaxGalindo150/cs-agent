import { z } from "zod";
import { Money, PaymentStatus, PaymentMethod, IsoDate } from "./common.js";

export const PaymentAppliedTo = z.object({
  installmentId: z.string().nullable(),
  orderId: z.string().nullable(),
  orderMerchantName: z.string().nullable(),
  installmentNumber: z.number().int().nullable(),
});

export const Payment = z.object({
  id: z.string(),
  userId: z.string(),
  externalReference: z.string(),
  amount: Money,
  currency: z.string().default("MXN"),
  method: PaymentMethod,
  status: PaymentStatus,
  appliedTo: PaymentAppliedTo,
  validatedAt: IsoDate.nullable(),
  /** Interno: la cuota correcta cuando hay mismatch (payment_wrong_order). */
  correctInstallmentId: z.string().nullable(),
  createdAt: IsoDate,
});

export type Payment = z.infer<typeof Payment>;
export type PaymentAppliedTo = z.infer<typeof PaymentAppliedTo>;
