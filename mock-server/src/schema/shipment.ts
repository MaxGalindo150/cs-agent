import { z } from "zod";
import { Carrier, ShipmentStatus, IsoDate } from "./common.js";

export const ShipmentEvent = z.object({
  status: z.string(),
  description: z.string(),
  location: z.string(),
  timestamp: IsoDate,
});

export const ShipmentAddress = z.object({
  line1: z.string(),
  city: z.string(),
  state: z.string(),
  zip: z.string(),
  country: z.string(),
});

export const Shipment = z.object({
  id: z.string(),
  orderId: z.string(),
  userId: z.string(),
  carrier: Carrier,
  trackingNumber: z.string(),
  status: ShipmentStatus,
  address: ShipmentAddress,
  estimatedDelivery: IsoDate.nullable(),
  shippedAt: IsoDate.nullable(),
  deliveredAt: IsoDate.nullable(),
  events: z.array(ShipmentEvent),
  createdAt: IsoDate,
  updatedAt: IsoDate,
});

export type Shipment = z.infer<typeof Shipment>;
export type ShipmentEvent = z.infer<typeof ShipmentEvent>;
export type ShipmentAddress = z.infer<typeof ShipmentAddress>;
