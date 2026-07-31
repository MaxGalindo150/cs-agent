import { AccountDashboard } from "@/components/dashboard/account-dashboard";
import { IdentityBar } from "@/components/identity/identity-bar";
import { ChatWidget } from "@/components/widget/chat-widget";

/**
 * Placeholder "host app" — stands in for whatever real product the support
 * widget gets embedded in. Its only job here is to simulate an
 * already-authenticated caller: the IdentityBar picks a demo user (or stays
 * anonymous), the AccountDashboard shows that user's own data so each demo
 * user is visibly distinct, and the floating ChatWidget forwards the active
 * identity to agent-service on every message.
 */
export default function Home() {
  return (
    <div className="flex h-full flex-col bg-background text-foreground">
      <IdentityBar />

      <div className="flex flex-1 items-center justify-center overflow-y-auto px-4 py-8">
        <AccountDashboard />
      </div>

      <ChatWidget />
    </div>
  );
}
