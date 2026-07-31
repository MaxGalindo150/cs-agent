import { z } from "zod";
import { PaymentMethodType, CardBrand, IsoDate } from "./common.js";

export const PaymentMethod = z.object({
  id: z.string(),
  userId: z.string(),
  type: PaymentMethodType,
  brand: CardBrand.nullable(),
  bankName: z.string().nullable(),
  last4: z.string(),
  expiryMonth: z.number().int().min(1).max(12).nullable(),
  expiryYear: z.number().int().nullable(),
  isDefault: z.boolean(),
  createdAt: IsoDate,
});

export type PaymentMethod = z.infer<typeof PaymentMethod>;
