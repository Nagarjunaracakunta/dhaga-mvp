"""The controlled business taxonomy. The LLM must map free text INTO this; code validates it."""
from enum import Enum


class Primary(str, Enum):
    FIT = "FIT"
    QUALITY = "QUALITY"
    COLOUR = "COLOUR"
    DAMAGE = "DAMAGE"
    WRONG_ITEM = "WRONG_ITEM"
    CHANGED_MIND = "CHANGED_MIND"
    UNCLEAR = "UNCLEAR"


class Sub(str, Enum):
    TOO_TIGHT = "TOO_TIGHT"
    TOO_LOOSE = "TOO_LOOSE"
    TOO_SHORT = "TOO_SHORT"
    TOO_LONG = "TOO_LONG"
    FABRIC = "FABRIC"
    STITCHING = "STITCHING"
    LISTING_DIFFERENCE = "LISTING_DIFFERENCE"
    UNSPECIFIED = "UNSPECIFIED"
    UNCLEAR = "UNCLEAR"


class BodyArea(str, Enum):
    SHOULDERS = "SHOULDERS"
    BUST = "BUST"
    WAIST = "WAIST"
    HIPS = "HIPS"
    SLEEVES = "SLEEVES"
    LENGTH = "LENGTH"
    NONE = "NONE"


ALLOWED_SUBS = {
    Primary.FIT: {Sub.TOO_TIGHT, Sub.TOO_LOOSE, Sub.TOO_SHORT, Sub.TOO_LONG, Sub.UNSPECIFIED},
    Primary.QUALITY: {Sub.FABRIC, Sub.STITCHING, Sub.UNSPECIFIED},
    Primary.COLOUR: {Sub.LISTING_DIFFERENCE, Sub.UNSPECIFIED},
    Primary.DAMAGE: {Sub.UNSPECIFIED},
    Primary.WRONG_ITEM: {Sub.UNSPECIFIED},
    Primary.CHANGED_MIND: {Sub.UNSPECIFIED},
    Primary.UNCLEAR: {Sub.UNCLEAR},
}


def is_valid_combo(primary, sub) -> bool:
    try:
        return Sub(sub) in ALLOWED_SUBS[Primary(primary)]
    except ValueError:
        return False


def taxonomy_text() -> str:
    return "\n".join(f"- {p.value}: " + ", ".join(sorted(s.value for s in subs)) for p, subs in ALLOWED_SUBS.items())
