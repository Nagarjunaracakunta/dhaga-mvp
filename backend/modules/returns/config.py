"""Central config: paths, canonical mappings, thresholds. No logic here."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
PROCESSED_DIR = DATA_DIR / "processed"

PRODUCT_COLUMNS = ["product_id", "product_name", "category"]
ORDER_COLUMNS = ["order_id", "customer_id", "product_id", "size", "colour", "order_date"]
RETURN_COLUMNS = [
    "return_id", "order_id", "customer_id", "product_id", "product_name", "category",
    "size", "colour", "return_reason", "return_comment", "return_date",
]
# Fields that must be non-blank for a record to be usable at all
REQUIRED_RETURN_FIELDS = ["return_id", "order_id", "product_id", "return_reason", "return_date"]
REQUIRED_ORDER_FIELDS = ["order_id", "product_id", "size", "order_date"]

DATE_FORMAT = "%Y-%m-%d"

# ---- Normalization maps (all keys lower-case, whitespace-collapsed) ----
SIZE_MAP = {
    "xs": "XS", "extra small": "XS",
    "s": "S", "small": "S",
    "m": "M", "medium": "M",
    "l": "L", "large": "L",
    "xl": "XL", "extra large": "XL",
    "xxl": "XXL", "2xl": "XXL",
    "free": "FREE", "free size": "FREE", "freesize": "FREE", "one size": "FREE", "os": "FREE",
}

COLOUR_VARIANTS = {
    "Pink": ["pink", "pinkish", "light pink", "gulabi", "baby pink"],
    "Peach": ["peach", "peachy"],
    "Blue": ["blue", "navy", "navy blue", "sky blue", "neela"],
    "Black": ["black", "kala"],
    "White": ["white", "off white", "off-white", "safed"],
    "Green": ["green", "olive", "sage green", "hara"],
    "Red": ["red", "laal", "lal"],
    "Yellow": ["yellow", "peela"],
    "Mustard": ["mustard", "mustard yellow"],
    "Maroon": ["maroon", "wine"],
}
COLOUR_MAP = {v: canon for canon, variants in COLOUR_VARIANTS.items() for v in variants}

# Reason dropdown -> (primary_reason, sub_reason). "other" is deliberately absent:
# those rows are the ones that will need language understanding (LLM) later.
DROPDOWN_REASON_MAP = {
    "size too small": ("FIT", "TOO_TIGHT"),
    "size too large": ("FIT", "TOO_LOOSE"),
    "quality not as expected": ("QUALITY", "UNSPECIFIED"),
    "colour different from photo": ("COLOUR", "LISTING_DIFFERENCE"),
    "damaged product": ("DAMAGE", "UNSPECIFIED"),
    "wrong item received": ("WRONG_ITEM", "UNSPECIFIED"),
    "changed my mind": ("CHANGED_MIND", "UNSPECIFIED"),
    # Dropdown values as stored in the live Supabase returns table
    "size/fit": ("FIT", "UNSPECIFIED"),
    "colour mismatch": ("COLOUR", "LISTING_DIFFERENCE"),
    "quality": ("QUALITY", "UNSPECIFIED"),
    "damaged": ("DAMAGE", "UNSPECIFIED"),
    "wrong item": ("WRONG_ITEM", "UNSPECIFIED"),
}
OTHER_REASON = "other"

# ---- Insight thresholds ----
MIN_RETURNS_FOR_INSIGHT = 15   # don't flag tiny samples (demo CSVs: ~450 returns)
MIN_RETURNS_FOR_INSIGHT_SUPABASE = 8   # live data is smaller: 563 returns over 100 products
LIFT_THRESHOLD = 1.5           # cell return rate must be >= 1.5x the overall rate
PARENT_LIFT_THRESHOLD = 1.4    # a size/colour cell must beat its own product's rate by this much
MAX_SAMPLE_COMMENTS = 5
