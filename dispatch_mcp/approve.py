"""Human approval CLI. List: python -m dispatch_mcp.approve   Approve: python -m dispatch_mcp.approve 3   Reject: ... 3 --reject"""
import sys
from .db import connect
from .tools import _audit


def main():
    con = connect()
    args = sys.argv[1:]
    if not args:
        for r in con.execute("SELECT * FROM pending_actions WHERE status='pending_approval'"):
            print(dict(r))
        return
    aid, reject = int(args[0]), "--reject" in args
    a = con.execute("SELECT * FROM pending_actions WHERE id=?", (aid,)).fetchone()
    if not a or a["status"] != "pending_approval":
        print("No pending action with that id"); return
    if reject:
        con.execute("UPDATE pending_actions SET status='rejected' WHERE id=?", (aid,))
    elif a["action"] == "reassign":
        con.execute("UPDATE orders SET shopper_id=? WHERE id=?", (a["shopper_id"], a["order_id"]))
        con.execute("UPDATE shoppers SET status='busy' WHERE id=?", (a["shopper_id"],))
        con.execute("UPDATE pending_actions SET status='approved' WHERE id=?", (aid,))
    else:
        con.execute("UPDATE orders SET status='fallback' WHERE id=?", (a["order_id"],))
        con.execute("UPDATE pending_actions SET status='approved' WHERE id=?", (aid,))
    _audit(con, "dispatcher", "reject" if reject else "approve", a["order_id"], {"approval_id": aid})
    con.commit()
    print("Rejected" if reject else "Approved", aid)


if __name__ == "__main__":
    main()
