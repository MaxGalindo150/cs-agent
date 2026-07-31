import { Hono } from "hono";
import { getDB } from "../db.js";
import { simulatedDelay } from "../utils/delay.js";
import { ALL_SCENARIOS, SCENARIO_DESCRIPTIONS } from "../seed/scenarios/index.js";

export const scenarioRoutes = new Hono();

// ── GET /api/v1/scenarios ───────────────────────────────────────────
/** Catálogo de todos los escenarios disponibles con los userIds asignados. */
scenarioRoutes.get("/scenarios", async (c) => {
  await simulatedDelay();
  const db = getDB();

  const result = ALL_SCENARIOS.map((scenario) => {
    const users = [...db.users.values()]
      .filter((u) => u.scenarioTags.includes(scenario.tag))
      .map((u) => ({
        id: u.id,
        name: `${u.firstName} ${u.lastName}`,
        email: u.email,
        allTags: u.scenarioTags,
      }));
    return {
      tag: scenario.tag,
      description: SCENARIO_DESCRIPTIONS[scenario.tag] ?? scenario.description,
      userCount: users.length,
      users,
    };
  });

  return c.json({ data: result });
});

// ── GET /api/v1/scenarios/:tag ──────────────────────────────────────
/** Lista los userIds que tienen un escenario específico. */
scenarioRoutes.get("/scenarios/:tag", async (c) => {
  await simulatedDelay();
  const db = getDB();
  const tag = c.req.param("tag");

  const users = [...db.users.values()]
    .filter((u) => u.scenarioTags.includes(tag as never))
    .map((u) => ({
      id: u.id,
      name: `${u.firstName} ${u.lastName}`,
      email: u.email,
      allTags: u.scenarioTags,
    }));

  return c.json({
    tag,
    description: SCENARIO_DESCRIPTIONS[tag] ?? "Unknown scenario",
    userCount: users.length,
    users,
  });
});
