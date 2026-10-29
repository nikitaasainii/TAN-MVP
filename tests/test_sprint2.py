"""Sprint 2 checks: fabric info cards, suitability hint, review page, edit from summary, confirm."""
import base64
import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["TAN_DB"] = os.path.join(_tmp, "test2.db")
os.environ["TAN_UPLOADS"] = os.path.join(_tmp, "uploads")

from fastapi.testclient import TestClient  # noqa: E402

from app.data import FABRICS, FABRIC_DETAILS, SUITABILITY_WARNINGS, suitability_for  # noqa: E402
from app.main import app  # noqa: E402

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
GOOD = {"slug": "petal-set", "size": "M", "fabric": "Cotton Cambric", "colour": "Blush Pink", "quantity": "1"}
CONTACT = {
    "email": "asha@example.com", "first_name": "Asha", "last_name": "Rao", "address": "12 Park Street",
    "apartment": "", "city": "Noida", "state": "Uttar Pradesh", "postcode": "201310", "phone": "9876543210",
}


def client():
    return TestClient(app)


def test_story1_every_fabric_has_info():
    for f in FABRICS:
        d = FABRIC_DETAILS[f]
        assert d["description"] and d["drape"] and d["stretch"] and d["care"], f
    with client() as c:
        html = c.get("/products/petal-set").text
        assert 'id="fabric-card"' in html and "Cotton Poplin" in html and "Dry Clean Only" in html


def test_story2_suitability_hint_pairs():
    assert len(SUITABILITY_WARNINGS) >= 2
    assert "Cotton Poplin" in suitability_for("lune-dress")
    assert "Satin" in suitability_for("bleu-stripe-muse-dress")
    assert suitability_for("lune-dress").get("Satin") is None
    with client() as c:
        assert "stiff for the flowy" in c.get("/products/lune-dress").text
        assert "stiff for the flowy" not in c.get("/products/cherie-set").text


def test_story3_review_page_shows_everything():
    with client() as c:
        assert c.get("/review", follow_redirects=False).status_code == 303  # empty cart
        c.post("/cart/add", data={**GOOD, "fabric": "Satin", "custom_fit": "on", "custom_fit_note": "Shorter skirt",
                                  "notes": "Add pockets"}, files={"photo": ("ref.png", PNG, "image/png")})
        r = c.get("/review")
        assert r.status_code == 200
        for expected in ["Petal Set", "M", "Satin", "Blush Pink", "Shorter skirt", "Add pockets", "/uploads/",
                         "Fluid and slinky", "Heads up", "Confirm and continue", "₹3,699.00"]:
            assert expected in r.text, expected


def test_story4_edit_updates_item_and_price():
    with client() as c:
        c.post("/cart/add", data=GOOD)
        page = c.get("/products/petal-set?edit=0")
        assert page.status_code == 200 and "Editing your selection" in page.text and "Save changes" in page.text
        r = c.post("/cart/update", data={"index": "0", "size": "XL", "fabric": "Linen Blend", "colour": "Mint",
                                         "custom_fit": "on", "custom_fit_note": "Longer", "notes": "n", "quantity": "2"})
        assert r.status_code == 200
        item = r.json()["cart"]["items"][0]
        assert (item["size"], item["fabric"], item["colour"], item["quantity"]) == ("XL", "Linen Blend", "Mint", 2)
        assert item["unit_price"] == 3699 and r.json()["cart"]["subtotal"] == 7398
        assert len(r.json()["cart"]["items"]) == 1  # updated, not duplicated


def test_edit_validation_and_bad_index():
    with client() as c:
        c.post("/cart/add", data=GOOD)
        bad = c.post("/cart/update", data={"index": "0", "size": "", "fabric": "Satin", "colour": "Mint"})
        assert bad.status_code == 400 and "size" in bad.json()["errors"]
        assert c.get("/cart.json").json()["items"][0]["size"] == "M"  # unchanged after failed edit
        assert c.post("/cart/update", data={**GOOD, "index": "5"}).status_code == 404
        assert c.get("/products/petal-set?edit=7", follow_redirects=False).status_code == 303
        assert c.get("/products/lune-dress?edit=0", follow_redirects=False).status_code == 303  # wrong garment


def test_edit_photo_keep_replace_remove():
    with client() as c:
        c.post("/cart/add", data=GOOD, files={"photo": ("a.png", PNG, "image/png")})
        first = c.get("/cart.json").json()["items"][0]["photo"]
        keep = c.post("/cart/update", data={**GOOD, "index": "0"}).json()["cart"]["items"][0]["photo"]
        assert keep == first
        new = c.post("/cart/update", data={**GOOD, "index": "0"}, files={"photo": ("b.png", PNG, "image/png")})
        second = new.json()["cart"]["items"][0]["photo"]
        assert second and second != first
        gone = c.post("/cart/update", data={**GOOD, "index": "0", "remove_photo": "on"})
        assert gone.json()["cart"]["items"][0]["photo"] == ""


def test_story4_edit_then_confirm_gives_order_number():
    with client() as c:
        c.post("/cart/add", data=GOOD)
        c.post("/cart/update", data={**GOOD, "index": "0", "colour": "Lavender", "notes": "Edited on review"})
        assert "Lavender" in c.get("/review").text
        r = c.post("/checkout", data=CONTACT, follow_redirects=False)
        assert r.status_code == 303
        assert "ORD-100" in c.get("/order-placed").text
        staff = c.get("/staff/orders").text
        assert "Lavender" in staff and "Edited on review" in staff


def test_review_remove_item():
    with client() as c:
        c.post("/cart/add", data=GOOD)
        c.post("/cart/remove", data={"index": "0"})
        assert c.get("/review", follow_redirects=False).status_code == 303
