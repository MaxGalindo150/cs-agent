"use client";

import { useEffect, useState } from "react";

import {
  fetchUserCredit,
  fetchUserMembership,
  fetchUserOrders,
} from "@/lib/dashboard/api";
import type {
  CreditSummary,
  DashboardOrder,
  MembershipSummary,
} from "@/lib/dashboard/types";
import { useIdentity } from "@/lib/identity/context";
import { formatScenarioTag } from "@/lib/identity/types";
import { cn } from "@/lib/utils";

function formatMoney(cents: number): string {
  return (cents / 100).toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
  });
}

const STATUS_STYLES: Record<string, string> = {
  active: "bg-emerald-500/10 text-emerald-400",
  approved: "bg-emerald-500/10 text-emerald-400",
  completed: "bg-zinc-800 text-zinc-400",
  cancelled: "bg-zinc-800 text-zinc-500",
  defaulted: "bg-red-500/10 text-red-400",
  pending: "bg-amber-500/10 text-amber-400",
};

/** Snapshot of the active demo user's own account data (orders, credit,
 *  membership) — pulled straight from the mock BNPL backend, same as the
 *  IdentityBar's user list. Lets you see at a glance that Alice/Bob/Carol
 *  are genuinely different accounts, not just different names. */
export function AccountDashboard() {
  const { activeUser } = useIdentity();
  const [orders, setOrders] = useState<DashboardOrder[]>([]);
  const [credit, setCredit] = useState<CreditSummary | null>(null);
  const [membership, setMembership] = useState<MembershipSummary | null>(null);

  useEffect(() => {
    // Nothing to fetch for an anonymous visitor. Stale data from a previous
    // login is harmless: the component renders the "not logged in" branch
    // below instead of these values whenever activeUser is null.
    if (!activeUser) return;
    let cancelled = false;
    Promise.all([
      fetchUserOrders(activeUser.id),
      fetchUserCredit(activeUser.id),
      fetchUserMembership(activeUser.id),
    ])
      .then(([o, c, m]) => {
        if (cancelled) return;
        setOrders(o);
        setCredit(c);
        setMembership(m);
      })
      .catch(() => {
        // Mock-server unreachable: leave the dashboard empty rather than block.
      });
    return () => {
      cancelled = true;
    };
  }, [activeUser]);

  if (!activeUser) {
    return (
      <div className="max-w-sm text-center">
        <p className="text-sm font-medium text-zinc-300">Demo host app</p>
        <p className="mt-1 text-sm text-zinc-500">
          Browsing anonymously — use the bar above to log in as a demo
          customer and see their account here.
        </p>
      </div>
    );
  }

  return (
    <div className="w-full max-w-lg">
      <div className="mb-4">
        <p className="text-sm font-medium text-zinc-100">
          {activeUser.firstName} {activeUser.lastName}
        </p>
        <p className="text-xs text-zinc-500">{activeUser.email}</p>
        {activeUser.scenarioTags.length > 0 ? (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {activeUser.scenarioTags.map((tag) => (
              <span
                key={tag}
                className="rounded-full bg-amber-500/10 px-2 py-0.5 text-xs text-amber-400"
              >
                {formatScenarioTag(tag)}
              </span>
            ))}
          </div>
        ) : (
          <p className="mt-2 text-xs text-zinc-600">No known issues</p>
        )}
      </div>

      <div className="mb-4 grid grid-cols-2 gap-3">
        <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-3">
          <p className="text-xs text-zinc-500">Membership</p>
          <p className="mt-1 text-sm text-zinc-200 capitalize">
            {membership ? membership.tier : "—"}
          </p>
          {membership && (
            <p className="text-xs text-zinc-500">
              {membership.pointsBalance.toLocaleString()} pts
            </p>
          )}
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-3">
          <p className="text-xs text-zinc-500">Credit</p>
          <p className="mt-1 text-sm text-zinc-200">
            {credit ? formatMoney(credit.availableCredit) : "—"}
          </p>
          {credit && (
            <p className="text-xs text-zinc-500">
              of {formatMoney(credit.creditLimit)} available
            </p>
          )}
        </div>
      </div>

      <p className="mb-2 text-xs text-zinc-500">
        Orders {orders.length > 0 && `(${orders.length})`}
      </p>
      <div className="max-h-64 overflow-y-auto rounded-lg border border-zinc-800">
        {orders.length === 0 ? (
          <p className="p-3 text-sm text-zinc-500">No orders.</p>
        ) : (
          <ul className="divide-y divide-zinc-800">
            {orders.map((order) => (
              <li
                key={order.id}
                className="flex items-center justify-between gap-2 px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm text-zinc-200">
                    {order.merchantName}
                  </p>
                  <p className="text-xs text-zinc-500">
                    {order.id} · {order.plan}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 text-xs capitalize",
                      STATUS_STYLES[order.status] ?? "bg-zinc-800 text-zinc-400",
                    )}
                  >
                    {order.status}
                  </span>
                  <span className="text-sm text-zinc-300">
                    {formatMoney(order.totalAmount)}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
