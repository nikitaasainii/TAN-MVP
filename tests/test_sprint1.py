"""Sprint 1 checks: order form (customisation) saves an order, staff can see it."""
import base64
import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["TAN_DB"] = os.path.join(_tmp, "test.db")
os.environ["TAN_UPLOADS"] = os.path.join(_tmp, "uploads")

from fastapi.testclient import TestClient  # noqa: E402

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


def test_pages_load():
    with client() as c:
        for url in ["/", "/products", "/products/petal-set", "/staff/orders"]:
            assert c.get(url).status_code == 200, url
        assert c.get("/products/nope").status_code == 404
        assert c.get("/checkout", follow_redirects=False).status_code == 303


def test_story1_choice_required():
    with client() as c:
        r = c.post("/cart/add", data={"slug": "petal-set"})
        assert r.status_code == 400
        errs = r.json()["errors"]
        assert {"size", "fabric", "colour"} <= set(errs)


def test_story2_size_notes_and_fit_fee():
    with client() as c:
        r = c.post("/cart/add", data={**GOOD, "custom_fit": "on", "custom_fit_note": "Shorter skirt", "notes": "Add pockets"})
        assert r.status_code == 200
        item = r.json()["cart"]["items"][0]
        assert item["unit_price"] == 3699 and item["custom_fit_note"] == "Shorter skirt" and item["notes"] == "Add pockets"
        r = c.post("/cart/add", data={**GOOD, "custom_fit_note": "x" * 256, "custom_fit": "on"})
        assert r.status_code == 400 and "custom_fit_note" in r.json()["errors"]


def test_story3_photo_upload_rules():
    with client() as c:
        bad = c.post("/cart/add", data=GOOD, files={"photo": ("note.txt", b"hello", "text/plain")})
        assert bad.status_code == 400 and "photo" in bad.json()["errors"]
        ok = c.post("/cart/add", data=GOOD, files={"photo": ("ref.png", PNG, "image/png")})
        assert ok.status_code == 200 and ok.json()["cart"]["items"][0]["photo"].endswith(".png")


def test_checkout_validation():
    with client() as c:
        c.post("/cart/add", data=GOOD)
        r = c.post("/checkout", data={**CONTACT, "email": "nope", "postcode": "12"})
        assert r.status_code == 400
        assert "Enter a valid email address." in r.text and "Enter a 6-digit postcode." in r.text


def test_story4_full_flow_staff_list():
    with client() as c:
        c.post("/cart/add", data={**GOOD, "fabric": "Linen Blend", "notes": "Add pockets"},
               files={"photo": ("ref.png", PNG, "image/png")})
        r = c.post("/checkout", data=CONTACT, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/order-placed"
        placed = c.get("/order-placed")
        assert "ORD-100" in placed.text
        assert c.get("/cart.json").json()["count"] == 0
        staff = c.get("/staff/orders").text
        for expected in ["Petal Set", "Linen Blend", "Blush Pink", "Asha Rao", "Add pockets", "/uploads/"]:
            assert expected in staff, expected


def test_remove_from_cart():
    with client() as c:
        c.post("/cart/add", data=GOOD)
        r = c.post("/cart/remove", data={"index": "0"})
        assert r.json()["cart"]["count"] == 0


def test_story1_pastel_colours_available():
    from app.data import COLOURS
    names = [c["name"] for c in COLOURS]
    assert len(names) == 10 and {"Peach", "Butter Yellow", "Mint", "Lavender", "Baby Pink"} <= set(names)
    with client() as c:
        for name in names:
            r = c.post("/cart/add", data={**GOOD, "colour": name})
            assert r.status_code == 200, name
        bad = c.post("/cart/add", data={**GOOD, "colour": "Neon Green"})
        assert bad.status_code == 400 and "colour" in bad.json()["errors"]
