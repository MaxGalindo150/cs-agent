"use client";

import { ChevronRight } from "lucide-react";
import { useState } from "react";

import type { OrderCard } from "@/lib/chat/types";
import { cn } from "@/lib/utils";

interface OrderCardsProps {
  orders: OrderCard[];
  /** Open an order in the host app (the embed's merchant portal). Cards are
   *  plain, not clickable, when omitted or when an order has no uuid. */
  onOpen?: (orderUuid: string) => void;
}

// How many cards show before "Ver N más".
const COLLAPSED = 5;

// The portal's status names → badge colours.
const STATUS_STYLES: Record<string, string> = {
  Abierta: "bg-amber-100 text-amber-800",
  Pendiente: "bg-orange-100 text-orange-800",
  "En progreso": "bg-sky-100 text-sky-800",
  Pagada: "bg-emerald-100 text-emerald-800",
  Cancelada: "bg-zinc-100 text-zinc-600",
};

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

/** Orders a tool returned, as compact cards: number and status on top, date,
 *  store and channel under it, amount on the right. */
export function OrderCards({ orders, onOpen }: OrderCardsProps) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? orders : orders.slice(0, COLLAPSED);
  const hidden = orders.length - visible.length;

  return (
    <div className="my-[var(--chat-block-gap)] flex flex-col gap-2">
      {visible.map((order) => (
        <Card key={String(order.orderNumber)} order={order} onOpen={onOpen} />
      ))}
      {hidden > 0 && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="self-start rounded text-xs font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          Ver {hidden} más
        </button>
      )}
    </div>
  );
}

function Card({ order, onOpen }: { order: OrderCard; onOpen?: (uuid: string) => void }) {
  const clickable = Boolean(onOpen && order.orderUuid);
  const details = [
    order.createdAt?.replace(" (hora de Venezuela)", ""),
    order.store,
    order.channel,
  ].filter(Boolean);

  const body = (
    <>
      <div className="flex min-w-0 flex-col gap-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold tabular-nums text-foreground">
            #{order.orderNumber}
          </span>
          {order.status && (
            <span
              className={cn(
                "rounded-full px-2 py-0.5 text-[11px] font-medium",
                STATUS_STYLES[order.status] ?? "bg-secondary text-secondary-foreground",
              )}
            >
              {order.status}
            </span>
          )}
        </div>
        {details.length > 0 && (
          <span className="truncate text-xs text-muted-foreground">{details.join(" · ")}</span>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {order.amount !== undefined && (
          <span className="text-sm font-semibold tabular-nums text-foreground">
            {money.format(order.amount)}
          </span>
        )}
        {clickable && <ChevronRight className="size-4 text-muted-foreground" />}
      </div>
    </>
  );

  const className =
    "flex w-full items-center justify-between gap-3 rounded-xl border border-border bg-card px-3 py-2.5 text-left shadow-xs";

  if (!clickable) return <div className={className}>{body}</div>;
  return (
    <button
      type="button"
      onClick={() => order.orderUuid && onOpen?.(order.orderUuid)}
      aria-label={`Abrir la orden ${order.orderNumber} en el portal`}
      className={cn(
        className,
        "transition-colors duration-150 hover:border-ring hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
      )}
    >
      {body}
    </button>
  );
}
