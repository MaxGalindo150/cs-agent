"use client";

// The embedded widget's identity: whoever is signed in to the host app.
//
// The loader (public/widget.js) opens /embed?host=<origin>&auth=1 when the
// host passed `getToken`. To act as that user the iframe asks the host for a
// token over postMessage, exchanges it once at POST /v1/auth/session, and
// sends the resulting session token on every call. The session token lives
// only in memory; when it expires (or a call comes back 401) the cycle repeats.
//
// Messages are accepted only from window.parent at the exact host origin, and
// that origin must be on NEXT_PUBLIC_EMBED_HOST_ORIGINS — the same hosts
// next.config.ts lets frame /embed.

import { useMemo, useState } from "react";

import type { ChatIdentity } from "@/components/chat/chat";
import type { ChatAuth } from "@/lib/chat/auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const ALLOWED_HOSTS = (process.env.NEXT_PUBLIC_EMBED_HOST_ORIGINS ?? "")
  .split(/[\s,]+/)
  .filter(Boolean);

// Wire protocol shared with public/widget.js.
const TOKEN_REQUEST = "cashea-chat:token-request";
const TOKEN_RESPONSE = "cashea-chat:token";

const HOST_TIMEOUT_MS = 10_000;
// Renew a little before expiry so a request never leaves with a dying token.
const RENEW_MARGIN_MS = 30_000;

interface Session {
  token: string;
  expiresAt: number;
}

/** The host origin to trust, or null when the host didn't opt in to sharing
 *  its identity (or isn't allowlisted — then the widget stays anonymous). */
function trustedHostOrigin(search: string): string | null {
  const params = new URLSearchParams(search);
  const host = params.get("host");
  if (params.get("auth") !== "1" || !host) return null;
  if (!ALLOWED_HOSTS.includes(host)) {
    console.error(`[casheaChat] ${host} is not an allowed host; staying anonymous.`);
    return null;
  }
  return host;
}

/** Ask the host page for a fresh token. Resolves null when nobody is signed in. */
function requestHostToken(hostOrigin: string): Promise<string | null> {
  const id = crypto.randomUUID();
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => {
      window.removeEventListener("message", onMessage);
      reject(new Error("host did not answer the token request"));
    }, HOST_TIMEOUT_MS);

    function onMessage(event: MessageEvent) {
      if (event.source !== window.parent || event.origin !== hostOrigin) return;
      const data = event.data as { type?: unknown; id?: unknown; token?: unknown };
      if (data?.type !== TOKEN_RESPONSE || data.id !== id) return;
      window.clearTimeout(timer);
      window.removeEventListener("message", onMessage);
      resolve(typeof data.token === "string" && data.token ? data.token : null);
    }

    window.addEventListener("message", onMessage);
    window.parent.postMessage({ type: TOKEN_REQUEST, id }, hostOrigin);
  });
}

function createHostAuth(
  hostOrigin: string,
  onSignedIn: (email: string | null) => void,
): ChatAuth {
  let session: Session | null = null;
  // Concurrent calls (the restore fetch and a send) share one renewal.
  let renewing: Promise<Session | null> | null = null;

  async function renew(): Promise<Session | null> {
    const hostToken = await requestHostToken(hostOrigin);
    if (!hostToken) {
      onSignedIn(null);
      return null;
    }
    const res = await fetch(`${API_URL}/v1/auth/session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ host_token: hostToken }),
    });
    if (!res.ok) throw new Error(`host sign-in failed: ${res.status}`);
    const body: { session_token: string; expires_in: number; email: string | null } =
      await res.json();
    onSignedIn(body.email);
    return {
      token: body.session_token,
      expiresAt: Date.now() + body.expires_in * 1000 - RENEW_MARGIN_MS,
    };
  }

  return {
    async headers(): Promise<Record<string, string>> {
      if (!session || Date.now() >= session.expiresAt) {
        renewing ??= renew().finally(() => {
          renewing = null;
        });
        session = await renewing;
      }
      return session ? { Authorization: `Bearer ${session.token}` } : {};
    },
    invalidate() {
      session = null;
    },
  };
}

/** The ChatIdentity for /embed: the host's signed-in user, or anonymous. */
export function useHostIdentity(): ChatIdentity {
  const [email, setEmail] = useState<string | null>(null);
  // Built once, on the client (the page is prerendered without a window).
  const [auth] = useState<ChatAuth | undefined>(() => {
    if (typeof window === "undefined") return undefined;
    const hostOrigin = trustedHostOrigin(window.location.search);
    return hostOrigin ? createHostAuth(hostOrigin, setEmail) : undefined;
  });

  // `key` stays fixed: a different host user means the host tears the widget
  // down (casheaChat.destroy()), not a switch inside this iframe.
  return useMemo(() => ({ auth, label: email ?? "Invitado", key: "host" }), [auth, email]);
}
