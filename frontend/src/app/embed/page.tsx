"use client";

import { Chat, type ChatCopy } from "@/components/chat/chat";
import { useHostBridge } from "@/lib/host/host-bridge";
import { useHostIdentity } from "@/lib/host/host-identity";

// The only host today is merchant-web, so the copy speaks to aliados.
const MERCHANT_COPY: ChatCopy = {
  title: "Cheo",
  headerSubtitle: "Soporte Cashea",
  greeting: "¡Hola, aliado!",
  subtitle: "¿En qué puedo ayudarte hoy?",
  suggestions: [
    "¿Cuáles son mis últimas órdenes?",
    "¿Cómo va el cierre de caja de hoy?",
    "¿Cómo creo una orden con Link?",
    "¿Cómo cancelo una orden?",
  ],
  placeholder: "Pregúntale a Cheo…",
};

/** The chat alone, filling the iframe, as the host app's signed-in user (or
 *  anonymous). The launcher bubble and open/close live in the host page
 *  (public/widget.js), not here. */
export default function EmbedPage() {
  const identity = useHostIdentity();
  const host = useHostBridge();
  return (
    <Chat
      variant="widget"
      storageKey="csa:embed:conversationId"
      copy={MERCHANT_COPY}
      identity={identity}
      showIdentity={false}
      allowAttachments={false}
      onOpenOrder={host.openOrder}
    />
  );
}
