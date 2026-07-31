import { z } from "zod";
import { Money, InstallmentStatus, IsoDate } from "./common.js";

export const Installment = z.object({
  id: z.string(),
  orderId: z.string(),
  userId: z.string(),
  number: z.number().int().positive(),
  amountDue: Money,
  principal: Money,
  interest: Money,
  fees: Money,
  dueDate: IsoDate,
  paidDate: IsoDate.nullable(),
  status: InstallmentStatus,
  paymentMethodId: z.string().nullable(),
  externalReference: z.string().nullable(),  // referencia bancaria externa (para payment_not_reflected)
});

export type Installment = z.infer<typeof Installment>;
