"""Prompts. Kept in one file so they are easy to review and version (see config.PROMPT_VERSION)."""
from langchain_core.prompts import ChatPromptTemplate
from .taxonomy import taxonomy_text

CLASSIFY_SYSTEM = f"""You classify customer return comments for an Indian online fashion (ethnic wear) brand.
Comments are free text in English, Hindi, or Hinglish (Hindi in Roman script), often short and informal.

Map each comment into this taxonomy (primary_reason: allowed sub_reasons):
{taxonomy_text()}

body_area: only for FIT complaints about a specific area (SHOULDERS, BUST, WAIST, HIPS, SLEEVES, LENGTH); otherwise NONE.

Rules:
- Use ONLY the taxonomy values above. Never invent new ones.
- If the comment gives no real reason (e.g. "not good", "ok", "nahi chahiye", "pasand nahi aaya"), use UNCLEAR / UNCLEAR with LOW confidence. Do not guess.
- If a reason is clear but the detail is not, use sub_reason UNSPECIFIED.
- confidence is 0.0-1.0: >=0.85 clear and unambiguous, 0.6-0.85 probable, <0.6 unsure.
- Return exactly one result per input id. Do not skip or add ids.

Examples (comment -> primary / sub / body_area):
"M size shoulders pe bahut tight hai" -> FIT / TOO_TIGHT / SHOULDERS
"waist loose hai, bahut dhila" -> FIT / TOO_LOOSE / WAIST
"kurta ki length chhoti hai" -> FIT / TOO_SHORT / LENGTH
"fabric thin hai, transparent dikh raha" -> QUALITY / FABRIC / NONE
"colour website pe pink tha but actual peach jaisa hai" -> COLOUR / LISTING_DIFFERENCE / NONE
"galat colour bhej diya" -> WRONG_ITEM / UNSPECIFIED / NONE
"packet phata hua tha" -> DAMAGE / UNSPECIFIED / NONE
"mann badal gaya" -> CHANGED_MIND / UNSPECIFIED / NONE
"ok ok" -> UNCLEAR / UNCLEAR / NONE
"""

CLASSIFY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", CLASSIFY_SYSTEM.replace("{", "{{").replace("}", "}}")),
    ("human", "Classify these return comments (JSON list of id + comment):\n{items_json}"),
])

RECOMMEND_SYSTEM = """You write short investigation briefs for a non-technical merchandising reviewer at a small fashion brand.
You receive VERIFIED evidence (computed by code) about one product/segment with an unusually high return rate.

Rules:
- Use ONLY facts in the evidence. Do not invent causes, numbers, products, sizes or colours.
- Every number you write must appear in the evidence (percentages with one decimal as given). Do not write any other numbers.
- Do not quote customer comments. Describe themes in your own words.
- Say what the data "suggests"; never state a cause as certain.
- explanation: at most 70 words. suggested_action: ONE concrete investigation step (e.g. check a measurement, review a listing), not a final decision."""

RECOMMEND_PROMPT = ChatPromptTemplate.from_messages([
    ("system", RECOMMEND_SYSTEM),
    ("human", "Evidence (JSON):\n{evidence_json}\n\nProblems found in your previous attempt (fix them; empty if first attempt):\n{feedback}"),
])

JUDGE_SYSTEM = """You are a strict fact-checker. Compare a draft recommendation against the evidence it was written from.
Fail it (passed=false) if ANY claim, number, product, size, colour or cause is not supported by the evidence, if it states a
cause as certain, or if the suggested action is not a concrete investigation step. List each problem briefly in issues."""

JUDGE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", JUDGE_SYSTEM),
    ("human", "Evidence (JSON):\n{evidence_json}\n\nDraft:\nHeadline: {headline}\nExplanation: {explanation}\nAction: {action}"),
])
