"""Sprint 3 checks: stage tracker, track by order number, staff advance stage, stage history log."""
import os
import sqlite3
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["TAN_DB"] = os.path.join(_tmp, "test3.db")
os.environ["TAN_UPLOADS"] = os.path.join(_tmp, "uploads")

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.data import STAGES  # noqa: E402
from app.main import app  # noqa: E402

GOOD = {"slug": "petal-set", "size": "M", "fabric": "Cotton Cambric", "colour": "Blush Pink", "quantity": "1"}
CONTACT = {
    "email": "asha@example.com", "first_name": "Asha", "last_name": "Rao", "address": "12 Park Street",
    "apartment": "", "city": "Noida", "state": "Uttar Pradesh", "postcode": "201310", "phone": "9876543210",
}


def place_order(c) -> str:
    c.post("/cart/add", data=GOOD)
    c.post("/checkout", data=CONTACT)
    placed = c.get("/order-placed").text
    start = placed.index("ORD-")
    return placed[start:start + 8]


def test_stages_are_the_six_agreed_ones():
    assert STAGES == ["Idea Received", "Sketch Shared", "Fabric Sample Review",
                      "Trial Piece Review", "Final Piece", "Delivered"]


def test_story1_tracker_shows_all_stages_with_current_highlighted():
    with TestClient(app) as c:
        no = place_order(c)
        html = c.get(f"/track/{no}").text
        for name in STAGES:
            assert name in html, name
        assert html.count('aria-current="step"') == 1
        assert "Current stage: <strong>Idea Received</strong>" in html
        assert html.count("tracker-step done") == 0


def test_story2_open_tracking_by_order_number():
    with TestClient(app) as c:
        no = place_order(c)
        assert c.get(f"/track/{no}").status_code == 200
        assert c.get(f"/track/{no.lower()}").status_code == 200      # lower case is fine
        r = c.get("/track", params={"order_no": no.split('-')[1]}, follow_redirects=False)  # digits only
        assert r.status_code == 303 and r.headers["location"] == f"/track/{no}"
        assert c.get("/track").status_code == 200                    # empty lookup form
        bad = c.get("/track/ORD-9999")
        assert bad.status_code == 404 and "could not find that order number" in bad.text
        assert no not in bad.text


def test_tracking_page_does_not_leak_customer_contact_details():
    with TestClient(app) as c:
        html = c.get(f"/track/{place_order(c)}").text
        for private in ["asha@example.com", "9876543210", "12 Park Street", "Asha Rao"]:
            assert private not in html


def test_story3_staff_advance_updates_customer_tracker():
    with TestClient(app) as c:
        no = place_order(c)
        r = c.post(f"/staff/orders/{no}/advance", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/staff/orders"
        html = c.get(f"/track/{no}").text
        assert "Current stage: <strong>Sketch Shared</strong>" in html
        assert html.count("tracker-step done") == 1 and html.count('aria-current="step"') == 1
        staff = c.get("/staff/orders").text
        assert "Advance to Fabric Sample Review" in staff


def test_advance_cannot_go_past_delivered():
    with TestClient(app) as c:
        no = place_order(c)
        for _ in range(10):
            c.post(f"/track/{no}/approve")  # Sprint 4: checkpoint stages need the customer's approval first
            c.post(f"/staff/orders/{no}/advance")
        assert db.get_order(no)["stage"] == len(STAGES) - 1
        assert len(db.stage_history(no)) == len(STAGES)          # no extra history rows
        html = c.get(f"/track/{no}").text
        assert "Your order has been delivered." in html and html.count("tracker-step done") == len(STAGES) - 1
        assert "Advance to" not in c.get(f"/staff/orders/{no}").text
        assert c.post("/staff/orders/ORD-9999/advance", follow_redirects=False).status_code == 303


def test_story4_history_log_has_time_and_order():
    with TestClient(app) as c:
        no = place_order(c)
        c.post(f"/staff/orders/{no}/advance", data={"back": "detail"})
        c.post(f"/track/{no}/approve")  # Sprint 4: Sketch Shared is a checkpoint
        c.post(f"/staff/orders/{no}/advance", data={"back": "detail"})
        hist = db.stage_history(no)
        assert [h["stage_name"] for h in hist] == STAGES[:3]
        assert all(h["changed_at"] for h in hist)
        page = c.get(f"/staff/orders/{no}")
        assert page.status_code == 200
        body = page.text
        assert body.index("Fabric Sample Review") < body.index("Sketch Shared") < body.index("Idea Received")  # newest first
        assert c.get("/staff/orders/ORD-9999").status_code == 404
        back = c.post(f"/staff/orders/{no}/advance", data={"back": "detail"}, follow_redirects=False)
        assert back.headers["location"] == f"/staff/orders/{no}"


def test_customer_links_to_tracking():
    with TestClient(app) as c:
        c.post("/cart/add", data=GOOD)
        c.post("/checkout", data=CONTACT)
        assert "Track this order" in c.get("/order-placed").text
        assert "/track" in c.get("/").text


def test_old_database_is_upgraded_without_losing_orders(tmp_path, monkeypatch):
    """A tan_mvp.db made by Sprint 1 or 2 has no stage column. init_db must add it."""
    old = tmp_path / "old.db"
    conn = sqlite3.connect(old)
    conn.execute("""CREATE TABLE orders (id INTEGER PRIMARY KEY AUTOINCREMENT, order_no TEXT UNIQUE,
        product_slug TEXT NOT NULL, product_name TEXT NOT NULL, fabric TEXT NOT NULL, colour TEXT NOT NULL,
        size TEXT NOT NULL, custom_fit INTEGER NOT NULL DEFAULT 0, custom_fit_note TEXT DEFAULT '',
        notes TEXT DEFAULT '', photo TEXT DEFAULT '', quantity INTEGER NOT NULL DEFAULT 1, total INTEGER NOT NULL,
        customer_name TEXT NOT NULL, email TEXT NOT NULL, phone TEXT NOT NULL, address TEXT NOT NULL,
        city TEXT NOT NULL, state TEXT NOT NULL, postcode TEXT NOT NULL, created_at TEXT NOT NULL)""")
    conn.execute("""INSERT INTO orders (order_no, product_slug, product_name, fabric, colour, size, total,
        customer_name, email, phone, address, city, state, postcode, created_at)
        VALUES ('ORD-1001','petal-set','Petal Set','Satin','Mint','M',3499,'A B','a@b.co','9999999999','x','y','z','201310','25 Oct 2026, 10:00 AM')""")
    conn.commit()
    conn.close()
    monkeypatch.setattr(db, "DB_PATH", old)
    db.init_db()
    db.init_db()  # running twice must be safe
    order = db.get_order("ORD-1001")
    assert order["stage"] == 0 and order["product_name"] == "Petal Set"
    hist = db.stage_history("ORD-1001")
    assert len(hist) == 1 and hist[0]["stage_name"] == "Idea Received" and hist[0]["changed_at"] == "25 Oct 2026, 10:00 AM"
    assert db.advance_stage("ORD-1001") == 1


def test_order_still_saves_if_database_file_is_deleted_while_running():
    """Regression: deleting tan_mvp.db under a running server used to give 'no such table: orders' (HTTP 500)."""
    with TestClient(app) as c:
        os.remove(db.DB_PATH)
        no = place_order(c)
        assert no.startswith("ORD-")
        assert c.get(f"/track/{no}").status_code == 200
        assert c.get("/staff/orders").status_code == 200


def test_empty_database_file_is_set_up_automatically():
    open(db.DB_PATH, "w").close()  # a 0-byte file, like a half-created database
    db.init_db()
    assert db.list_orders() == [] or isinstance(db.list_orders(), list)
