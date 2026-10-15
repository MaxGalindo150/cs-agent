---
name: daily-closing
description: Usar cuando el aliado pregunta por el cierre de caja — qué es, cómo hacerlo, el código de confirmación, si ya se hizo hoy, el historial de cierres o cuánto lleva vendido en el día.
---

# Cierre de caja

The end-of-day summary of a store: orders of the day, **total facturado** and
**total financiado por Cashea**, also per caja. Any employee can do it, from
**"Cierre de caja"** in the menu. get_daily_closing shows today's numbers so
far and when the last cierre was — use it before answering about their
store's day.

## How
1. "Cierre de caja" → check "Sucursal", "Órdenes del día", "Total
   facturado", "Total financiado por Cashea" ("Ver cajas" for the per-caja
   breakdown).
2. "Código de confirmación": a 4-digit number, required.
3. **"Guardar"** → "Cierre de caja realizado".

That screen is always today's cierre. For yesterday's, the portal says: try
to create a new order, and it will ask for it if it wasn't done.

## Errors
- "Código inválido." → the confirmation code is wrong.
- "Error al realizar el cierre de caja." / "Datos inválidos para realizar el
  cierre." → try again; if it keeps failing, send them to Cashea support.
- "En mantenimiento" on the screen → the cierre isn't available for their
  store right now; nothing they can do in the portal.

Where the 4-digit confirmation code comes from and how to recover it is not
known here (to confirm). If they don't have it, they should ask their
store's admin; if no one has it, send them to Cashea support.

## Why it matters
- After the cierre, managers and cashiers can no longer cancel the orders
  created before it — only an admin can.
- "Historial" (on the same screen) lists past cierres with their facturado
  and financiado.

## Don't
- Don't say you'll do the cierre — you can only read it.
- get_daily_closing covers only the store the employee is assigned to; for
  another store, they check it in the portal.
