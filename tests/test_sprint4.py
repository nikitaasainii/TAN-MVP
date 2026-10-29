"""Sprint 4 checks: approve at a checkpoint, request changes, staff feedback log, stats view."""
import base64
import os
import sqlite3
import tempfile
from datetime import datetime

_tmp = tempfile.mkdtemp()
os.environ["TAN_DB"] = os.path.join(_tmp, "test4.db")
os.environ["TAN_UPLOADS"] = os.path.join(_tmp, "uploads")

from fastapi.testclient import TestClient  # noqa: E402

from app import db, stats  # noqa: E402
from app.data import CHECKPOINTS, STAGES  # noqa: E402
from app.main import UPLOAD_DIR, app  # noqa: E402

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
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


def at_stage(c, stage: int) -> str:
    """Place an order and move it (approving checkpoints on the way) to the given stage."""
    no = place_order(c)
    while db.get_order(no)["stage"] < stage:
        c.post(f"/track/{no}/approve")
        c.post(f"/staff/orders/{no}/advance")
    return no


def test_checkpoints_are_sketch_sample_and_trial_piece():
    assert {STAGES[i] for i in CHECKPOINTS} == {"Sketch Shared", "Fabric Sample Review", "Trial Piece Review"}


def test_story1_approve_is_saved_and_lets_the_stage_advance():
    with TestClient(app) as c:
        no = at_stage(c, 1)                                   # Sketch Shared
        html = c.get(f"/track/{no}").text
        assert "Please review your sketch" in html and f"/track/{no}/approve" in html
        r = c.post(f"/track/{no}/approve", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"].startswith(f"/track/{no}")
        assert db.get_order(no)["review"] == "approved"
        assert "You approved the sketch" in c.get(f"/track/{no}").text
        assert "Approved" in c.get(f"/staff/orders/{no}").text
        c.post(f"/staff/orders/{no}/advance")
        assert db.get_order(no)["stage"] == 2
        assert db.get_order(no)["review"] == "awaiting"      # the next checkpoint starts fresh


def test_staff_cannot_advance_a_checkpoint_until_customer_approves():
    with TestClient(app) as c:
        no = at_stage(c, 2)
        c.post(f"/staff/orders/{no}/advance")
        assert db.get_order(no)["stage"] == 2                 # blocked
        assert db.advance_stage(no) is None
        staff = c.get(f"/staff/orders/{no}").text
        assert "Waiting" in c.get("/staff/orders").text or "must approve" in staff
        assert " disabled" in staff
        c.post(f"/track/{no}/approve")
        c.post(f"/staff/orders/{no}/advance")
        assert db.get_order(no)["stage"] == 3


def test_approve_does_nothing_outside_checkpoints_or_twice():
    with TestClient(app) as c:
        no = place_order(c)                                   # Idea Received: not a checkpoint
        assert "Approve" not in c.get(f"/track/{no}").text
        c.post(f"/track/{no}/approve")
        assert db.feedback_log(no) == []
        c.post(f"/staff/orders/{no}/advance")                 # free to advance, no approval needed
        assert db.get_order(no)["stage"] == 1
        c.post(f"/track/{no}/approve")
        c.post(f"/track/{no}/approve")                        # double click or refresh
        assert [f["kind"] for f in db.feedback_log(no)] == ["approved"]
        assert c.post("/track/ORD-9999/approve", follow_redirects=True).status_code == 404


def test_final_piece_and_delivered_have_no_approval_step():
    with TestClient(app) as c:
        no = at_stage(c, 4)
        html = c.get(f"/track/{no}").text
        assert 'id="checkpoint"' not in html
        c.post(f"/staff/orders/{no}/advance")                 # Final Piece -> Delivered with no approval
        assert db.get_order(no)["stage"] == 5


def test_story2_request_changes_saves_comment_and_marks_order():
    with TestClient(app) as c:
        no = at_stage(c, 3)                                   # Trial Piece Review
        r = c.post(f"/track/{no}/changes", data={"comment": "  Please shorten the hem  "}, follow_redirects=False)
        assert r.status_code == 303
        order = db.get_order(no)
        assert order["review"] == "changes_requested" and order["stage"] == 3
        fb = db.feedback_log(no)[-1]
        assert fb["kind"] == "changes_requested" and fb["comment"] == "Please shorten the hem"
        page = c.get(f"/track/{no}").text
        assert "We have your change request" in page and "Please shorten the hem" in page
        assert 'action="/track/' + no + '/approve"' not in page   # cannot approve while changes are pending
        c.post(f"/staff/orders/{no}/advance")
        assert db.get_order(no)["stage"] == 3                 # still blocked
        assert "Changes requested" in c.get("/staff/orders").text


def test_request_changes_needs_a_comment_and_a_sensible_length():
    with TestClient(app) as c:
        no = at_stage(c, 1)
        for bad in ["", "   "]:
            r = c.post(f"/track/{no}/changes", data={"comment": bad})
            assert r.status_code == 400 and "Please tell us what you would like changed." in r.text
        r = c.post(f"/track/{no}/changes", data={"comment": "x" * 501})
        assert r.status_code == 400 and "up to 500 characters" in r.text
        assert db.feedback_log(no) == [] and db.get_order(no)["review"] == "awaiting"
        assert c.post("/track/ORD-9999/changes", data={"comment": "hi"}, follow_redirects=True).status_code == 404


def test_full_revision_loop_then_approve_then_advance():
    with TestClient(app) as c:
        no = at_stage(c, 2)
        c.post(f"/track/{no}/changes", data={"comment": "Swatch is too dark"})
        c.post(f"/track/{no}/approve")                        # ignored: changes are pending
        assert db.get_order(no)["review"] == "changes_requested"
        r = c.post(f"/staff/orders/{no}/revision", data={"back": "detail"}, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == f"/staff/orders/{no}"
        assert db.get_order(no)["review"] == "awaiting"
        c.post(f"/track/{no}/approve")
        c.post(f"/staff/orders/{no}/advance")
        assert db.get_order(no)["stage"] == 3
        kinds = [f["kind"] for f in db.feedback_log(no) if f["stage"] == 2]
        assert kinds == ["changes_requested", "revision_shared", "approved"]
        # 'revision shared' only works after a change request
        assert db.add_feedback(no, "revision_shared") is False
        assert c.post("/staff/orders/ORD-9999/revision", follow_redirects=False).status_code == 303


def test_story3_staff_feedback_log_shows_time_type_and_comment_newest_first():
    with TestClient(app) as c:
        no = at_stage(c, 1)
        c.post(f"/track/{no}/changes", data={"comment": "First <b>note</b>"})
        c.post(f"/staff/orders/{no}/revision")
        c.post(f"/track/{no}/approve")
        page = c.get(f"/staff/orders/{no}").text
        assert 'id="feedback-log"' in page
        assert page.index("Approved") < page.index("Revised version shared") < page.index("Changes requested")
        assert "First &lt;b&gt;note&lt;/b&gt;" in page and "<b>note</b>" not in page   # comment is escaped
        assert all(f["created_at"] for f in db.feedback_log(no))
        empty = c.get(f"/staff/orders/{place_order(c)}").text
        assert "No feedback yet" in empty


def test_customer_page_never_shows_contact_details_with_feedback():
    with TestClient(app) as c:
        no = at_stage(c, 1)
        c.post(f"/track/{no}/changes", data={"comment": "Make it longer"})
        html = c.get(f"/track/{no}").text
        for private in ["asha@example.com", "9876543210", "12 Park Street", "Asha Rao"]:
            assert private not in html


# ---------- stretch: stats ----------

def test_format_duration():
    assert stats.format_duration(None) == "-"
    assert stats.format_duration(0) == "0 s"
    assert stats.format_duration(45) == "45 s"
    assert stats.format_duration(190) == "3 min 10 s"
    assert stats.format_duration(120) == "2 min"
    assert stats.format_duration(3720) == "1 h 2 min"
    assert stats.format_duration(7200) == "2 h"


def test_time_in_stages_uses_gaps_between_history_entries():
    hist = [
        {"stage": 0, "changed_at": "27 Oct 2026, 10:00:00 AM"},
        {"stage": 1, "changed_at": "27 Oct 2026, 10:01:30 AM"},
        {"stage": 2, "changed_at": "27 Oct 2026, 10:05:30 AM"},
    ]
    t = stats.time_in_stages(hist, now=datetime(2026, 10, 27, 10, 10, 30))
    assert t[0] == {"seconds": 90, "open": False}
    assert t[1] == {"seconds": 240, "open": False}
    assert t[2] == {"seconds": 300, "open": True}             # current stage: time so far
    done = hist + [{"stage": 5, "changed_at": "27 Oct 2026, 10:06:30 AM"}]
    assert 5 not in stats.time_in_stages(done, now=datetime(2026, 10, 28))  # Delivered has no duration
    # orders from Sprint 1 and 2 store created_at without seconds
    assert stats.parse_time("25 Oct 2026, 10:00 AM") == datetime(2026, 10, 25, 10, 0)


def test_build_stats_counts_rounds_and_averages_finished_stages():
    orders = [{"order_no": "A", "product_name": "P", "stage": 2}, {"order_no": "B", "product_name": "Q", "stage": 0}]
    histories = {
        "A": [{"stage": 0, "changed_at": "27 Oct 2026, 10:00:00 AM"}, {"stage": 1, "changed_at": "27 Oct 2026, 10:01:00 AM"},
              {"stage": 2, "changed_at": "27 Oct 2026, 10:04:00 AM"}],
        "B": [{"stage": 0, "changed_at": "27 Oct 2026, 10:00:00 AM"}],
    }
    feedbacks = {"A": [{"kind": "changes_requested"}, {"kind": "revision_shared"}, {"kind": "changes_requested"},
                       {"kind": "approved"}], "B": []}
    out = stats.build_stats(orders, histories, feedbacks, now=datetime(2026, 10, 27, 10, 10, 0))
    a, b = out["rows"]
    assert (a["rounds"], a["approvals"]) == (2, 1) and (b["rounds"], b["approvals"]) == (0, 0)
    assert a["cells"][0]["text"] == "1 min" and a["cells"][1]["text"] == "3 min"
    assert a["cells"][2] == {"text": "6 min", "open": True}
    assert b["cells"][0] == {"text": "10 min", "open": True}
    assert out["averages"][0] == "1 min" and out["averages"][1] == "3 min" and out["averages"][2] == "-"
    assert out["summary"] == {"orders": 2, "rounds": 2, "approvals": 1, "reworked": 1, "avg_rounds": "1.0"}
    assert stats.build_stats([], {}, {})["summary"]["avg_rounds"] == "0.0"


def test_story4_stats_page_shows_rounds_and_time_per_stage():
    with TestClient(app) as c:
        no = at_stage(c, 1)
        c.post(f"/track/{no}/changes", data={"comment": "Another look please"})
        r = c.get("/staff/stats")
        assert r.status_code == 200
        body = r.text
        assert "Feedback rounds" in body and "Time in Sketch Shared" in body and "Average (finished stages only)" in body
        row = body[body.index(no):]
        row = row[:row.index("</tr>")]
        assert "Sketch Shared" in row and "so far" in row     # the order is still in Sketch Shared
        assert "/staff/stats" in c.get("/staff/orders").text  # linked from the staff list


def test_database_from_sprint3_gets_the_feedback_table(tmp_path, monkeypatch):
    old = tmp_path / "s3.db"
    conn = sqlite3.connect(old)
    conn.executescript(db.SCHEMA.split("CREATE TABLE IF NOT EXISTS feedback")[0])   # Sprint 3 had no feedback table
    conn.execute("""INSERT INTO orders (order_no, product_slug, product_name, fabric, colour, size, total,
        customer_name, email, phone, address, city, state, postcode, created_at, stage)
        VALUES ('ORD-1001','petal-set','Petal Set','Satin','Mint','M',3499,'A B','a@b.co','9999999999','x','y','z','201310','25 Oct 2026, 10:00 AM', 1)""")
    conn.commit()
    conn.close()
    monkeypatch.setattr(db, "DB_PATH", old)
    db.init_db()
    assert db.get_order("ORD-1001")["review"] == "awaiting"
    assert db.add_feedback("ORD-1001", "approved") is True
    assert db.advance_stage("ORD-1001") == 2


# ---------- staff upload an image at a stage ----------

def upload(c, no, data=PNG, name="sketch.png", ctype="image/png", note=""):
    files = {"photo": (name, data, ctype)} if data is not None else {}
    return c.post(f"/staff/orders/{no}/image", files=files, data={"note": note}, follow_redirects=False)


def test_staff_page_has_an_upload_form():
    with TestClient(app) as c:
        no = at_stage(c, 1)
        page = c.get(f"/staff/orders/{no}").text
        assert f'action="/staff/orders/{no}/image"' in page and 'enctype="multipart/form-data"' in page
        assert "Share an image with the customer" in page and "No images shared yet" in page
        assert "Upload image" in c.get("/staff/orders").text


def test_uploaded_image_is_saved_and_shown_next_to_the_approve_button():
    with TestClient(app) as c:
        no = at_stage(c, 1)
        r = upload(c, no, note="Sketch v1 <b>front</b>")
        assert r.status_code == 303 and r.headers["location"].startswith(f"/staff/orders/{no}")
        imgs = db.stage_images(no)
        assert len(imgs) == 1 and imgs[0]["stage_name"] == "Sketch Shared" and imgs[0]["note"] == "Sketch v1 <b>front</b>"
        assert (UPLOAD_DIR / imgs[0]["filename"]).read_bytes() == PNG
        page = c.get(f"/track/{no}").text
        panel = page[page.index('id="checkpoint"'):page.index("cp-actions")]
        assert f'/uploads/{imgs[0]["filename"]}' in panel          # image sits inside the approval panel
        assert "Sketch v1 &lt;b&gt;front&lt;/b&gt;" in page and "<b>front</b>" not in page
        assert "has not attached an image" not in page
        assert f'/uploads/{imgs[0]["filename"]}' in c.get(f"/staff/orders/{no}").text
        assert c.get(f'/uploads/{imgs[0]["filename"]}').status_code == 200


def test_customer_sees_a_note_when_no_image_was_shared_but_can_still_respond():
    with TestClient(app) as c:
        no = at_stage(c, 1)
        assert "has not attached an image" in c.get(f"/track/{no}").text
        c.post(f"/track/{no}/approve")
        assert db.get_order(no)["review"] == "approved"            # image is optional


def test_images_belong_to_the_stage_they_were_uploaded_at():
    with TestClient(app) as c:
        no = at_stage(c, 1)
        upload(c, no, note="the sketch")
        c.post(f"/track/{no}/approve")
        c.post(f"/staff/orders/{no}/advance")                      # now Fabric Sample Review
        upload(c, no, note="the swatch")
        imgs = db.stage_images(no)
        assert [i["stage_name"] for i in imgs] == ["Fabric Sample Review", "Sketch Shared"]   # newest first
        page = c.get(f"/track/{no}").text
        panel = page[page.index('id="checkpoint"'):page.index("cp-actions")]
        assert "the swatch" in panel and "the sketch" not in panel
        assert "Images from TAN" in page and page.index("the swatch") < page.index("the sketch")
        assert page.count("the swatch") == 1                       # not repeated in the gallery


def test_revised_image_replaces_the_one_shown_in_the_approval_panel():
    with TestClient(app) as c:
        no = at_stage(c, 1)
        upload(c, no, note="first version")
        c.post(f"/track/{no}/changes", data={"comment": "lower neckline"})
        upload(c, no, note="second version")
        c.post(f"/staff/orders/{no}/revision")
        page = c.get(f"/track/{no}").text
        panel = page[page.index('id="checkpoint"'):page.index("cp-actions")]
        assert "second version" in panel and "first version" not in panel
        assert "first version" in page                              # still visible in the gallery


def test_bad_uploads_are_rejected_with_a_message_and_nothing_is_saved():
    with TestClient(app) as c:
        no = at_stage(c, 1)
        cases = [
            (dict(data=None), "Please choose an image to upload."),
            (dict(data=b"not an image", name="a.txt", ctype="text/plain"), "Please upload a JPG, PNG or WEBP image."),
            (dict(data=b"", name="a.png", ctype="image/png"), "That file is empty."),
            (dict(data=b"x" * (5 * 1024 * 1024 + 1)), "smaller than 5 MB"),
            (dict(note="n" * 201), "up to 200 characters"),
        ]
        before = set(os.listdir(UPLOAD_DIR))
        for kwargs, message in cases:
            r = upload(c, no, **kwargs)
            assert r.status_code == 400 and message in r.text, message
        assert db.stage_images(no) == []
        assert set(os.listdir(UPLOAD_DIR)) == before               # no stray files left behind
        assert upload(c, "ORD-9999").status_code == 303            # unknown order goes back to the list


def test_database_from_before_images_gets_the_table(tmp_path, monkeypatch):
    old = tmp_path / "noimg.db"
    conn = sqlite3.connect(old)
    conn.executescript(db.SCHEMA.split("CREATE TABLE IF NOT EXISTS stage_images")[0])
    conn.execute("""INSERT INTO orders (order_no, product_slug, product_name, fabric, colour, size, total,
        customer_name, email, phone, address, city, state, postcode, created_at, stage)
        VALUES ('ORD-1001','petal-set','Petal Set','Satin','Mint','M',3499,'A B','a@b.co','9999999999','x','y','z','201310','25 Oct 2026, 10:00 AM', 1)""")
    conn.commit()
    conn.close()
    monkeypatch.setattr(db, "DB_PATH", old)
    assert db.add_stage_image("ORD-1001", "abc.png", "hi") is True
    assert db.stage_images("ORD-1001")[0]["stage_name"] == "Sketch Shared"
