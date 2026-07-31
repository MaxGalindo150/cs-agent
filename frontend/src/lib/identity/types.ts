// A demo identity from the mock BNPL backend (mock-server), simulating the
// "already-authenticated host app" that the support widget is embedded in.
// Not a real auth system — see lib/identity/api.ts.

export interface DemoUser {
  id: string;
  firstName: string;
  lastName: string;
  email: string;
  /** Known support scenarios seeded onto this user (e.g. "shipment_stuck") —
   *  see mock-server/src/seed/scenarios/. Empty for a user with no known
   *  issue. */
  scenarioTags: string[];
}

/** "shipment_stuck" -> "Shipment stuck". */
export function formatScenarioTag(tag: string): string {
  const words = tag.split("_").join(" ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
