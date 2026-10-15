---
name: create-order
description: Usar cuando el aliado pregunta cómo crear o cobrar una orden o venta con Cashea (QR, Link, Sin Conexión), o tiene un problema al crearla — monto mínimo, caja no configurada, orden pendiente, el comprador no puede, código del comprador, factura.
---

# Crear una orden

Any role can create orders: **"Crear orden"** in Órdenes. Which ways appear
depends on the store's channels: an in-store business gets **Cashea QR** and
**Cashea Sin Conexión**; one that sells remotely gets **Cashea Link**. Online
and Checkout Web orders are not created in the portal (they come from the app
or the store's web integration). Admins with several stores pick the sucursal
first. QR and Sin Conexión then ask for the caja (only cajas with a QR
assigned are listed); Link needs no caja.

## Cashea QR (buyer in store, with internet)
1. "Monto": total amount of the order.
2. "Escaneo QR": the buyer scans the caja's QR with the Cashea app, chooses
   their plan and confirms. Until they confirm: "Tu comprador debe confirmar
   la orden en la app". If the buyer can't get in, they contact support from
   their app.
3. "Factura": the invoice number from their billing system.
4. "Pago inicial": pick how the buyer paid the down payment, review, and
   **"Confirmar orden"**. Skipped when the buyer has 0% down payment.

## Cashea Sin Conexión (buyer without internet)
Amount → buyer's cédula → **6-digit security code shown in the buyer's Cashea
app** → invoice → down payment method. Wrong code: "Código de seguridad
incorrecto."

## Cashea Link (remote sale)
Amount + buyer's cédula (numbers only, at least 6) → review → **"Confirmar
orden"** → **"Copiar link"** and send it to the buyer. Needs no caja.

## When it doesn't go through
- "El monto es menor a $X" → below the store's minimum; the portal shows it.
- "Tienes una orden pendiente" (QR) → the last order on that caja is still
  Pendiente: open it ("Ir al detalle") and finish or cancel it first.
- "Tu caja aún no está configurada" / "Aún no tienes disponible esta opción"
  / "Tu tienda no tiene acceso en este momento" → only Cashea can
  fix it: send them to Cashea support.
- "Tu comprador no tiene cuenta en Cashea" → the buyer must register in the
  app. "Tu comprador no tiene la cuenta activa" → they must finish verifying
  their account in the app. "Tu comprador tiene pagos pendientes" → they must
  catch up on their installments; they can contact Cashea support. Don't
  speculate about the buyer's account beyond that.
- "Encontramos una orden similar" → same buyer and amount on that caja in the
  last hour. If it's the same sale, cancel the new one and keep the existing
  one; if not, continue.
- Invoice: no spaces, under 50 characters, and each number only once ("Este
  número de factura ya fue registrado").

To see the result, search_orders finds the new order.
