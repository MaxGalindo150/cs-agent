import { beforeEach, describe, expect, test } from "bun:test";
import { Hono } from "hono";
import { getDB, resetDB } from "../db.js";
import type { Employee } from "../schema/index.js";
import { employeeRoutes } from "./employees.js";

const app = new Hono().route("/employees", employeeRoutes);

function employee(overrides: Partial<Employee> = {}): Employee {
  return {
    id: "emp_1",
    merchantId: 1,
    phoneNumber: "+58 412 123 4567",
    phoneRegistered: false,
    mustChangePassword: false,
    otpNeverArrives: false,
    ...overrides,
  } as Employee;
}

describe("employee 2FA routes", () => {
  beforeEach(() => {
    resetDB();
    getDB().employees.set("emp_1", employee());
  });

  test("registering the existing phone updates persisted state", async () => {
    const response = await app.request("/employees/emp_1/2fa/register-phone", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phone: "+58 412 123 4567" }),
    });

    expect(response.status).toBe(200);
    expect(getDB().employees.get("emp_1")?.phoneRegistered).toBe(true);
  });

  test("null request bodies return validation errors", async () => {
    const register = await app.request("/employees/emp_1/2fa/register-phone", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "null",
    });
    const verify = await app.request("/employees/emp_1/2fa/verify-code", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "null",
    });

    expect(register.status).toBe(400);
    expect(verify.status).toBe(400);
  });

  test("verification requires a requested challenge", async () => {
    getDB().employees.get("emp_1")!.phoneRegistered = true;

    const response = await app.request("/employees/emp_1/2fa/verify-code", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: "123456" }),
    });

    expect(response.status).toBe(409);
    expect((await response.json()).error).toBe("code_not_requested");
  });

  test("requested demo code verifies once", async () => {
    getDB().employees.get("emp_1")!.phoneRegistered = true;
    await app.request("/employees/emp_1/2fa/send-code", { method: "POST" });

    const first = await app.request("/employees/emp_1/2fa/verify-code", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: "123456" }),
    });
    const replay = await app.request("/employees/emp_1/2fa/verify-code", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: "123456" }),
    });

    expect(first.status).toBe(200);
    expect(replay.status).toBe(409);
  });
});
