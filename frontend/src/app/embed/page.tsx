import { Chat, type ChatCopy } from "@/components/chat/chat";

// The only host today is merchant-web, so the copy speaks to aliados.
const MERCHANT_COPY: ChatCopy = {
  title: "Cheo",
  greeting: "¡Hola, aliado!",
  subtitle: "¿En qué puedo ayudarte hoy?",
  suggestions: [
    "¿Cuándo recibo mis pagos?",
    "¿Cómo anulo una orden?",
    "¿Cómo agrego un empleado?",
    "Hablar con una persona",
  ],
};

/** The chat alone, filling the iframe. The launcher bubble and open/close
 *  live in the host page (public/widget.js), not here. */
export default function EmbedPage() {
  return (
    <Chat variant="widget" storageKey="csa:embed:conversationId" copy={MERCHANT_COPY} />
  );
}
