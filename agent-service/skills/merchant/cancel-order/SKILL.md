---
name: cancel-order
description: Usar cuando el aliado quiere cancelar una orden, pregunta por qué no puede cancelarla, qué es el código de seguridad para cancelar, o quiere reactivar o restaurar una orden cancelada.
---

# Cancelar o reactivar una orden

Look the order up first (search_orders → get_order_detail) to check its status
and creation time. The caller's role is in your context.

## Who can cancel, and when
- Orders in **Pagada** or **Cancelada** can't be cancelled. Only Abierta,
  Pendiente and En progreso can.
- **OWNER**: any time, no security code.
- **ADMIN**: any time, but must enter the security code.
- **MANAGER and CASHIER**: each order has a cancellation window that opens
  when it's created and closes at whichever comes first: 24 hours later, or
  the store's next cierre de caja. After that only an admin can cancel it
  ("Después del cierre de caja, solo un administrador podrá cancelarla.").

To check it for a manager or cashier: created_at less than 24 hours ago,
AND created_at later than get_daily_closing's last_closing_at (no cierre has
happened since the order was created). If the last cierre came after the
order, its window is closed. get_daily_closing only covers their own store;
for an order of another store, state the rule instead of confirming.

Answer for the role in your context. If they describe themselves with a
different role, explain the rule for the role they ask about, and mention
which role their own user has.

## How (they do it; you can't cancel)
1. Órdenes → open the order → **"Cancelar orden"**.
2. "Elige un motivo de cancelación". With "Otro motivo" they type the reason
   (70 characters max).
3. "Ingresa el código de seguridad" (4 characters; OWNER doesn't see it).
4. **"Confirmar"** → "Cancelamos la orden".

## Errors they may see
- "El código de seguridad es incorrecto. Corrígelo para continuar." → wrong
  code; re-enter it.
- "No tienes permisos para cancelar esta orden" / "No tienes permisos para
  cancelar la orden" → their role or the time window doesn't allow it; an
  admin must do it.
- "Cancelación no disponible por tiempo o cierre de caja." → same.
- The cancel button is missing → the order is Pagada or already Cancelada.

The security code: where it comes from and how to recover it is not known
here (to confirm). If they don't have it, they should ask their store's admin;
if no one has it, send them to Cashea support.

## Reactivar una orden cancelada
Only ADMIN or OWNER, and only for cancelled orders that had a payment plan:
order detail → **"Reactivar orden"** ("La orden volverá a estar activa con las
mismas condiciones."). If it fails ("No podemos restaurar esta orden"):
- "El plazo de pago venció" → it can't be restored; create a new order.
- "Tu comprador no tiene crédito disponible" → retry when the buyer has
  credit again.
- "Tu comprador tiene pagos pendientes" / "no tiene línea de compra
  disponible" → the buyer must catch up on their installments first.

## Don't
- Don't promise what cancelling does to the buyer's down payment, refund or
  credit line — that isn't known here. If it matters, send them to Cashea
  support.
- Don't offer "Devolver monto" (partial return): it only exists for a few
  pilot merchants.
