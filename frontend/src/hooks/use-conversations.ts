"use client";

import { useCallback, useEffect, useState } from "react";

import { listConversations } from "@/lib/chat/api";
import type { ConversationSummary } from "@/lib/chat/types";

export interface UseConversations {
  conversations: ConversationSummary[];
  /** Refetch the list (e.g. after a new message is sent). */
  refresh: () => void;
}

/** Fetches the conversation list for the sidebar. */
export function useConversations(): UseConversations {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);

  const refresh = useCallback(() => {
    listConversations()
      .then(setConversations)
      .catch(() => {
        // Non-fatal: keep whatever we had if the list can't load.
      });
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { conversations, refresh };
}
