import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .data import CHECKPOINTS, FEEDBACK_LABELS, STAGES

DB_PATH = Path(os.environ.get("TAN_DB", Path(__file__).parent / "tan_mvp.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no TEXT UNIQUE,
    product_slug TEXT NOT NULL,
    product_name TEXT NOT NULL,
    fabric TEXT NOT NULL,
    colour TEXT NOT NULL,
    size TEXT NOT NULL,
    custom_fit INTEGER NOT NULL DEFAULT 0,
    custom_fit_note TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    photo TEXT DEFAULT '',
    quantity INTEGER NOT NULL DEFAULT 1,
    total INTEGER NOT NULL,
    customer_name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT NOT NULL,
    address TEXT NOT NULL,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    postcode TEXT NOT NULL,
    created_at TEXT NOT NULL,
    stage INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS stage_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no TEXT NOT NULL,
    stage INTEGER NOT NULL,
    changed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no TEXT NOT NULL,
    stage INTEGER NOT NULL,
    kind TEXT NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stage_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no TEXT NOT NULL,
    stage INTEGER NOT NULL,
    filename TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
"""

LAST_STAGE = len(STAGES) - 1

# Which review state an order must be in before each kind of feedback is accepted.
FEEDBACK_RULES = {
    "approved": "awaiting",
    "changes_requested": "awaiting",
    "revision_shared": "changes_requested",
}


def _prepare(conn):
    """Create the tables if they are missing and upgrade an older database (adds the stage column).

    Safe to run on every connection: every statement is a no-op when the database is already up to date.
    The feedback table (Sprint 4) is created here too, so a Sprint 1, 2 or 3 database upgrades itself.
    """
    conn.executescript(SCHEMA)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(orders)")}
    if "stage" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN stage INTEGER NOT NULL DEFAULT 0")
    # Older orders get a first history entry so every order has a log.
    conn.execute(
        """INSERT INTO stage_history (order_no, stage, changed_at)
           SELECT order_no, 0, created_at FROM orders
           WHERE order_no NOT IN (SELECT order_no FROM stage_history)"""
    )


@contextmanager
def connect():
    """Open the database, make sure the tables exist, commit on success and always close.

    Preparing the schema here (not only at startup) means the app keeps working if tan_mvp.db is
    deleted or replaced while the server is running, instead of failing with "no such table: orders".
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        _prepare(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def now_text() -> str:
    return datetime.now().strftime("%d %b %Y, %I:%M:%S %p")


def init_db():
    """Create or upgrade the database at startup (connect() also does this on every use)."""
    with connect():
        pass


def create_order(item: dict, contact: dict) -> str:
    """Save one customised piece as an order and return its order number."""
    now = datetime.now().strftime("%d %b %Y, %I:%M %p")
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO orders (order_no, product_slug, product_name, fabric, colour, size,
                custom_fit, custom_fit_note, notes, photo, quantity, total, customer_name, email,
                phone, address, city, state, postcode, created_at)
               VALUES ('', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item["slug"], item["name"], item["fabric"], item["colour"], item["size"],
                1 if item["custom_fit"] else 0, item["custom_fit_note"], item["notes"],
                item["photo"], item["quantity"], item["unit_price"] * item["quantity"],
                contact["customer_name"], contact["email"], contact["phone"], contact["address"],
                contact["city"], contact["state"], contact["postcode"], now,
            ),
        )
        order_no = f"ORD-{1000 + cur.lastrowid}"
        conn.execute("UPDATE orders SET order_no = ? WHERE id = ?", (order_no, cur.lastrowid))
        conn.execute("INSERT INTO stage_history (order_no, stage, changed_at) VALUES (?, 0, ?)",
                     (order_no, now_text()))
    return order_no


# ---------- review state (Sprint 4) ----------

def _review_state(conn, order_no: str, stage: int) -> str:
    """Where the customer's review of the order's current stage stands.

    "" = this stage is not a checkpoint, "awaiting" = waiting for the customer (also after staff share a
    revised version), "approved", or "changes_requested".
    """
    if stage not in CHECKPOINTS:
        return ""
    row = conn.execute(
        "SELECT kind FROM feedback WHERE order_no = ? AND stage = ? ORDER BY id DESC LIMIT 1",
        (order_no, stage),
    ).fetchone()
    if row and row["kind"] in ("approved", "changes_requested"):
        return row["kind"]
    return "awaiting"


def add_feedback(order_no: str, kind: str, comment: str = "") -> bool:
    """Record a customer response (or staff 'revision shared') for the order's current stage.

    Returns False and saves nothing if the order does not exist, the stage is not a checkpoint, or the
    response does not fit the current state (for example approving twice).
    """
    if kind not in FEEDBACK_RULES:
        raise ValueError(f"unknown feedback kind: {kind}")
    with connect() as conn:
        row = conn.execute("SELECT stage FROM orders WHERE order_no = ?", (order_no,)).fetchone()
        if not row:
            return False
        stage = row["stage"]
        if _review_state(conn, order_no, stage) != FEEDBACK_RULES[kind]:
            return False
        conn.execute(
            "INSERT INTO feedback (order_no, stage, kind, comment, created_at) VALUES (?, ?, ?, ?, ?)",
            (order_no, stage, kind, comment, now_text()),
        )
        return True


def feedback_log(order_no: str) -> list:
    """Every feedback entry for one order, oldest first."""
    with connect() as conn:
        rows = conn.execute("SELECT * FROM feedback WHERE order_no = ? ORDER BY id", (order_no,))
        return [{"stage": r["stage"], "stage_name": STAGES[r["stage"]], "kind": r["kind"],
                 "label": FEEDBACK_LABELS.get(r["kind"], r["kind"]), "comment": r["comment"],
                 "created_at": r["created_at"]} for r in rows]


# ---------- images staff share with the customer (Sprint 4) ----------

def add_stage_image(order_no: str, filename: str, note: str = "") -> bool:
    """Attach an uploaded image to the order's current stage. False if the order does not exist."""
    with connect() as conn:
        row = conn.execute("SELECT stage FROM orders WHERE order_no = ?", (order_no,)).fetchone()
        if not row:
            return False
        conn.execute(
            "INSERT INTO stage_images (order_no, stage, filename, note, created_at) VALUES (?, ?, ?, ?, ?)",
            (order_no, row["stage"], filename, note, now_text()),
        )
        return True


def stage_images(order_no: str) -> list:
    """Every image shared on one order, newest first."""
    with connect() as conn:
        rows = conn.execute("SELECT * FROM stage_images WHERE order_no = ? ORDER BY id DESC", (order_no,))
        return [{"stage": r["stage"], "stage_name": STAGES[r["stage"]], "filename": r["filename"],
                 "note": r["note"], "created_at": r["created_at"]} for r in rows]


# ---------- reading orders ----------

def list_orders():
    with connect() as conn:
        orders = [dict(r) for r in conn.execute("SELECT * FROM orders ORDER BY id DESC")]
        for o in orders:
            o["review"] = _review_state(conn, o["order_no"], o["stage"])
        return orders


def get_order(order_no: str):
    with connect() as conn:
        row = conn.execute("SELECT * FROM orders WHERE order_no = ?", (order_no,)).fetchone()
        if not row:
            return None
        order = dict(row)
        order["review"] = _review_state(conn, order_no, order["stage"])
        return order


def stage_history(order_no: str) -> list:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM stage_history WHERE order_no = ? ORDER BY id", (order_no,))
        return [{"stage": r["stage"], "stage_name": STAGES[r["stage"]], "changed_at": r["changed_at"]}
                for r in rows]


def advance_stage(order_no: str):
    """Move an order forward one stage and log it. Returns the new stage, or None if it cannot move.

    It cannot move past Delivered, and (Sprint 4) at a checkpoint stage it cannot move until the
    customer has approved.
    """
    with connect() as conn:
        row = conn.execute("SELECT stage FROM orders WHERE order_no = ?", (order_no,)).fetchone()
        if not row or row["stage"] >= LAST_STAGE:
            return None
        if _review_state(conn, order_no, row["stage"]) in ("awaiting", "changes_requested"):
            return None
        new_stage = row["stage"] + 1
        conn.execute("UPDATE orders SET stage = ? WHERE order_no = ?", (new_stage, order_no))
        conn.execute("INSERT INTO stage_history (order_no, stage, changed_at) VALUES (?, ?, ?)",
                     (order_no, new_stage, now_text()))
        return new_stage
