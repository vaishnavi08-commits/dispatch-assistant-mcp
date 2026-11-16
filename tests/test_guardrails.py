"""Guardrail tests: the rules must hold no matter what the model asks for."""
import os, tempfile, pytest

os.environ["DISPATCH_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
from dispatch_mcp import db, tools  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    db.seed()


def status(oid):
    return db.connect().execute("SELECT status, shopper_id FROM orders WHERE id=?", (oid,)).fetchone()


def test_at_risk_sorted_most_late_first():
    r = tools.get_at_risk_orders()
    lates = [o["minutes_late"] for o in r["orders"]]
    assert lates == sorted(lates, reverse=True) and all(l > 0 for l in lates)


def test_reassign_never_executes_without_approval():
    r = tools.reassign_order("O1009", "S2", "late")
    assert r["status"] == "pending_approval"
    assert status("O1009")["shopper_id"] is None


def test_reassign_refuses_other_store_busy_and_delivering():
    assert "refused" in tools.reassign_order("O1015", "S4", "x")   # other store
    assert "refused" in tools.reassign_order("O1005", "S7", "x")   # busy shopper
    assert "refused" in tools.reassign_order("O1024", "S2", "x")   # already delivering


def test_fallback_refused_when_on_track_or_shoppers_free():
    assert "refused" in tools.trigger_fallback_delivery("O1013", "x")  # on track
    assert "refused" in tools.trigger_fallback_delivery("O1009", "x")  # Lincoln Park has free shoppers


def test_fallback_low_value_executes_high_value_needs_approval():
    assert tools.trigger_fallback_delivery("O1004", "late")["status"] == "sent_to_fallback_partner"
    assert tools.trigger_fallback_delivery("O1001", "late")["status"] == "pending_approval"
    assert status("O1001")["status"] == "queued"


def test_every_action_is_audited():
    tools.escalate_to_dispatcher("O1021", "angry customer", "high")
    tools.reassign_order("O1009", "S2", "late")
    n = db.connect().execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    assert n == 2
