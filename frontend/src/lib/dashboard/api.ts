// Reads the mock BNPL backend's per-user data directly, same as
// lib/identity/api.ts — this is the host app's own account data, agent-service
// never sees these calls.

import type {
  CreditSummary,
  DashboardOrder,
  MembershipSummary,
} from "@/lib/dashboard/types";

const BNPL_API_URL =
  process.env.NEXT_PUBLIC_BNPL_API_URL ?? "http://localhost:3001";

export async function fetchUserOrders(userId: string): Promise<DashboardOrder[]> {
  const res = await fetch(`${BNPL_API_URL}/api/v1/users/${userId}/orders`);
  if (!res.ok) {
    throw new Error(`request failed: ${res.status} ${res.statusText}`);
  }
  const body: { data: DashboardOrder[] } = await res.json();
  return body.data;
}

export async function fetchUserCredit(userId: string): Promise<CreditSummary | null> {
  const res = await fetch(`${BNPL_API_URL}/api/v1/users/${userId}/credit`);
  if (res.status === 404) return null;
  if (!res.ok) {
    throw new Error(`request failed: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function fetchUserMembership(
  userId: string,
): Promise<MembershipSummary | null> {
  const res = await fetch(`${BNPL_API_URL}/api/v1/users/${userId}/membership`);
  if (res.status === 404) return null;
  if (!res.ok) {
    throw new Error(`request failed: ${res.status} ${res.statusText}`);
  }
  return res.json();
}
