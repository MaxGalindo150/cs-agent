"use client";

// Messages from the embedded chat to the host page, besides the token
// handshake (host-identity.ts): open an order the user tapped, and close the
// widget on Esc. public/widget.js accepts them only from its own iframe at
// the chat origin, and passes an order on only as a UUID — the host decides
// where it leads.

import { useEffect, useState } from "react";

import { trustedHostOrigin } from "@/lib/host/host-identity";

// Wire protocol shared with public/widget.js.
const OPEN_ORDER = "cashea-chat:open-order";
const CLOSE = "cashea-chat:close";

export interface HostBridge {
  /** Show this order in the host app. Undefined when there's no trusted host. */
  openOrder?: (orderUuid: string) => void;
}

/** The embed's line to its host page. Also closes the widget on Esc. */
export function useHostBridge(): HostBridge {
  // Resolved once, on the client (the page is prerendered without a window).
  const [hostOrigin] = useState<string | null>(() =>
    typeof window === "undefined" ? null : trustedHostOrigin(window.location.search),
  );

  useEffect(() => {
    if (!hostOrigin) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") window.parent.postMessage({ type: CLOSE }, hostOrigin as string);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [hostOrigin]);

  if (!hostOrigin) return {};
  return {
    openOrder: (orderUuid) =>
      window.parent.postMessage({ type: OPEN_ORDER, orderUuid }, hostOrigin),
  };
}
