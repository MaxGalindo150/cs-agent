"use client";

import { MessageCircle, X } from "lucide-react";
import { useState } from "react";

import { Chat } from "@/components/chat/chat";
import { Button } from "@/components/ui/button";

/** Floating support widget: a launcher bubble (bottom-right) that opens a
 *  fixed-size panel reusing the same `Chat` screen the standalone page uses.
 *  Standing in for how a real embed (Intercom-style) would sit on top of a
 *  host app's own pages. */
export function ChatWidget() {
  const [open, setOpen] = useState(false);

  return (
    <>
      {open && (
        <div className="fixed right-6 bottom-24 z-50 h-[640px] w-[400px] max-w-[calc(100vw-3rem)] overflow-hidden rounded-2xl border border-zinc-800 bg-background shadow-2xl">
          <Chat variant="widget" />
        </div>
      )}

      <Button
        variant="default"
        size="icon-lg"
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? "Close support chat" : "Open support chat"}
        className="fixed right-6 bottom-6 z-50 size-14 rounded-full shadow-lg"
      >
        {open ? <X className="size-6" /> : <MessageCircle className="size-6" />}
      </Button>
    </>
  );
}
