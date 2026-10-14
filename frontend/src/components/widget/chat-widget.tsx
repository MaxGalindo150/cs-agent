"use client";

import { MessageCircle, X } from "lucide-react";
import { useMemo, useState } from "react";

import { Chat, type ChatIdentity } from "@/components/chat/chat";
import { Button } from "@/components/ui/button";
import { demoUserAuth } from "@/lib/chat/auth";
import { useIdentity } from "@/lib/identity/context";

/** Floating support widget: a launcher bubble (bottom-right) that opens a
 *  fixed-size panel reusing the same `Chat` screen the standalone page uses.
 *  The demo page's stand-in for a real embed (public/widget.js), chatting as
 *  whichever demo user the IdentityBar has logged in. */
export function ChatWidget() {
  const [open, setOpen] = useState(false);
  const { activeUser, ready } = useIdentity();

  const identity = useMemo<ChatIdentity | undefined>(
    () =>
      activeUser
        ? {
            auth: demoUserAuth(activeUser),
            label: `${activeUser.firstName} ${activeUser.lastName}`,
            key: activeUser.id,
          }
        : undefined,
    [activeUser],
  );

  return (
    <>
      {/* Wait for the stored login: a chat mounted before it would restore
          the user's last conversation as anonymous and be refused. */}
      {open && ready && (
        <div className="fixed right-6 bottom-24 z-50 h-[640px] w-[400px] max-w-[calc(100vw-3rem)] overflow-hidden rounded-2xl border border-border bg-background shadow-2xl">
          <Chat variant="widget" identity={identity} />
        </div>
      )}

      <Button
        variant="default"
        size="icon-lg"
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? "Cerrar chat de soporte" : "Abrir chat de soporte"}
        className="fixed right-6 bottom-6 z-50 size-14 rounded-full shadow-lg"
      >
        {open ? <X className="size-6" /> : <MessageCircle className="size-6" />}
      </Button>
    </>
  );
}
