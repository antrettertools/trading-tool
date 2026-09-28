// Order fill-matching rules. Direct port of ../trading/orders.py.
import type { Order } from "./types";

export function checkFill(order: Order, price: number): number | null {
  if (order.status !== "open") return null;
  switch (order.type) {
    case "market":
      return price;
    case "limit":
      if (order.side === "buy" && price <= order.limitPrice!) return order.limitPrice!;
      if (order.side === "sell" && price >= order.limitPrice!) return order.limitPrice!;
      return null;
    case "stop":
      if (order.side === "buy" && price >= order.stopPrice!) return price;
      if (order.side === "sell" && price <= order.stopPrice!) return price;
      return null;
    case "stop_limit": {
      if (!order.stopTriggered) {
        if (
          (order.side === "buy" && price >= order.stopPrice!) ||
          (order.side === "sell" && price <= order.stopPrice!)
        ) {
          order.stopTriggered = true;
        }
      }
      if (order.stopTriggered) {
        if (order.side === "buy" && price <= order.limitPrice!) return order.limitPrice!;
        if (order.side === "sell" && price >= order.limitPrice!) return order.limitPrice!;
      }
      return null;
    }
    default:
      return null;
  }
}

export function describeOrder(o: Order): string {
  const bits = [o.side.toUpperCase(), o.type.replace("_", "-").toUpperCase(), `x${o.qty}`];
  if (o.limitPrice) bits.push(`@${o.limitPrice.toFixed(2)}`);
  if (o.stopPrice) bits.push(`stop ${o.stopPrice.toFixed(2)}`);
  return bits.join(" ");
}
