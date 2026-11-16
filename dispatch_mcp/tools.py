"""Dispatch tools. Plain Python functions so the MCP server and the eval runner share one implementation."""
import json
from datetime import datetime, timedelta
from .db import connect, SIM_NOW, STORES

DRIVE_MIN = 20          # average drive time to customer
QUEUE_WAIT_MIN = 15     # wait before an unassigned order is picked up
HIGH_RISK_LATE_MIN = 15 # minutes late that counts as high risk
APPROVAL_VALUE_USD = 150


def _audit(con, actor, action, order_id, detail):
    con.execute("INSERT INTO audit_log (ts, actor, action, order_id, detail) VALUES (?,?,?,?,?)",
                (SIM_NOW.isoformat(timespec="minutes"), actor, action, order_id, json.dumps(detail)))


def _eta(con, o):
    """Predicted completion time for an order."""
    if o["status"] in ("delivered", "fallback"):
        return None
    if o["status"] == "delivering":
        return SIM_NOW + timedelta(minutes=DRIVE_MIN // 2)
    remaining = o["items_total"] - o["items_picked"]
    if o["shopper_id"]:
        speed = con.execute("SELECT items_per_hour FROM shoppers WHERE id=?", (o["shopper_id"],)).fetchone()[0]
        wait = 0
    else:
        speed, wait = 60, QUEUE_WAIT_MIN
    return SIM_NOW + timedelta(minutes=wait + remaining / speed * 60 + DRIVE_MIN)


def _order_view(con, o):
    eta = _eta(con, o)
    promised = datetime.fromisoformat(o["promised_by"])
    late = None if eta is None else round((eta - promised).total_seconds() / 60)
    return {
        "order_id": o["id"], "store": o["store"], "status": o["status"], "shopper_id": o["shopper_id"],
        "items_left": o["items_total"] - o["items_picked"], "value_usd": o["value_usd"],
        "promised_by": o["promised_by"], "predicted_eta": eta.isoformat(timespec="minutes") if eta else None,
        "minutes_late": late,
        "risk": None if late is None else ("high" if late >= HIGH_RISK_LATE_MIN else "medium" if late > 0 else "on_track"),
    }


def get_order(order_id: str) -> dict:
    """Get one order's status, shopper, predicted ETA and lateness risk."""
    con = connect()
    o = con.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not o:
        return {"error": f"Order {order_id} not found"}
    return _order_view(con, o)


def get_at_risk_orders(store: str | None = None) -> dict:
    """List orders predicted to miss their promised delivery time, most late first. Optionally filter by store."""
    con = connect()
    q, args = "SELECT * FROM orders", ()
    if store:
        q, args = q + " WHERE store=?", (store,)
    views = [_order_view(con, o) for o in con.execute(q, args).fetchall()]
    risky = sorted([v for v in views if v["risk"] in ("medium", "high")], key=lambda v: -v["minutes_late"])
    return {"as_of": SIM_NOW.isoformat(timespec="minutes"), "count": len(risky), "orders": risky}


def get_shopper_availability(store: str) -> dict:
    """List shoppers at a store with status and speed (items per hour).
    store must be a store name: "Lincoln Park", "Edina" or "Maple Grove" (not a shopper ID).
    Tip: get_order returns the order's store."""
    con = connect()
    rows = con.execute("SELECT * FROM shoppers WHERE store=?", (store,)).fetchall()
    if not rows:
        return {"error": f"Unknown store {store}. Valid stores: {', '.join(STORES)}"}
    return {"store": store, "shoppers": [dict(r) for r in rows],
            "available_count": sum(r["status"] == "available" for r in rows)}


def reassign_order(order_id: str, shopper_id: str, reason: str) -> dict:
    """Request moving an order to another shopper. Never executes directly: creates a pending action a human dispatcher must approve.
    Only call this when the dispatcher has asked you to act on the order (e.g. "fix it", "reassign it").
    For status questions, report what you found and suggest the action instead of requesting it."""
    con = connect()
    o = con.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    s = con.execute("SELECT * FROM shoppers WHERE id=?", (shopper_id,)).fetchone()
    if not o:
        return {"error": f"Order {order_id} not found"}
    if not s:
        return {"error": f"Shopper {shopper_id} not found"}
    if o["status"] not in ("queued", "shopping"):
        return {"refused": f"Order is {o['status']}; only queued or shopping orders can be reassigned"}
    if s["store"] != o["store"]:
        return {"refused": "Shopper works at a different store"}
    if s["status"] != "available":
        return {"refused": f"Shopper is {s['status']}"}
    cur = con.execute("INSERT INTO pending_actions (action, order_id, shopper_id, reason, status, created_at) "
                      "VALUES ('reassign',?,?,?,'pending_approval',?)",
                      (order_id, shopper_id, reason, SIM_NOW.isoformat(timespec="minutes")))
    _audit(con, "agent", "request_reassign", order_id, {"shopper_id": shopper_id, "reason": reason})
    con.commit()
    return {"status": "pending_approval", "approval_id": cur.lastrowid,
            "message": "A dispatcher must approve this before it takes effect."}


def escalate_to_dispatcher(order_id: str, reason: str, urgency: str = "normal") -> dict:
    """Hand an order to a human dispatcher with a reason. Use when unsure, when rules block an action, or for customer-sensitive cases."""
    con = connect()
    if not con.execute("SELECT 1 FROM orders WHERE id=?", (order_id,)).fetchone():
        return {"error": f"Order {order_id} not found"}
    _audit(con, "agent", "escalate", order_id, {"reason": reason, "urgency": urgency})
    con.commit()
    return {"status": "escalated", "order_id": order_id, "urgency": urgency}


def trigger_fallback_delivery(order_id: str, reason: str) -> dict:
    """Send an order to a third-party delivery partner. Allowed only if the order is at risk and no shopper at its store is available. Orders over $150 need dispatcher approval.
    Only call this when the dispatcher has asked you to act on the order. For status questions, suggest it instead."""
    con = connect()
    o = con.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not o:
        return {"error": f"Order {order_id} not found"}
    view = _order_view(con, o)
    if view["risk"] not in ("medium", "high"):
        return {"refused": "Order is not at risk; fallback not allowed"}
    avail = con.execute("SELECT COUNT(*) FROM shoppers WHERE store=? AND status='available'", (o["store"],)).fetchone()[0]
    if avail:
        return {"refused": f"{avail} shopper(s) available at {o['store']}; reassign instead"}
    if o["value_usd"] > APPROVAL_VALUE_USD:
        cur = con.execute("INSERT INTO pending_actions (action, order_id, reason, status, created_at) "
                          "VALUES ('fallback',?,?,'pending_approval',?)",
                          (order_id, reason, SIM_NOW.isoformat(timespec="minutes")))
        _audit(con, "agent", "request_fallback", order_id, {"reason": reason})
        con.commit()
        return {"status": "pending_approval", "approval_id": cur.lastrowid,
                "message": f"Order value ${o['value_usd']} is over ${APPROVAL_VALUE_USD}; dispatcher approval needed."}
    con.execute("UPDATE orders SET status='fallback' WHERE id=?", (order_id,))
    _audit(con, "agent", "fallback", order_id, {"reason": reason})
    con.commit()
    return {"status": "sent_to_fallback_partner", "order_id": order_id}


TOOLS = [get_order, get_at_risk_orders, get_shopper_availability,
         reassign_order, escalate_to_dispatcher, trigger_fallback_delivery]
