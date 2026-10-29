# TAN MVP (TANvolution) - customisation and order tracking

A web-only MVP that looks like TAN's real site (tanofficials.com) and shows two ideas:
1. **Customisation** when ordering (Sprints 1 and 2, both built).
2. **Order tracking** with customer feedback checkpoints (Sprints 3 and 4, both built).

It runs on **demo data**. Products and prices are from TAN's All Products page. Fabric and colour options are demo options, not TAN's real list.

## Run it

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Open http://localhost:8000. Fonts (Montserrat, Roboto) load from Google Fonts, so use an internet connection to see the real look.

Run the tests: `pip install pytest httpx` then `pytest tests -q`.

## What Sprint 1 contains

| Story | Where to see it |
|---|---|
| 1. Choose garment, fabric and colour | Open a product (the product is the garment), then pick a fabric and one of 10 colours (soft pastels plus ivory and charcoal) |
| 2. Enter size and notes | Size boxes, "Notes for TAN", and TAN's own "Custom Fit Request (+₹200)" box |
| 3. Upload a reference photo | "Reference photo" box on the product page (JPG, PNG or WEBP, up to 5 MB) |
| 4. View saved orders (staff) | `/staff/orders` (also linked in the menu as "Staff view (MVP)") |

Flow: product page, Add to cart or Buy now, checkout, "Place order", order number shown, order appears in the staff list.

Also in the code, but not a separate story: the site shell (home page, header, footer, cart drawer and checkout page) so the MVP looks like TAN's site. Log it in Jira (for example under Story 1 or as its own task) so it isn't untracked work.

## What Sprint 2 adds (Customisation, refined)

| Story | Where to see it |
|---|---|
| 1. Fabric info cards | On any product page, pick a fabric: a card shows description, drape, stretch and care |
| 2. Fabric suitability hint | An amber "Heads up" note appears under the card for mismatched pairs (for example Luné Dress + Cotton Poplin, Bleu Stripe Muse Dress + Satin; 4 pairs in total, listed in `app/data.py`) |
| 3. Review summary page | `/review` lists every item with size, fabric, colour, custom fit, notes, reference photo, quantity and price |
| 4. Edit from summary and confirm | "Edit" on `/review` reopens the product form prefilled (`/products/<slug>?edit=<n>`) and "Save changes" updates that cart item. "Confirm and continue" goes to checkout, and "Place order" shows the order number |

Flow now: product page, Add to cart or Buy now, **review page (edit if needed)**, confirm, checkout, "Place order", order number shown, order appears in the staff list. The cart drawer button now reads "Review order" and each drawer item has an Edit link.

New routes: `GET /review`, `POST /cart/update`. Suitability pairs use string keys like `petal-set|Satin` so they can be sent to the browser as JSON.

## What Sprint 3 adds (Order tracking, basic)

| Story | Where to see it |
|---|---|
| 1. Order stages as a tracker | `/track/<order number>` shows the 6 stages (Idea Received, Sketch Shared, Fabric Sample Review, Trial Piece Review, Final Piece, Delivered) with the current one highlighted and the time each finished stage was reached |
| 2. Open tracking by order number | `/track` (also "Track your order" in the menu, and "Track this order" on the order-placed page). Accepts `ORD-1001`, `ord-1001` or just `1001`. An unknown number shows a clear message |
| 3. Staff advance the stage | `/staff/orders` has a Stage column and an "Advance to ..." button per order. The customer's tracker updates straight away. An order cannot go past Delivered |
| 4. Stage history log | Click an order number in the staff list to open `/staff/orders/<order number>`: every stage change with its time, newest first |

Notes:
- The tracking page shows only the piece details, never the customer's contact details.
- An existing `tan_mvp.db` from Sprint 1 or 2 is upgraded automatically on start (a `stage` column and a `stage_history` table are added, old orders start at Idea Received). You do not need to delete it.
- The database tables are checked on every connection, so deleting `app/tan_mvp.db` to reset the demo data is safe even while the server is running (a new empty one is created). Earlier this caused `no such table: orders` when placing an order.
- Staff pages have no login in this MVP.

## What Sprint 4 adds (Tracking with feedback)

Three stages are **checkpoints** where the customer must respond before TAN moves on: Sketch Shared, Fabric Sample Review and Trial Piece Review. The other stages need no approval.

| Story | Where to see it |
|---|---|
| 1. Approve at a checkpoint | On `/track/<order number>`, when the order is at a checkpoint, a "Please review your sketch / fabric sample / trial piece" panel has an **Approve** button. The approval is saved and the staff "Advance" button unlocks |
| 2. Request changes with a comment | The same panel has a comment box and **Request changes**. A comment is required (up to 500 characters). The order is marked "Changes requested" for the customer and for staff |
| Share an image to ask for approval | `/staff/orders/<order number>` has a "Share an image with the customer" form (JPG, PNG or WEBP, up to 5 MB, optional caption, 200 characters). The image is saved against the order's current stage and appears on the customer's tracking page inside the review panel, next to Approve and Request changes. Earlier images stay visible under "Images from TAN" |
| 3. Feedback log for staff | `/staff/orders/<order number>` has a "Customer feedback" table: time, stage, type (Approved, Changes requested, Revised version shared) and the comment, newest first. The staff list has a "Customer review" column |
| 4. Basic stats view (stretch) | `/staff/stats` shows feedback rounds per order, approvals, and time spent in each stage (with an average for finished stages) |

The feedback loop:
1. Staff advance an order to a checkpoint stage and upload an image of the sketch, sample or trial piece. The customer sees the review panel with that image. Staff see "Waiting for customer approval" and the Advance button is disabled.
2. The customer either approves (staff can now advance) or requests changes with a comment.
3. After a change request, staff upload the revised image, then click **Mark revised version shared**. The customer reviews the new image, and a new round can begin or the customer approves.

New routes: `POST /track/<no>/approve`, `POST /track/<no>/changes`, `POST /staff/orders/<no>/revision`, `POST /staff/orders/<no>/image`, `GET /staff/stats`.

Notes:
- **Change from Sprint 3:** staff can no longer advance an order past a checkpoint stage until the customer approves. At the other stages the Advance button works as before. The two Sprint 3 tests that advance through the checkpoints now approve first.
- A "feedback round" means one change request. Time in a stage runs until the next stage change; the current stage shows "so far".
- A database from Sprint 1, 2 or 3 is upgraded automatically (`feedback` and `stage_images` tables are added).
- Uploading an image is optional: the customer can still approve or request changes without one (the panel then says TAN has not attached an image yet).
- Like the rest of the MVP, the tracking page is opened with the order number only, and staff pages have no login.

## Project layout

```
app/main.py        routes (storefront, cart, review, checkout, tracking, feedback, staff)
app/data.py        demo products, fabrics, fabric details, suitability pairs, colours, sizes
app/db.py          SQLite orders, stage history and customer feedback
app/stats.py       feedback rounds and time-per-stage numbers for the stats page
app/templates/     pages (base, home, products, product, review, checkout, order_placed, track, staff_orders, staff_order, staff_stats)
app/static/        css, js, images (logo, hero and product photos cropped from TAN's site)
app/uploads/       customer reference photos (created at runtime, not committed)
tests/             Sprint 1, 2, 3 and 4 tests (49 in total)
```

## Commit messages

Start each commit with the Jira key, for example `KEY-4 add reference photo upload`. Commit each sprint's work on that sprint's day so the Git history matches the Jira timeline.
