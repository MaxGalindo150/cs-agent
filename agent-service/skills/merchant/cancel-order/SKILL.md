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
- **MANAGER and CASHIER**: only if the order was created less than 24 hours
  ago AND before the store's next cierre de caja. After the cierre only an
  admin can cancel it ("Después del cierre de caja, solo un administrador
  podrá cancelarla."). Tell them to ask an admin of their store.

You can check the 24-hour part from the order's created_at. You can't see
when the store's last cierre de caja happened, so never confirm that an order
is still cancellable for them — say what you can check and that the cierre
part they'll see in the order itself (the "Cancelar orden" button is there
or not).

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
if no one has it, escalate_to_human.

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
  credit line — that isn't known here. If it matters, escalate_to_human.
- Don't offer "Devolver monto" (partial return): it only exists for a few
  pilot merchants.
