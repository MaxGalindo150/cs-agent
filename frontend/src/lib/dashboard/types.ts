// Read-only slices of the mock BNPL backend's per-user data, shown on the
// host-app placeholder page so each demo user visibly differs (their known
// support scenario, orders, credit, points). Amounts are in cents, same
// convention as mock-server.

export interface DashboardOrder {
  id: string;
  merchantName: string;
  status: string;
  plan: string;
  totalAmount: number;
}

export interface CreditSummary {
  creditLimit: number;
  outstandingBalance: number;
  availableCredit: number;
  status: string;
}

export interface MembershipSummary {
  tier: string;
  pointsBalance: number;
}
