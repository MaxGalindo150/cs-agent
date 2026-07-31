"use client";

import { Button } from "@/components/ui/button";
import { useIdentity } from "@/lib/identity/context";
import { formatScenarioTag } from "@/lib/identity/types";
import { cn } from "@/lib/utils";

/** Simulated host-app login bar: "Log in as: Alice | Bob | Carol | Guest".
 *  Not a real auth form — picking a user is instant, standing in for whatever
 *  the real host app's login would have already resolved. Each name is
 *  tagged with a dot when that user has a known support scenario seeded
 *  (see mock-server/src/seed/scenarios/) — hover for which one. */
export function IdentityBar() {
  const { users, activeUser, login, logout } = useIdentity();

  return (
    <div className="flex h-12 shrink-0 items-center gap-2 border-b border-zinc-800 bg-zinc-950 px-4">
      <span className="text-xs text-zinc-500">Log in as:</span>
      <div className="flex items-center gap-1.5">
        {users.map((user) => {
          const active = activeUser?.id === user.id;
          const hasIssue = user.scenarioTags.length > 0;
          return (
            <Button
              key={user.id}
              variant={active ? "secondary" : "ghost"}
              size="sm"
              onClick={() => login(user)}
              className={cn(active && "text-zinc-100")}
              title={
                hasIssue
                  ? `Known issue: ${user.scenarioTags.map(formatScenarioTag).join(", ")}`
                  : "No known issues"
              }
            >
              {user.firstName}
              {hasIssue && (
                <span
                  className="ml-1 size-1.5 rounded-full bg-amber-500"
                  aria-hidden
                />
              )}
            </Button>
          );
        })}
        <Button
          variant={!activeUser ? "secondary" : "ghost"}
          size="sm"
          onClick={logout}
          className={cn(!activeUser && "text-zinc-100")}
        >
          Guest
        </Button>
      </div>
    </div>
  );
}
