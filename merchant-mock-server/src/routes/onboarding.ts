import { Hono } from "hono";
import { findOnboarding } from "../db.js";
import { simulatedDelay } from "../utils/delay.js";

export const onboardingRoutes = new Hono();

// ── Estado de onboarding por ID ────────────────────────────────────
onboardingRoutes.get("/:onboardingId", async (c) => {
  await simulatedDelay();
  const onboarding = findOnboarding(c.req.param("onboardingId"));
  if (!onboarding) {
    return c.json(
      { error: `No se encontró onboarding ${c.req.param("onboardingId")}` },
      404,
    );
  }
  return c.json(onboarding);
});
