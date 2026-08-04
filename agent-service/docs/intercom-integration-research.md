# Investigación: integración con Intercom sin perder el widget propio

> Estado: investigación (no ADR, no decisión tomada). Generado a partir de research puntual sobre las APIs de Intercom (agosto 2026). Ojo: los endpoints de Custom Channel Events (`notify_new_conversation`, `notify_new_message`, etc.) **no son parte de la API pública documentada** — están en "managed availability" bajo la versión `preview` (header `Intercom-Version: preview`, [ref](https://developers.intercom.com/docs/references/preview/rest-api/api.intercom.io/custom-channel-events/notifynewconversation)) y requieren acceso gestionado por el equipo de cuenta de Intercom, no son self-serve. Antes de implementar, validar con ese equipo los puntos marcados como "managed availability" / plan requerido.

## Objetivo

Evaluar si es posible aprovechar la infraestructura de Intercom (inbox de agentes, asignación por equipos, macros, reporting, Fin AI) **sin reemplazar** el widget de chat propio (`frontend/src/components/chat/*`) ni el harness propio (`agent/loop`, `present_choice`, `needs_human`).

## Mecanismo relevante: Custom Channel ≠ Switch

Son dos cosas distintas y es fácil confundirlas:

| | Switch | Custom Channel (Custom Channel Events API) |
|---|---|---|
| Qué es | Handoff de llamada telefónica → chat | Canal genérico vía API para integraciones externas |
| Aplica a nuestro caso | No | **Sí** — es el mecanismo correcto |

Con Custom Channel, Intercom trata nuestra integración "como cualquier otro canal nativo": la conversación aparece en su inbox, pero el frontend sigue siendo 100% nuestro widget.

---

## ✅ Lo que sí tenemos (es posible)

- **Inbox compartido**: las conversaciones escaladas pueden aparecer en el inbox de Intercom con historial completo, para que un agente humano las trabaje ahí (asignación, macros, tags, reporting), sin tocar el widget del cliente.
- **Flujo bidireccional básico**: crear una conversación desde nuestro backend (Custom Channel Events) cuando el `Agent` decide `needs_human`, y recibir las respuestas del agente humano vía el webhook estándar `conversation.admin.replied` (no existe un topic `conversation.reply.created` — ese nombre no es real) para inyectarlas de vuelta en la sesión y mostrarlas en nuestro widget — mismo patrón que ya usamos para `choice_id`/`present_choice`. Falta definir cómo el `conversation_id` de Intercom y el contenido de la respuesta se mapean de regreso a nuestro `session_id`/widget — probablemente vía un campo custom attribute o metadata guardado al crear la conversación.
- **Mapeo de identidad**: Contacts API permite buscar/crear un `Contact` de Intercom a partir de nuestro `Principal`, para asociar la conversación al usuario correcto.
- **Fin AI accesible vía API** ("Fin over API"): en teoría permite que Fin razone dentro de nuestra propia UI en lugar del Messenger de Intercom — pendiente de confirmar el detalle técnico exacto (ver bloqueantes abajo).
- **Idempotencia estándar**: el comportamiento real de los webhooks de Intercom es: 5 segundos de timeout de respuesta, 1 solo reintento (a los 1 minuto) si hay timeout o error; un `429` produce throttling (de 1 minuto hasta 2 horas, se descarta pasado ese límite); fallos repetidos pueden pausar o suspender la suscripción del webhook. La entrega es "at-least-once", así que puede llegar duplicado — se puede aplicar el mismo patrón de dedup que ya usamos (hash/ID único), usando el `id` de nivel superior del payload del webhook como clave, no es un caso nuevo para nuestro harness. ([ref](https://developers.intercom.com/docs/references/webhooks/webhook-models))
- **Alternativa más liviana (Opción B)**: si no necesitamos threading en vivo bidireccional, se puede usar solo Conversations API + Contacts API "normales" (crear conversación al escalar, cerrar al resolver) — mucho menos integración, sin el gate de "managed availability" de Custom Channel.

## ❌ Lo que no es posible (o no confirmado)

- **No se puede "entrar" al builder visual de Workflows de Intercom desde un Custom Channel.** Workflows (el bot builder con botones/paths, antes "Operator/Custom Bots") solo soporta canales nativos de Intercom: Web/Messenger, iOS, Android, Email, SMS, WhatsApp, Facebook, Instagram, Twitter, Telegram, Phone Call. **No existe un canal "Custom" en esa lista.** Esto significa que alguien de negocio no puede diseñar visualmente un flujo de botones en Intercom y esperar que se renderice en nuestro widget — ese mecanismo seguimos siendo nosotros los que lo construimos (ya lo tenemos: `present_choice` → `choice_id` → `choice-prompt.tsx`).
- **No hay "push" de componentes de botón estructurados hacia un canal custom** documentado — Intercom no tiene un mecanismo confirmado para que un Workflow nativo le entregue a nuestro widget una lista de opciones que renderizar como botones. Si quisiéramos ese nivel de control visual gestionado por Intercom, la conversación tendría que vivir en un canal que Intercom controla de punta a punta (su propio Messenger embebido, o WhatsApp/SMS) — y ahí perdemos control total de la UI.
- **Personalización de Messenger limitada y de pago**: personalizar launcher/home del Messenger nativo requiere plan **Advanced o Expert**. No aplica si nos quedamos 100% en Custom Channel con nuestro widget, pero sí si en algún punto migramos parte del tráfico a Messenger nativo.
- **"Fin over API" / Custom Channel está en "managed availability"**: no es self-serve. Hay que contactar al equipo de cuenta/ventas de Intercom para obtener acceso, soporte y (probablemente) costo adicional. **Esto es un bloqueante duro para saber si el plan actual lo permite** antes de invertir tiempo de ingeniería.
- **No confirmado**: si Fin-over-API devuelve contenido estructurado (tipo "quick reply") que nuestro widget pueda pintar como botones nativos, o solo texto libre. Requiere confirmación directa con Intercom.
- **Custom Action (Data Connector) es lo inverso de lo que buscamos**: dentro de un Workflow nativo se puede agregar un paso que llame a nuestra API a mitad del flujo — pero es Intercom orquestando y llamando a nuestro backend, no nuestro widget consumiendo un flujo de botones diseñado en Intercom.

---

## Mapeo a nuestra arquitectura actual

| Pieza actual | Rol si integramos Custom Channel |
|---|---|
| `Agent.respond` + resultado `needs_human` | Trigger para crear/sincronizar la conversación en Intercom |
| `present_choice` / `choice_id` / `choice-prompt.tsx` | Sigue siendo nuestro — Intercom no lo reemplaza |
| `chat.py` / `chat_stream.py` | Punto donde se inyectarían las respuestas humanas recibidas por webhook |
| Dedup por hash (imágenes) | Mismo patrón aplicable a dedup de eventos webhook de Intercom |

---

## Preguntas abiertas antes de decidir

1. ¿El objetivo es reemplazar nuestro backend de escalación humana por el inbox completo de Intercom con respuestas en vivo hacia el widget (Opción A, Custom Channel), o solo usar Intercom como sistema de tickets/reporting al escalar (Opción B, Conversations API estándar)?
2. ¿Nuestro plan actual de Intercom permite acceso a Custom Channel / Fin over API, o hay que negociarlo con su equipo de cuenta?
3. Si el valor principal que buscábamos era el builder visual de flujos con botones — ese valor **no se obtiene** vía Custom Channel; seguiríamos manteniendo `present_choice` como está.

## Fuentes

- [Channels explained | Intercom Help](https://www.intercom.com/help/en/articles/9955432-channels-explained)
- [Custom Channel Events | Intercom Developer Platform](https://developers.intercom.com/docs/references/rest-api/api.intercom.io/custom-channel-events)
- [Hand over Fin AI Agent conversations to another support tool | Intercom Help](https://www.intercom.com/help/en/articles/7995955-hand-over-fin-ai-agent-conversations-to-another-support-tool)
- [Omnichannel support for Workflows | Intercom Help](https://www.intercom.com/help/en/articles/6884847-omnichannel-support-for-workflows)
- [Workflows FAQs | Intercom Help](https://www.intercom.com/help/en/articles/8826728-workflows-faqs)
- [Using WhatsApp as a channel | Intercom Help](https://www.intercom.com/help/en/articles/9881312-using-whatsapp-as-a-channel)
- [Messenger FAQs | Intercom Help](https://www.intercom.com/help/en/articles/6612597-messenger-faqs)
- [Ultimate guide to Intercom pricing plans 2026 – Freshworks](https://www.freshworks.com/explore-cx/intercom-pricing/)
