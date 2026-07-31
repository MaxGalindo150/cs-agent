import { z } from "zod";
import { Money, OrderStatus, OrderPlan, IsoDate } from "./common.js";

export const OrderItem = z.object({
  sku: z.string(),
  name: z.string(),
  qty: z.number().int().positive(),
  unitPrice: Money,
});

export const Financing = z.object({
  principal: Money,
  interest: Money,
  fees: Money,
  apr: z.number(),
  termMonths: z.number().int(),
});

export const Order = z.object({
  id: z.string(),
  userId: z.string(),
  merchantId: z.string(),
  merchantName: z.string(),
  items: z.array(OrderItem),
  subtotal: Money,
  shipping: Money,
  tax: Money,
  totalAmount: Money,
  plan: OrderPlan,
  status: OrderStatus,
  financing: Financing,
  installmentCount: z.number().int(),
  refundRequested: z.boolean().default(false),
  refundReason: z.string().nullable(),
  createdAt: IsoDate,
  updatedAt: IsoDate,
});

export type Order = z.infer<typeof Order>;
export type OrderItem = z.infer<typeof OrderItem>;
export type Financing = z.infer<typeof Financing>;
