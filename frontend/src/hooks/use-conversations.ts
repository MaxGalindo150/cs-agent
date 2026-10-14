"use client";

import { useCallback, useEffect, useState } from "react";

import { listConversations } from "@/lib/chat/api";
import type { ChatAuth } from "@/lib/chat/auth";
import type { ConversationSummary } from "@/lib/chat/types";

export interface UseConversations {
  conversations: ConversationSummary[];
  /** Refetch the list (e.g. after a new message is sent). */
  refresh: () => void;
}

/** Fetches the caller's conversation list for the sidebar. Refetches when the
 *  caller changes — agent-service only lists the caller's own sessions. */
export function useConversations(auth?: ChatAuth): UseConversations {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);

  const refresh = useCallback(() => {
    listConversations(auth)
      .then(setConversations)
      .catch(() => {
        // Non-fatal: keep whatever we had if the list can't load.
      });
  }, [auth]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { conversations, refresh };
}
