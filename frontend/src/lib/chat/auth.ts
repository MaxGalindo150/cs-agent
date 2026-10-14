// Who the chat is talking as, from agent-service's point of view.
//
// Each surface supplies its own: the demo page sends its simulated user as
// X-User-* headers (dev only on the server), the embedded widget sends a
// session token obtained from the host app (lib/host/). Everything that calls
// agent-service goes through `authedFetch`, so neither the API client nor the
// hooks know which one is in use.

/** What a call is for. A chat turn may need more than identifying the caller:
 *  the embed also sends the host user's own token so the agent's tools can
 *  read Cashea's API as them (lib/host/). Other calls never carry it. */
export type CallPurpose = "chat" | "api";

export interface ChatAuth {
  /** Headers that identify the caller. May do network work (renewing a
   *  token), so it is async; an empty object means anonymous. */
  headers(purpose: CallPurpose): Promise<Record<string, string>>;
  /** Drop any cached credential after a 401, so the next `headers()` renews. */
  invalidate?(): void;
}

/** fetch with the caller's identity attached. On a 401 it invalidates the
 *  credential and retries once — an expired session token renews transparently. */
export async function authedFetch(
  url: string,
  init: RequestInit = {},
  auth?: ChatAuth,
  purpose: CallPurpose = "api",
): Promise<Response> {
  const send = async () =>
    fetch(url, {
      ...init,
      headers: { ...init.headers, ...(await auth?.headers(purpose)) },
    });

  const res = await send();
  if (res.status !== 401 || !auth?.invalidate) return res;
  auth.invalidate();
  return send();
}

/** The demo page's simulated login (lib/identity/), trusted by agent-service
 *  only in dev. */
export function demoUserAuth(user: { id: string; email?: string }): ChatAuth {
  const headers: Record<string, string> = { "X-User-Id": user.id };
  if (user.email) headers["X-User-Email"] = user.email;
  return { headers: async () => headers };
}
