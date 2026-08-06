import { beforeEach, describe, expect, test } from "bun:test";
import { Hono } from "hono";
import { getDB } from "../db.js";
import { runSeed } from "../seed/seed.js";
import { orderRoutes } from "./orders.js";

const app = new Hono().route("/orders", orderRoutes);

describe("order mutation routes", () => {
  beforeEach(() => runSeed());

  test("null request bodies return validation errors", async () => {
    const order = [...getDB().orders.values()][0]!;
    const cancel = await app.request(`/orders/${order.orderNumber}/cancel`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "null",
    });
    const invoice = await app.request(`/orders/${order.orderNumber}/invoice`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "null",
    });

    expect(cancel.status).toBe(400);
    expect(invoice.status).toBe(400);
  });

  test("manager cannot mutate an order from another store", async () => {
    const db = getDB();
    const manager = [...db.employees.values()].find((employee) => {
      if (employee.role !== "MANAGER") return false;
      return [...db.orders.values()].some(
        (order) =>
          order.merchantId === employee.merchantId &&
          order.storeUuid !== employee.storeUuid,
      );
    });
    expect(manager).toBeDefined();
    const order = [...db.orders.values()].find(
      (candidate) =>
        candidate.merchantId === manager!.merchantId &&
        candidate.storeUuid !== manager!.storeUuid,
    )!;

    const cancel = await app.request(`/orders/${order.orderNumber}/cancel`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ employeeId: manager!.id, reasonId: 1 }),
    });
    const invoice = await app.request(`/orders/${order.orderNumber}/invoice`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ employeeId: manager!.id, invoiceNumber: "INV-1" }),
    });

    expect(cancel.status).toBe(403);
    expect(invoice.status).toBe(403);
  });
});
