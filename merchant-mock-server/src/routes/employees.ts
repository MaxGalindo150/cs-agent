import { Hono } from "hono";
import { z } from "zod";
import { findEmployee, findPOS, getDB } from "../db.js";
import { simulatedDelay } from "../utils/delay.js";

// Los bodies POST llegaban tipados a mano y solo se comprobaba que existieran,
// así que un `{"phone": 42}` pasaba el guard y se escribía en un campo `string`.
// zod los valida de verdad y devuelve 400 con el detalle.
const registerPhoneBody = z.object({ phone: z.string().min(1) });
const verifyCodeBody = z.object({ code: z.string().min(1) });
const linkQRBody = z.object({ activationCode: z.string().min(1) });

export const employeeRoutes = new Hono();

// ── Detalle de empleado ────────────────────────────────────────────
employeeRoutes.get("/:id", async (c) => {
  await simulatedDelay();
  const employee = findEmployee(c.req.param("id"));
  if (!employee) {
    return c.json({ error: `No se encontró empleado ${c.req.param("id")}` }, 404);
  }
  return c.json(employee);
});

// ── 2FA: Registrar teléfono ────────────────────────────────────────
employeeRoutes.post("/:id/2fa/register-phone", async (c) => {
  await simulatedDelay();
  const employee = findEmployee(c.req.param("id"));
  if (!employee) {
    return c.json({ error: `No se encontró empleado ${c.req.param("id")}` }, 404);
  }

  let body: z.infer<typeof registerPhoneBody>;
  try {
    body = registerPhoneBody.parse(await c.req.json());
  } catch {
    return c.json({ error: "phone es obligatorio y debe ser un string" }, 400);
  }

  // Caso frecuente: el teléfono ya es el suyo
  if (employee.phoneNumber === body.phone) {
    employee.phoneRegistered = true;
    return c.json({
      alreadyRegistered: true,
      message: "El teléfono proporcionado ya es el registrado para este empleado",
      phoneRegistered: true,
    });
  }

  employee.phoneNumber = body.phone;
  employee.phoneRegistered = true;
  // Al cambiar el teléfono, se requiere cambio de password
  employee.mustChangePassword = true;

  return c.json({
    alreadyRegistered: false,
    phoneRegistered: true,
  });
});

// ── 2FA: Enviar código OTP ─────────────────────────────────────────
employeeRoutes.post("/:id/2fa/send-code", async (c) => {
  await simulatedDelay();
  const employee = findEmployee(c.req.param("id"));
  if (!employee) {
    return c.json({ error: `No se encontró empleado ${c.req.param("id")}` }, 404);
  }

  if (!employee.phoneRegistered) {
    return c.json(
      { error: "phone_not_registered", message: "Debe registrar un teléfono antes de recibir códigos" },
      403,
    );
  }

  // El escenario otpNeverArrives simula entrega fallida con un challenge que
  // ya nace expirado; el endpoint sigue respondiendo 200 como el proveedor real.
  getDB().otpChallenges.set(
    employee.id,
    Date.now() + (employee.otpNeverArrives ? -1 : 5 * 60 * 1000),
  );
  return c.json({ sent: true });
});

// ── 2FA: Verificar código OTP ──────────────────────────────────────
employeeRoutes.post("/:id/2fa/verify-code", async (c) => {
  await simulatedDelay();
  const employee = findEmployee(c.req.param("id"));
  if (!employee) {
    return c.json({ error: `No se encontró empleado ${c.req.param("id")}` }, 404);
  }

  let body: z.infer<typeof verifyCodeBody>;
  try {
    body = verifyCodeBody.parse(await c.req.json());
  } catch {
    return c.json({ error: "code es obligatorio y debe ser un string" }, 400);
  }

  if (!employee.phoneRegistered) {
    return c.json(
      { error: "phone_not_registered", message: "Debe registrar un teléfono antes de verificar códigos" },
      403,
    );
  }

  const db = getDB();
  const expiresAt = db.otpChallenges.get(employee.id);
  if (expiresAt === undefined) {
    return c.json(
      { error: "code_not_requested", message: "Solicite un código antes de verificarlo" },
      409,
    );
  }
  if (expiresAt < Date.now()) {
    db.otpChallenges.delete(employee.id);
    return c.json(
      { error: "code_expired", message: "El código ha expirado. Solicite uno nuevo." },
      409,
    );
  }

  // Código demo
  if (body.code === "123456") {
    db.otpChallenges.delete(employee.id);
    return c.json({ verified: true });
  }

  return c.json(
    { error: "invalid_code", message: "El código es incorrecto" },
    409,
  );
});

// ── POS por UUID ───────────────────────────────────────────────────
// (montado bajo /api/v1/pos/:uuid en el server)
export const posRoutes = new Hono();

posRoutes.get("/:uuid", async (c) => {
  await simulatedDelay();
  const pos = findPOS(c.req.param("uuid"));
  if (!pos) {
    return c.json({ error: `No se encontró POS ${c.req.param("uuid")}` }, 404);
  }
  return c.json(pos);
});

// ── POST: Vincular QR a POS ─────────────────────────────────────────
posRoutes.post("/:uuid/link-qr", async (c) => {
  await simulatedDelay();
  const pos = findPOS(c.req.param("uuid"));
  if (!pos) {
    return c.json({ error: `No se encontró POS ${c.req.param("uuid")}` }, 404);
  }

  let body: z.infer<typeof linkQRBody>;
  try {
    body = linkQRBody.parse(await c.req.json());
  } catch {
    return c.json({ error: "activationCode es obligatorio y debe ser un string" }, 400);
  }

  pos.qrLinked = true;
  pos.qrCode = {
    activationCode: body.activationCode,
    status: "LINKED",
  };

  return c.json({
    status: "linked",
    posUuid: pos.posUuid,
    activationCode: body.activationCode,
  });
});
