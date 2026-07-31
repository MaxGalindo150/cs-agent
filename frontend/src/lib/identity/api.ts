// Reads the mock BNPL backend's own user list directly — simulating the host
// app's own login, which already knows its users without going through
// agent-service. agent-service never sees this call.

import type { DemoUser } from "@/lib/identity/types";

const BNPL_API_URL =
  process.env.NEXT_PUBLIC_BNPL_API_URL ?? "http://localhost:3001";

interface BnplUser {
  id: string;
  firstName: string;
  lastName: string;
  email: string;
  scenarioTags: string[];
}

/** The mock-server's static demo users (see mock-server/src/seed/seed.ts). */
export async function fetchDemoUsers(): Promise<DemoUser[]> {
  const res = await fetch(`${BNPL_API_URL}/api/v1/users`);
  if (!res.ok) {
    throw new Error(`request failed: ${res.status} ${res.statusText}`);
  }
  const body: { data: BnplUser[] } = await res.json();
  return body.data.map((u) => ({
    id: u.id,
    firstName: u.firstName,
    lastName: u.lastName,
    email: u.email,
    scenarioTags: u.scenarioTags,
  }));
}
