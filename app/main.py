import os
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import db, stats
from .data import (CHECKPOINTS, COLOURS, CUSTOM_FIT_FEE, FABRICS, FABRIC_DETAILS, PRODUCTS, PRODUCTS_BY_SLUG, SIZES,
                   STAGES, STATES, suitability_for)

BASE = Path(__file__).parent
UPLOAD_DIR = Path(os.environ.get("TAN_UPLOADS", BASE / "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_PHOTO_BYTES = 5 * 1024 * 1024
PHOTO_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}

@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    yield


app = FastAPI(title="TAN MVP", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("TAN_SECRET", "tan-mvp-demo-secret"))
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

templates = Jinja2Templates(directory=BASE / "templates")
templates.env.filters["inr"] = lambda v: f"₹{v:,.2f}"


# ---------- helpers ----------

def cart_items(request: Request) -> list:
    return request.session.get("cart", [])


def cart_view(request: Request) -> dict:
    items = []
    subtotal = 0
    for i, it in enumerate(cart_items(request)):
        line = it["unit_price"] * it["quantity"]
        subtotal += line
        items.append({**it, "index": i, "line_total": line})
    return {"items": items, "subtotal": subtotal, "count": sum(it["quantity"] for it in items)}


def page(request: Request, name: str, status_code: int = 200, **ctx):
    ctx.update(cart=cart_view(request))
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


# ---------- storefront pages ----------

@app.get("/")
def home(request: Request):
    return page(request, "home.html")


@app.get("/products")
def products(request: Request):
    return page(request, "products.html", products=PRODUCTS)


@app.get("/products/{slug}")
def product_detail(request: Request, slug: str, edit: int | None = None):
    product = PRODUCTS_BY_SLUG.get(slug)
    if not product:
        return page(request, "not_found.html", status_code=404)
    edit_item = None
    if edit is not None:
        cart = cart_items(request)
        if 0 <= edit < len(cart) and cart[edit]["slug"] == slug:
            edit_item = cart[edit]
        else:
            return RedirectResponse(f"/products/{slug}", status_code=303)
    return page(request, "product.html", product=product, sizes=SIZES, fabrics=FABRICS,
                colours=COLOURS, fit_fee=CUSTOM_FIT_FEE, fabric_details=FABRIC_DETAILS,
                warnings=suitability_for(slug), edit_item=edit_item, edit_index=edit if edit_item else None)


# ---------- cart ----------

async def build_item(product, size, fabric, colour, custom_fit, custom_fit_note, notes, quantity,
                     photo, keep_photo=""):
    """Validate the form fields and return (item, errors, new_photo_name)."""
    errors = {}
    if size not in SIZES:
        errors["size"] = "Please select a size."
    if fabric not in FABRICS:
        errors["fabric"] = "Please choose a fabric."
    if colour not in [c["name"] for c in COLOURS]:
        errors["colour"] = "Please choose a colour."
    if not 1 <= quantity <= 10:
        errors["quantity"] = "Quantity must be between 1 and 10."
    wants_fit = custom_fit.lower() in ("on", "true", "1", "yes")
    if len(custom_fit_note) > 255:
        errors["custom_fit_note"] = "Custom fit request can be up to 255 characters."
    if len(notes) > 500:
        errors["notes"] = "Notes can be up to 500 characters."

    new_photo = ""
    if photo is not None and photo.filename:
        data = await photo.read()
        if photo.content_type not in PHOTO_TYPES:
            errors["photo"] = "Please upload a JPG, PNG or WEBP image."
        elif len(data) > MAX_PHOTO_BYTES:
            errors["photo"] = "The photo must be smaller than 5 MB."
        elif data:
            new_photo = f"{uuid.uuid4().hex}{PHOTO_TYPES[photo.content_type]}"
            (UPLOAD_DIR / new_photo).write_bytes(data)

    if errors:
        if new_photo:
            (UPLOAD_DIR / new_photo).unlink(missing_ok=True)
        return None, errors, ""

    unit_price = product["price"] + (CUSTOM_FIT_FEE if wants_fit else 0)
    item = {
        "slug": product["slug"], "name": product["name"], "image": product["image"], "size": size,
        "fabric": fabric, "colour": colour, "custom_fit": wants_fit,
        "custom_fit_note": custom_fit_note.strip() if wants_fit else "",
        "notes": notes.strip(), "photo": new_photo or keep_photo, "quantity": quantity,
        "unit_price": unit_price,
    }
    return item, {}, new_photo


@app.post("/cart/add")
async def cart_add(
    request: Request,
    slug: str = Form(""),
    size: str = Form(""),
    fabric: str = Form(""),
    colour: str = Form(""),
    custom_fit: str = Form(""),
    custom_fit_note: str = Form(""),
    notes: str = Form(""),
    quantity: int = Form(1),
    photo: UploadFile | None = File(None),
):
    product = PRODUCTS_BY_SLUG.get(slug)
    if not product:
        return JSONResponse({"ok": False, "errors": {"form": "This piece could not be found."}}, status_code=404)

    item, errors, _ = await build_item(product, size, fabric, colour, custom_fit, custom_fit_note,
                                       notes, quantity, photo)
    if errors:
        return JSONResponse({"ok": False, "errors": errors}, status_code=400)

    cart = cart_items(request)
    cart.append(item)
    request.session["cart"] = cart
    return {"ok": True, "cart": cart_view(request)}


@app.post("/cart/update")
async def cart_update(
    request: Request,
    index: int = Form(...),
    size: str = Form(""),
    fabric: str = Form(""),
    colour: str = Form(""),
    custom_fit: str = Form(""),
    custom_fit_note: str = Form(""),
    notes: str = Form(""),
    quantity: int = Form(1),
    remove_photo: str = Form(""),
    photo: UploadFile | None = File(None),
):
    """Edit one item already in the cart (used by the Edit button on the review page)."""
    cart = cart_items(request)
    if not 0 <= index < len(cart):
        return JSONResponse({"ok": False, "errors": {"form": "This item is no longer in your cart."}}, status_code=404)
    old = cart[index]
    product = PRODUCTS_BY_SLUG[old["slug"]]
    removing = remove_photo.lower() in ("on", "true", "1", "yes")

    item, errors, new_photo = await build_item(product, size, fabric, colour, custom_fit, custom_fit_note,
                                               notes, quantity, photo,
                                               keep_photo="" if removing else old["photo"])
    if errors:
        return JSONResponse({"ok": False, "errors": errors}, status_code=400)

    if old["photo"] and old["photo"] != item["photo"]:
        (UPLOAD_DIR / old["photo"]).unlink(missing_ok=True)
    cart[index] = item
    request.session["cart"] = cart
    return {"ok": True, "cart": cart_view(request)}


@app.get("/cart.json")
def cart_json(request: Request):
    return cart_view(request)


@app.post("/cart/remove")
def cart_remove(request: Request, index: int = Form(...)):
    cart = cart_items(request)
    if 0 <= index < len(cart):
        cart.pop(index)
        request.session["cart"] = cart
    return {"ok": True, "cart": cart_view(request)}


# ---------- review (Sprint 2) ----------

@app.get("/review")
def review(request: Request):
    cart = cart_view(request)
    if not cart["items"]:
        return RedirectResponse("/products", status_code=303)
    for it in cart["items"]:
        it["fabric_info"] = FABRIC_DETAILS.get(it["fabric"], {})
        it["warning"] = suitability_for(it["slug"]).get(it["fabric"], "")
    return page(request, "review.html", review_items=cart["items"])


# ---------- checkout ----------

REQUIRED = {
    "first_name": "Enter your first name.",
    "last_name": "Enter your last name.",
    "address": "Enter your address.",
    "city": "Enter your city.",
    "state": "Select your state.",
}


@app.get("/checkout")
def checkout(request: Request):
    if not cart_items(request):
        return RedirectResponse("/products", status_code=303)
    return page(request, "checkout.html", states=STATES, values={}, errors={})


@app.post("/checkout")
def checkout_submit(
    request: Request,
    email: str = Form(""),
    first_name: str = Form(""),
    last_name: str = Form(""),
    address: str = Form(""),
    apartment: str = Form(""),
    city: str = Form(""),
    state: str = Form(""),
    postcode: str = Form(""),
    phone: str = Form(""),
):
    items = cart_items(request)
    if not items:
        return RedirectResponse("/products", status_code=303)

    values = {"email": email.strip(), "first_name": first_name.strip(), "last_name": last_name.strip(),
              "address": address.strip(), "apartment": apartment.strip(), "city": city.strip(),
              "state": state.strip(), "postcode": postcode.strip(), "phone": phone.strip()}
    errors = {k: msg for k, msg in REQUIRED.items() if not values[k]}
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", values["email"]):
        errors["email"] = "Enter a valid email address."
    if not re.fullmatch(r"\d{6}", values["postcode"]):
        errors["postcode"] = "Enter a 6-digit postcode."
    if len(re.sub(r"\D", "", values["phone"])) < 10:
        errors["phone"] = "Enter a valid phone number."
    if values["state"] and values["state"] not in STATES:
        errors["state"] = "Select your state."

    if errors:
        return page(request, "checkout.html", status_code=400, states=STATES, values=values, errors=errors)

    street = values["address"] + (f", {values['apartment']}" if values["apartment"] else "")
    contact = {"customer_name": f"{values['first_name']} {values['last_name']}", "email": values["email"],
               "phone": values["phone"], "address": street, "city": values["city"],
               "state": values["state"], "postcode": values["postcode"]}
    placed = []
    for it in items:
        placed.append({"order_no": db.create_order(it, contact), "name": it["name"],
                       "size": it["size"], "fabric": it["fabric"], "colour": it["colour"]})
    request.session["cart"] = []
    request.session["placed"] = placed
    return RedirectResponse("/order-placed", status_code=303)


@app.get("/order-placed")
def order_placed(request: Request):
    placed = request.session.get("placed")
    if not placed:
        return RedirectResponse("/", status_code=303)
    return page(request, "order_placed.html", placed=placed)


# ---------- order tracking (Sprint 3) ----------

def normalise_order_no(raw: str) -> str:
    """Accept 'ord-1001', ' ORD 1001 ' or just '1001' and return 'ORD-1001'."""
    cleaned = raw.strip().upper().replace(" ", "")
    if cleaned.isdigit():
        cleaned = "ORD-" + cleaned
    return cleaned


def tracker_steps(order: dict, history: list) -> list:
    times = {h["stage"]: h["changed_at"] for h in history}
    last = len(STAGES) - 1
    steps = []
    for i, name in enumerate(STAGES):
        state = "done" if i < order["stage"] else "current" if i == order["stage"] else "todo"
        steps.append({"name": name, "state": state, "time": times.get(i, ""),
                      "dot": "\u2713" if state == "done" or (state == "current" and i == last) else str(i + 1)})
    return steps


@app.get("/track")
def track_form(request: Request, order_no: str = ""):
    if order_no.strip():
        return RedirectResponse(f"/track/{quote(normalise_order_no(order_no))}", status_code=303)
    return page(request, "track.html", order=None, steps=[], error="", value="")


def render_track(request: Request, order_no: str, status_code: int = 200, comment_error: str = "",
                 comment_value: str = ""):
    """The customer's tracking page (also re-used to show a problem with the change-request form)."""
    number = normalise_order_no(order_no)
    order = db.get_order(number)
    if not order:
        return page(request, "track.html", status_code=404, order=None, steps=[], value=order_no,
                    error="We could not find that order number. Please check it and try again.")
    steps = tracker_steps(order, db.stage_history(number))
    return page(request, "track.html", status_code=status_code, order=order, steps=steps, error="", value=number,
                stage_name=STAGES[order["stage"]], delivered=order["stage"] == len(STAGES) - 1,
                checkpoint=CHECKPOINTS.get(order["stage"]), review=order["review"],
                feedback=db.feedback_log(number), images=db.stage_images(number),
                comment_error=comment_error, comment_value=comment_value)


@app.get("/track/{order_no}")
def track_order(request: Request, order_no: str):
    return render_track(request, order_no)


# ---------- customer feedback at checkpoints (Sprint 4) ----------

MAX_COMMENT = 500


@app.post("/track/{order_no}/approve")
def track_approve(order_no: str):
    number = normalise_order_no(order_no)
    db.add_feedback(number, "approved")  # ignored if not at a checkpoint or already answered
    return RedirectResponse(f"/track/{quote(number)}#checkpoint", status_code=303)


@app.post("/track/{order_no}/changes")
def track_changes(request: Request, order_no: str, comment: str = Form("")):
    number = normalise_order_no(order_no)
    if not db.get_order(number):
        return RedirectResponse(f"/track/{quote(number)}", status_code=303)
    text = comment.strip()
    error = ""
    if not text:
        error = "Please tell us what you would like changed."
    elif len(text) > MAX_COMMENT:
        error = f"Comments can be up to {MAX_COMMENT} characters."
    if error:
        return render_track(request, number, status_code=400, comment_error=error, comment_value=comment)
    db.add_feedback(number, "changes_requested", text)
    return RedirectResponse(f"/track/{quote(number)}#checkpoint", status_code=303)


# ---------- staff view ----------

@app.get("/staff/orders")
def staff_orders(request: Request):
    return page(request, "staff_orders.html", orders=db.list_orders(), stages=STAGES)


def render_staff_order(request: Request, order_no: str, status_code: int = 200, upload_error: str = "",
                       note_value: str = ""):
    order = db.get_order(order_no)
    if not order:
        return page(request, "not_found.html", status_code=404)
    return page(request, "staff_order.html", status_code=status_code, order=order, stages=STAGES,
                history=db.stage_history(order_no), checkpoint=CHECKPOINTS.get(order["stage"]),
                feedback=db.feedback_log(order_no), images=db.stage_images(order_no),
                upload_error=upload_error, note_value=note_value)


@app.get("/staff/orders/{order_no}")
def staff_order_detail(request: Request, order_no: str):
    return render_staff_order(request, order_no)


def staff_target(order_no: str, back: str) -> str:
    return f"/staff/orders/{quote(order_no)}" if back == "detail" else "/staff/orders"


@app.post("/staff/orders/{order_no}/advance")
def staff_advance(order_no: str, back: str = Form("list")):
    if not db.get_order(order_no):
        return RedirectResponse("/staff/orders", status_code=303)
    db.advance_stage(order_no)  # does nothing at Delivered, or at a checkpoint the customer has not approved
    return RedirectResponse(staff_target(order_no, back), status_code=303)


@app.post("/staff/orders/{order_no}/revision")
def staff_revision(order_no: str, back: str = Form("list")):
    """Staff share a revised version after the customer asked for changes, so the customer can review again."""
    if not db.get_order(order_no):
        return RedirectResponse("/staff/orders", status_code=303)
    db.add_feedback(order_no, "revision_shared")
    return RedirectResponse(staff_target(order_no, back), status_code=303)


MAX_NOTE = 200


@app.post("/staff/orders/{order_no}/image")
async def staff_upload_image(request: Request, order_no: str, photo: UploadFile | None = File(None),
                             note: str = Form("")):
    """Staff share an image (sketch, fabric sample, trial piece...) so the customer can see it and respond."""
    if not db.get_order(order_no):
        return RedirectResponse("/staff/orders", status_code=303)
    text = note.strip()
    error, name = "", ""
    if photo is None or not photo.filename:
        error = "Please choose an image to upload."
    elif len(text) > MAX_NOTE:
        error = f"The caption can be up to {MAX_NOTE} characters."
    else:
        data = await photo.read()
        if photo.content_type not in PHOTO_TYPES:
            error = "Please upload a JPG, PNG or WEBP image."
        elif not data:
            error = "That file is empty. Please choose another image."
        elif len(data) > MAX_PHOTO_BYTES:
            error = "The image must be smaller than 5 MB."
        else:
            name = f"{uuid.uuid4().hex}{PHOTO_TYPES[photo.content_type]}"
    if error:
        return render_staff_order(request, order_no, status_code=400, upload_error=error, note_value=note)
    (UPLOAD_DIR / name).write_bytes(data)
    db.add_stage_image(order_no, name, text)
    return RedirectResponse(f"/staff/orders/{quote(order_no)}#images", status_code=303)


@app.get("/staff/stats")
def staff_stats(request: Request):
    orders = db.list_orders()
    histories = {o["order_no"]: db.stage_history(o["order_no"]) for o in orders}
    feedbacks = {o["order_no"]: db.feedback_log(o["order_no"]) for o in orders}
    return page(request, "staff_stats.html", stages=STAGES, **stats.build_stats(orders, histories, feedbacks))
