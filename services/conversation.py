"""Deterministic conversational routing for the Farmer Assistant.

Runs before retrieval so greetings, out-of-scope and livestock turns never invoke RAG or the
verifier. Crop mentions are resolved from the current turn or earlier user turns, which keeps
the conversation from re-asking for a crop the caller already named.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Intent = Literal[
    "greeting",
    "social",
    "clarification",
    "livestock",
    "out_of_scope",
    "crop_only",
    "crop_question",
    "crop_problem",
    "general_crop_question",
]

CROP_ALIASES: dict[str, tuple[str, ...]] = {
    "maize": ("maize", "corn"),
    "rice": ("rice", "paddy"),
    "cassava": ("cassava",),
    "tomato": ("tomato", "tomatoes"),
    "pepper": ("pepper", "peppers", "chilli", "chili"),
    "onion": ("onion", "onions"),
    "garlic": ("garlic",),
    "cowpea": ("cowpea", "cowpeas", "beans"),
    "groundnut": ("groundnut", "groundnuts", "peanut", "peanuts"),
    "soybean": ("soybean", "soybeans", "soya"),
    "sorghum": ("sorghum", "guinea corn"),
    "millet": ("millet",),
    "yam": ("yam", "yams"),
    "plantain": ("plantain", "plantains"),
    "banana": ("banana", "bananas"),
    "cocoa": ("cocoa", "cacao"),
    "rubber": ("rubber",),
    "citrus": ("citrus", "orange", "oranges", "lemon", "lime"),
    "mango": ("mango", "mangoes"),
    "pineapple": ("pineapple", "pineapples"),
    "okra": ("okra",),
    "garden egg": ("garden egg", "garden eggs", "eggplant", "aubergine"),
    "ogbono": ("ogbono", "irvingia"),
    "gum arabic": ("gum arabic", "gum arabic"),
    "lablab": ("lablab",),
    "wheat": ("wheat",),
    "potato": ("potato", "potatoes"),
    "sweet potato": ("sweet potato", "sweet potatoes"),
    "beniseed": ("beniseed", "sesame"),
}

LIVESTOCK_TERMS = (
    "cow", "cattle", "goat", "goats", "sheep", "chicken", "chickens", "poultry",
    "duck", "ducks", "pig", "pigs", "swine", "fish", "fishery", "aquaculture",
    "snail", "snails", "rabbit", "rabbits", "horse", "horses", "dog", "dogs",
    "livestock", "herd", "veterinary", "veterinarian",
    "newcastle", "rabies", "anthrax", "trypanosomiasis", "mastitis",
    "foot and mouth", "lumpy skin", "ppr", "brucellosis",
)

OUT_OF_SCOPE_PATTERNS = (
    r"\b(football|soccer|premier league|match result|who won)\b",
    r"\b(election|president|governor|politics|political party)\b",
    r"\b(interest rate|inflation|forex|exchange rate|stock market|crypto|bitcoin)\b",
    r"\b(movie|music|celebrity|joke|recipe for jollof)\b",
    r"\b(phone|sim card|data plan|betting|lottery)\b",
)

BACKCHANNEL_PATTERNS = (
    r"\b(do|can|could) you hear( me| us| that)?\b",
    r"\b(are|is) you (there|hearing me)\b",
    r"\bi (can't|cannot|can not) hear you\b",
)

CLARIFICATION_PATTERNS = (
    r"^(what do you mean|what does that mean|can you clarify|could you clarify|please clarify)\b",
    r"^(explain( that| this| it)?|i (do not|don't) understand|repeat that|say that again)\b",
    r"^(which (one|part|crop) do you mean)\b",
)

GREETING_RE = re.compile(
    r"^(?:hi|hello|hey|hiya|greetings|good (?:morning|afternoon|evening)|"
    r"how are you(?: doing)?|how far|sannu|bawo)\b[\s,.!?]*",
    re.IGNORECASE,
)

SOCIAL_RE = re.compile(
    r"^(?:thanks|thank you|thank you very much|bye|goodbye|see you|okay|ok|alright)\b[\s,.!?]*",
    re.IGNORECASE,
)

_SHORT_FILLERS = {
    "no", "yes", "okay", "ok", "please", "actually", "well", "so", "i", "me",
    "also", "ask", "it", "that", "this", "and", "but",
}

CROP_ONLY_FILLER = {
    "i", "we", "grow", "growing", "plant", "planting", "am", "is", "are", "my",
    "farm", "farming", "have", "has", "the", "a", "an", "on", "of", "about",
    "it", "this", "that", "please", "thanks", "thank", "you", "crop", "crops",
    "ask", "also", "just", "want", "wanted",
}

NEEDS_CROP_TERMS = (
    "fertilizer", "fertiliser", "manure", "spacing", "seed", "seeds", "variety",
    "varieties", "plant", "planting", "sow", "sowing", "transplant", "harvest",
    "harvesting", "storage", "store", "irrigation", "irrigate", "yield", "weed",
    "weeds", "pest", "pests", "disease", "diseases", "insect", "insects",
    "spray", "spraying", "yellow", "yellowing", "wilting", "wilt", "spots",
    "dying", "died", "holes", "rot", "blight", "mosaic", "stunted", "leaves",
    "leaf", "stem", "root", "roots", "fall armyworm", "armyworm",
)

PROBLEM_TERMS = (
    "yellow", "yellowing", "wilting", "wilt", "spots", "dying", "died", "holes",
    "rot", "blight", "mosaic", "stunted", "pest", "pests", "disease", "diseases",
    "insect", "insects", "weed", "weeds", "armyworm", "damage", "sick",
)

#GREETING_REPLY = (
#    "Hello! I am AgroBridge, your crop-production assistant. I can help with maize, rice, "
#    "cassava, tomato, pepper and other crops. Which crop are you growing?"
#)
GREETING_REPLY = (
    "Hello! I am AgroBridge, your crop-production assistant. I can help with querries concerning your farm, "
    "what will you need my assistance with today?"
)
SOCIAL_REPLY = (
    "You are welcome. I am here whenever you need help with a crop-production question."
)
CLARIFY_REPLY = (
    "I can clarify. Which part would you like me to explain: the crop, the symptoms you are "
    "seeing, or the recommended next step?"
)
NO_CROP_REPLY = (
    "I can help with that, but I need to know which crop you mean. Which crop are you asking "
    "about, for example maize, rice, cassava or tomato?"
)
CROP_ONLY_TEMPLATE = (
    "Thanks, I have noted {crop}. What would you like to know about your {crop}? For example, "
    "planting, fertilizer, pests or harvest."
)
LIVESTOCK_REPLY = (
    "I can only help with crop production, not livestock or animal production. For animal "
    "health, please contact a veterinarian or your local livestock extension officer. I can "
    "help with crop questions such as maize, rice, cassava, tomato or pepper."
)
BACKCHANNEL_REPLY = (
    "Yes, I can hear you. Please tell me what you would like to know about your crop."
)
OUT_OF_SCOPE_REPLY = (
    "I am AgroBridge, a crop-production assistant, so I cannot help with that. I can answer "
    "questions about growing crops such as maize, rice, cassava, tomato and pepper."
)


@dataclass(frozen=True)
class Turn:
    intent: Intent
    crop: str | None
    direct_answer: str | None
    cleaned_question: str


def detect_crop(text: str) -> str | None:
    lowered = text.lower()
    pairs = sorted(
        ((alias, crop) for crop, aliases in CROP_ALIASES.items() for alias in aliases),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    for alias, crop in pairs:
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            return crop
    return None


def crop_from_history(history: list[dict[str, str]] | None) -> str | None:
    if not history:
        return None
    for message in reversed(history):
        if message.get("role") != "user":
            continue
        crop = detect_crop(str(message.get("content", "")))
        if crop:
            return crop
    return None


def mentions_crop(text: str, crop: str) -> bool:
    aliases = CROP_ALIASES.get(crop, (crop,))
    lowered = text.lower()
    return any(re.search(rf"\b{re.escape(alias)}\b", lowered) for alias in aliases)


def _is_crop_only(text: str, crop: str | None) -> bool:
    if not crop:
        return False
    removed = text.lower()
    for alias in CROP_ALIASES.get(crop, (crop,)):
        removed = re.sub(rf"\b{re.escape(alias)}\b", " ", removed)
    tokens = [token for token in re.findall(r"[a-z0-9]+", removed) if token not in CROP_ONLY_FILLER]
    return len(tokens) == 0


def classify_turn(question: str, history: list[dict[str, str]] | None = None) -> Turn:
    original = " ".join(str(question or "").split())
    if not original:
        return Turn("clarification", None, NO_CROP_REPLY, original)

    # Strip leading conversational fillers ("Okay.", "No.", "So...") before routing.
    cleaned = original
    for _ in range(2):
        stripped = re.sub(r"^(okay|ok|no|so|well)[\s,.!?]+", "", cleaned, flags=re.IGNORECASE).strip()
        if stripped == cleaned:
            break
        cleaned = stripped
    if not cleaned:
        return Turn("clarification", detect_crop(original), NO_CROP_REPLY, original)

    # Social / greeting first, but keep any substantive content after it.
    greeting = GREETING_RE.match(cleaned)
    if greeting:
        remainder = cleaned[greeting.end():].strip(" ,.!-")
        remainder_tokens = [t for t in re.findall(r"[a-z]+", remainder.lower()) if t not in CROP_ONLY_FILLER]
        if not remainder or remainder.lower() in {"there", "agrobridge", "assistant", "sir", "madam"} or not remainder_tokens:
            return Turn("greeting", detect_crop(original), GREETING_REPLY, original)
        cleaned = remainder
    social = SOCIAL_RE.match(cleaned)
    if social and not cleaned[social.end():].strip(" ,.!-"):
        return Turn("social", detect_crop(original), SOCIAL_REPLY, original)

    lowered = cleaned.lower()
    words = re.findall(r"[a-z]+", lowered)
    if words and all(word in _SHORT_FILLERS for word in words):
        return Turn("clarification", detect_crop(original), NO_CROP_REPLY, cleaned)
    if any(re.search(rf"\b{re.escape(term)}\b", lowered) for term in LIVESTOCK_TERMS) or re.search(
        r"\bmy animals?\b|\banimal (health|disease|production|doctor)\b", lowered
    ):
        return Turn("livestock", None, LIVESTOCK_REPLY, cleaned)

    if any(re.search(pattern, lowered) for pattern in BACKCHANNEL_PATTERNS):
        return Turn("clarification", None, BACKCHANNEL_REPLY, cleaned)

    if any(re.search(pattern, lowered) for pattern in OUT_OF_SCOPE_PATTERNS):
        return Turn("out_of_scope", None, OUT_OF_SCOPE_REPLY, cleaned)

    if any(re.search(pattern, lowered) for pattern in CLARIFICATION_PATTERNS):
        return Turn("clarification", detect_crop(original) or crop_from_history(history), CLARIFY_REPLY, cleaned)

    crop = detect_crop(cleaned) or crop_from_history(history)
    if crop and _is_crop_only(cleaned, crop):
        return Turn("crop_only", crop, CROP_ONLY_TEMPLATE.format(crop=crop), cleaned)

    if not crop and any(
        re.search(rf"\b{re.escape(term)}\b", lowered) for term in NEEDS_CROP_TERMS
    ):
        return Turn("clarification", None, NO_CROP_REPLY, cleaned)

    if not crop:
        return Turn("general_crop_question", None, None, cleaned)

    intent: Intent = (
        "crop_problem"
        if any(re.search(rf"\b{re.escape(term)}\b", lowered) for term in PROBLEM_TERMS)
        else "crop_question"
    )
    return Turn(intent, crop, None, cleaned)
