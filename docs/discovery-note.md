# Discovery Note: Dhaga & Co.

**Written up:** 3 October 2026. *The brief asks for this note to be dated before the first code commit (30 September 2026). It wasn't written down before then. Group to add when the discovery discussion took place.*
**Group:** _names_

Numbers marked **(brief)** are from the case study. Numbers marked **(calc)** are our arithmetic on brief numbers.

### 1. The problem, in the client's words

Two people are reading customer free text by hand, and neither can keep up:

> **A.** "Fifty-eight percent of tickets are some version of where is my order. My agents copy and paste the same four replies all day. Average first response is nine hours." (Arpita, Head of CX)
>
> **B.** "Returns are thirty-one percent overall. When I read the Other box by hand, most of it is about fit, but I can only read a few hundred at a time." (Neha, Category Head)

**One root cause:** customers tell Dhaga what's wrong in Hinglish free text (9,000 tickets a week, the "Other" box on 44% of returns), and nothing turns that text into something a team can act on.

### 2. Who owns it today, and what they do instead

| | Owner | What they do today (brief) |
|---|---|---|
| **A. Support** | Arpita, Head of CX | 34 agents on Freshdesk and WhatsApp look up each order and paste one of four canned replies. Tickets are tagged only "when agents remember". |
| **B. Returns** | Neha, Category Head | Reads "Other" return comments by hand, a few hundred at a time. 44% of returns carry no usable reason. |

### 3. The evidence

- **A:** about 9,000 tickets a week, 58% "where is my order" **(brief)**, so about 5,220 a week **(calc)**. First response is 9 hours **(brief)**.
- **B:** a 31% return rate, with 44% of returns in "Other" **(brief)**. Neha's own reading says most of them are about fit **(brief)**.
- **Both:** the input is free text and often Hinglish **(brief)**. The facts needed to act already exist: orders are "clean and trustworthy" (11 million rows with status history), and returns are captured with a reason field **(brief)**.

### 4. What it costs them

- **A:** a 9-hour first response on about 5,220 near-identical tickets a week **(brief, calc)**. Agent cost per ticket isn't in the brief; it's our first question for Arpita.
- **B:** 31% of orders come back **(brief)**, and for 44% of those Dhaga can't say why, so it can't fix the product, the size chart or the photo. The cost of one return isn't in the brief; it's our first question for Faizan.
- **Shared:** repeat purchase has been stuck at 22% for six quarters **(brief)**. Slow support and repeated bad buys are plausible contributors. We note this as a hypothesis, not a claim.

### 5. What success looks like, and how we measure it

| Problem | Measure | Data they already hold |
|---|---|---|
| A | First response time on "where is my order" tickets falls below 9 hours | Freshdesk timestamps |
| A | Share of drafts sent without edits; no risky ticket (lost parcel, damage, RTO) auto-drafted | Our `ai_interactions` log |
| B | Share of returns with no usable reason falls from 44% | Returns table, after classifying "Other" |
| B | Products, sizes and colours flagged for a fix, and their return rate after the fix | Orders + returns tables |

### 6. Ranked shortlist

Ranked by: a named owner losing something measurable today, size of the pain, whether the data exists, whether we can show it working end to end, and the risk if it's wrong.

| Rank | Problem (owner) | Evidence (brief) | Why it sits here |
|---|---|---|---|
| **1** | **Support drowning in "where is my order"** (Arpita) | 9,000 tickets/week, 58% WISMO, 9-hour first response | Measured pain, clean data that answers the question, a person approves every reply, demoable end to end. **Built: CX Copilot.** |
| **2** | **Returns with no real reason** (Neha) | 31% returns, 44% "Other", read by hand | Same root cause and same method as #1, sharing one reason taxonomy and pipeline. Ranked below #1 because the payoff depends on the category team acting on what we find, which takes longer to show. **Built: Returns Insights.** |
| 3 | **COD return-to-origin** (Faizan) | 26% RTO on COD at about ₹120 each; 61% COD; 48,000 orders/week | **The biggest money:** about 7,600 RTOs a week × ₹120 ≈ ₹9.1 lakh a week **(calc)**. Ranked third because it needs customer and address history we'd have to request, sends messages to customers before dispatch, and can't be shown reducing RTO inside an MVP. First in line for the next engagement. |
| 4 | **Slow, inconsistent product copy** (Vivek) | 200 descriptions/week by 4 people; 6–9 days from sample to live | Easy to build, but copy is one step of a pipeline that includes the studio shoot. Planned for phase 2, fed by what #2 and reviews find. |
| 5 | **410,000 reviews nobody reads** (no owner) | "Displayed and never analysed" | No owner today, so an idea rather than a problem. Useful as an input to #2 and #4. |
| 6 | **Analyst queue** (Karthik) | Requests wait about 2 weeks | Real, but a general "ask the data" tool is broad and risky to scope as an MVP. |

**Why two, not one:** #1 and #2 are the same capability, reading Hinglish free text into a fixed reason, applied to two owners. Building both shows the method generalises without doubling the system: one backend, one taxonomy, one review step. A support ticket about a return links straight to that product's returns view.

### 7. Biggest assumptions, and what would prove them wrong

- **A:** the 9-hour first response is driven by agent handling time, not queue waiting. **Wrong if** Freshdesk shows tickets sit unopened for hours while handle time is short; then routing and staffing are the fix, not drafting. **Check:** one week of created / first opened / first replied timestamps.
- **B:** the "Other" comments carry a real, classifiable reason, mostly fit as Neha believes. **Wrong if** a hand-labelled sample of 200 "Other" comments is mostly unclassifiable ("ok", "return karna hai"); then the fix is a better dropdown, not a classifier. **Check:** Neha's team labels 200 comments before we scale.
