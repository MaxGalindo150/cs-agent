import type { Database } from "../db.js";
import type { ScenarioTag } from "../schema/index.js";

export interface Scenario {
  tag: ScenarioTag;
  description: string;
  /** Busca un usuario apto y muta la DB para crear la anomalía. */
  apply(db: Database): void;
}

/** Helper: marcar un usuario con un scenario tag. */
export function tagUser(db: Database, userId: string, tag: ScenarioTag): void {
  const user = db.users.get(userId);
  if (user && !user.scenarioTags.includes(tag)) {
    user.scenarioTags.push(tag);
  }
}

/** Helper: obtener todos los IDs de usuario que ya tienen N scenario tags. */
export function usersWithFewestTags(db: Database, excludeTags: ScenarioTag[] = []): string[] {
  const eligible = [...db.users.values()]
    .filter((u) => u.status === "active")
    .filter((u) => !excludeTags.some((t) => u.scenarioTags.includes(t)))
    .sort((a, b) => a.scenarioTags.length - b.scenarioTags.length);
  return eligible.map((u) => u.id);
}

/** Helper: las órdenes activas (no completed/cancelled) de un usuario. */
export function activeOrders(db: Database, userId: string) {
  return [...db.orders.values()].filter(
    (o) => o.userId === userId && (o.status === "active" || o.status === "approved"),
  );
}

/** Helper: ordenes completadas de un usuario. */
export function completedOrders(db: Database, userId: string) {
  return [...db.orders.values()].filter(
    (o) => o.userId === userId && o.status === "completed",
  );
}
