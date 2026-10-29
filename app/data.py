"""Demo catalogue and customisation options for the TAN MVP.

Products and prices come from TAN's All Products page. Fabric and colour
options are DEMO data for the MVP (not TAN's real fabric list).
"""

CUSTOM_FIT_FEE = 200  # same as the "Custom Fit Request (+₹200)" option on TAN's site

SIZES = ["XS", "S", "M", "XL"]

FABRICS = ["Cotton Cambric", "Linen Blend", "Satin", "Cotton Poplin"]

FABRIC_DETAILS = {
    "Cotton Cambric": {
        "description": "Lightweight, crisp cotton with a smooth texture. Breathes exceptionally well.",
        "drape": "Crisp and structured",
        "stretch": "None",
        "care": "Dry Clean Only",
    },
    "Linen Blend": {
        "description": "Airy and breathable with a signature natural texture and relaxed feel.",
        "drape": "Soft and flowing",
        "stretch": "Low natural give",
        "care": "Gentle hand wash or Dry Clean",
    },
    "Satin": {
        "description": "Luxurious glossy finish with a fluid, slippery drape that hugs the silhouette.",
        "drape": "Fluid and slinky",
        "stretch": "Low (or slight spandex blend)",
        "care": "Dry Clean Only",
    },
    "Cotton Poplin": {
        "description": "Tightly woven sturdy cotton that holds sharp shapes and structured silhouettes.",
        "drape": "Structured and crisp",
        "stretch": "None",
        "care": "Machine wash gentle or Dry Clean",
    },
}

# Garment + fabric pairs that may not look or behave like the reference photo.
# Key format is "<product slug>|<fabric>" (a string so it can be sent to the browser as JSON).
SUITABILITY_WARNINGS = {
    "lune-dress|Cotton Poplin": "Cotton Poplin is quite stiff for the flowy Luné Dress silhouette and will look more structured than the reference photo.",
    "bleu-stripe-muse-dress|Satin": "Satin has a high-gloss finish and fluid drape, which differs significantly from standard striped cotton styling.",
    "petal-set|Satin": "The Petal Set top is a structured button-down. Satin is slinky and may not hold its shape the way the photo shows.",
    "cherie-set|Satin": "The Cherié Set relies on crisp gingham ruffles. Satin will drape softly and lose that crisp shape.",
}


def suitability_for(slug: str) -> dict:
    """Return {fabric: message} for one garment."""
    prefix = slug + "|"
    return {k[len(prefix):]: v for k, v in SUITABILITY_WARNINGS.items() if k.startswith(prefix)}

COLOURS = [
    {"name": "Blush Pink", "hex": "#e9c6c4"},
    {"name": "Ivory", "hex": "#f2ece0"},
    {"name": "Sage Green", "hex": "#b5c4a6"},
    {"name": "Powder Blue", "hex": "#bfd2e3"},
    {"name": "Charcoal", "hex": "#3a3a3a"},
    {"name": "Peach", "hex": "#f8d5bf"},
    {"name": "Butter Yellow", "hex": "#f6eab9"},
    {"name": "Mint", "hex": "#cde8d9"},
    {"name": "Lavender", "hex": "#d8cfea"},
    {"name": "Baby Pink", "hex": "#f7d4dc"},
]

# Order stages (Sprint 3). An order starts at stage 0 and staff move it forward one stage at a time.
STAGES = [
    "Idea Received",
    "Sketch Shared",
    "Fabric Sample Review",
    "Trial Piece Review",
    "Final Piece",
    "Delivered",
]

# Sprint 4: stages where the customer must respond before staff can move the order on.
# Key = stage number, value = what the customer is looking at.
CHECKPOINTS = {1: "sketch", 2: "fabric sample", 3: "trial piece"}

FEEDBACK_LABELS = {
    "approved": "Approved",
    "changes_requested": "Changes requested",
    "revision_shared": "Revised version shared (staff)",
}

PRODUCTS = [
    {
        "slug": "lune-dress",
        "name": "Luné Dress",
        "price": 3499,
        "price_from": True,
        "image": "lune-dress.jpg",
        "detail_image": "lune-dress.jpg",
        "description": "Taxes included. Shipping calculated at checkout.",
    },
    {
        "slug": "cherie-set",
        "name": "Cherié Set",
        "price": 2299,
        "price_from": False,
        "image": "cherie-set.jpg",
        "detail_image": "cherie-set.jpg",
        "description": "Taxes included. Shipping calculated at checkout.",
    },
    {
        "slug": "bleu-stripe-muse-dress",
        "name": "Bleu Stripe Muse Dress",
        "price": 2799,
        "price_from": False,
        "image": "bleu-stripe-muse-dress.jpg",
        "detail_image": "bleu-stripe-muse-dress.jpg",
        "description": "Taxes included. Shipping calculated at checkout.",
    },
    {
        "slug": "petal-set",
        "name": "Petal Set",
        "price": 3499,
        "price_from": False,
        "image": "petal-set.jpg",
        "detail_image": "petal-set-main.jpg",
        "description": (
            "Taxes included. Shipping calculated at checkout. Structured button-down top "
            "featuring adjustable back tie-up strings for a snatched fit, paired with a flowy "
            "midi skirt. Fabric Detail & Care Material- Cotton Cambric. Preserve the beauty of "
            "your garment. Do not machine wash; Dry Clean Only."
        ),
    },
]

PRODUCTS_BY_SLUG = {p["slug"]: p for p in PRODUCTS}

STATES = [
    "Andhra Pradesh", "Assam", "Bihar", "Chandigarh", "Chhattisgarh", "Delhi", "Goa", "Gujarat",
    "Haryana", "Himachal Pradesh", "Jammu and Kashmir", "Jharkhand", "Karnataka", "Kerala",
    "Madhya Pradesh", "Maharashtra", "Odisha", "Punjab", "Rajasthan", "Tamil Nadu", "Telangana",
    "Uttar Pradesh", "Uttarakhand", "West Bengal",
]
