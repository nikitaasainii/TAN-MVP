"""Sprint 4 stretch story: feedback rounds per order and time spent in each stage.

Pure functions (no database access) so they are easy to test. app/main.py feeds them the data.
"""
from datetime import datetime

from .data import STAGES

# db.now_text() writes seconds; create_order() stores minutes only. Accept both.
TIME_FORMATS = ("%d %b %Y, %I:%M:%S %p", "%d %b %Y, %I:%M %p")


def parse_time(text):
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except (ValueError, TypeError):
            continue
    return None


def format_duration(seconds) -> str:
    """45 -> '45 s', 190 -> '3 min 10 s', 3720 -> '1 h 2 min'. None -> '-'."""
    if seconds is None:
        return "-"
    s = int(round(seconds))
    if s < 60:
        return f"{s} s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m} min {s} s" if s else f"{m} min"
    h, m = divmod(m, 60)
    return f"{h} h {m} min" if m else f"{h} h"


def time_in_stages(history: list, now: datetime) -> dict:
    """{stage: {"seconds": float or None, "open": bool}} for the stages an order has reached.

    A stage lasts until the next history entry. The stage the order is in now is "open" (time so far).
    Delivered is skipped: once delivered nothing is waiting.
    """
    out = {}
    for i, h in enumerate(history):
        start = parse_time(h["changed_at"])
        if i + 1 < len(history):
            end, is_open = parse_time(history[i + 1]["changed_at"]), False
        elif h["stage"] < len(STAGES) - 1:
            end, is_open = now, True
        else:
            continue
        seconds = max((end - start).total_seconds(), 0) if start and end else None
        out[h["stage"]] = {"seconds": seconds, "open": is_open}
    return out


def build_stats(orders: list, histories: dict, feedbacks: dict, now: datetime | None = None) -> dict:
    """Numbers for the staff stats page.

    orders: rows from db.list_orders(); histories / feedbacks: {order_no: list} from the db.
    """
    now = now or datetime.now()
    rows, finished = [], {i: [] for i in range(len(STAGES))}
    total_rounds = total_approvals = reworked = 0

    for o in orders:
        fb = feedbacks.get(o["order_no"], [])
        rounds = sum(1 for f in fb if f["kind"] == "changes_requested")
        approvals = sum(1 for f in fb if f["kind"] == "approved")
        total_rounds += rounds
        total_approvals += approvals
        reworked += 1 if rounds else 0

        times = time_in_stages(histories.get(o["order_no"], []), now)
        cells = []
        for i in range(len(STAGES)):
            t = times.get(i)
            if t is None:
                cells.append({"text": "-", "open": False})
                continue
            cells.append({"text": format_duration(t["seconds"]), "open": t["open"]})
            if not t["open"] and t["seconds"] is not None:
                finished[i].append(t["seconds"])
        rows.append({"order_no": o["order_no"], "product_name": o["product_name"],
                     "stage_name": STAGES[o["stage"]], "rounds": rounds, "approvals": approvals,
                     "cells": cells})

    averages = [format_duration(sum(v) / len(v)) if v else "-" for _, v in sorted(finished.items())]
    n = len(orders)
    return {
        "rows": rows,
        "averages": averages,
        "summary": {"orders": n, "rounds": total_rounds, "approvals": total_approvals,
                    "reworked": reworked, "avg_rounds": f"{total_rounds / n:.1f}" if n else "0.0"},
    }
