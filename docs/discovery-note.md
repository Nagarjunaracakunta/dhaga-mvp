# Discovery Note: Dhaga & Co.

**Written up:** 3 October 2026. *The brief asks for this note to be dated before the first code commit (30 September 2026). It wasn't written down before then. Group to add when the discovery discussion took place.*
**Group:** _names_

Numbers marked **(brief)** are from the case study. Numbers marked **(calc)** are our arithmetic on brief numbers. Nothing else is assumed without saying so.

### 1. The problem in one sentence (the client's words)

> "Fifty-eight percent of tickets are some version of where is my order. My agents copy and paste the same four replies all day. Average first response is nine hours." (Arpita, Head of CX)

### 2. Who owns it today, and what they do instead

**Arpita, Head of CX.** 34 agents answer about 9,000 tickets a week on Freshdesk, plus a WhatsApp line through Gupshup **(brief)**. For each "where is my order" ticket an agent looks up the order, picks one of four canned replies from a shared document, and edits it by hand. Tickets are free text and tagged only "when agents remember" **(brief)**.

### 3. The evidence

- **Volume:** about 9,000 tickets a week, 58% of them "where is my order" **(brief)**, which is about 5,220 a week **(calc)**.
- **Speed:** the average first response is 9 hours **(brief)**.
- **Repetition:** agents use the same four replies all day **(brief)**, so the work is mostly lookup and copy.
- **The data exists and is clean:** orders are 11 million rows in Postgres with status history, "clean and trustworthy" **(brief)**. The answer to most of these tickets is already in a table.
- **The input is messy:** messages are free text, often Hinglish **(brief)**. That's a language problem, which is where a model earns its place.

### 4. What it costs them

- **Time:** a 9-hour first response, on about 5,220 near-identical tickets a week **(brief, calc)**. First response time is a metric Arpita already tracks and argues about.
- **Money we can't price yet:** agent minutes per ticket and agent cost aren't in the brief. That's our first question for Arpita.
- **Retention:** repeat purchase has been stuck at 22% for six quarters **(brief)**. A slow answer to "where is my order" is one plausible contributor. We note it as a hypothesis and don't claim it.

### 5. What success looks like, and how we measure it

| Measure | Data they already hold |
|---|---|
| First response time on "where is my order" tickets falls below 9 hours | Freshdesk timestamps |
| Agent handle time per routine ticket | Freshdesk, plus the time from draft to send in our log |
| Share of drafts sent without edits | Our `ai_interactions` log (approve / edit / reject) |
| No ticket that needs a person gets an automatic draft (lost parcel, damage, RTO) | Our log, checked against a labelled sample |

### 6. Ranked shortlist

We ranked by: a named owner losing something measurable today, size of the pain, whether the data exists, whether we can show it working end to end in the MVP, and the risk if it's wrong.

| Rank | Problem (owner) | Evidence (brief) | Why it sits here |
|---|---|---|---|
| **1** | **Support drowning in "where is my order"** (Arpita) | 9,000 tickets/week, 58% WISMO, 9-hour first response, same 4 replies | Named owner, measured pain, clean data that answers the question, a human approves every reply, and we can demo it end to end. **Built as CX Copilot.** |
| 2 | **"Other" returns hide the real reason** (Neha) | 31% return rate; 44% of returns tagged "Other"; she reads a few hundred by hand | Clear owner and data, but the value depends on what the category team does with the insight, which is slower to show. **Built as the second module, rules only so far.** |
| 3 | **COD return-to-origin** (Faizan) | 26% RTO on COD at about ₹120 each; 61% of orders are COD; 48,000 orders/week | **The biggest money:** about 48,000 × 61% × 26% ≈ 7,600 RTOs a week × ₹120 ≈ ₹9.1 lakh a week **(calc)**. Ranked below because the fix (predict risk, then confirm with the customer before dispatch) needs customer and address history we'd have to request, sends messages to customers, and can't be shown reducing RTO within an MVP. First in line for the next engagement. |
| 4 | **Slow, inconsistent product copy** (Vivek) | 200 descriptions/week by 4 people; tone drifts; sample to live takes 6–9 days | Easy to build, but copy is one step of a 6–9-day pipeline that includes the studio shoot. Faster copy alone may not move the drop calendar. Planned for phase 2 with reviews. |
| 5 | **410,000 reviews nobody reads** (no owner) | "Displayed and never analysed" | Nobody owns it today, so it's an idea rather than a problem. It becomes useful as an input to returns and product copy (phase 2). |
| 6 | **Analyst queue** (Karthik) | Requests wait about 2 weeks | Real, but a general "ask the data" tool is broad and risky to get wrong. Hard to scope as a small MVP. |

Ritu's retention (22%) and Sameer's acquisition cost (up 40%) are business outcomes these problems feed into, not problems to build for directly.

### 7. Our biggest assumption, and what would prove it wrong

**Assumption:** the 9-hour first response is driven mainly by the time agents spend on each repetitive ticket. A reviewed draft cuts that time enough to shorten the queue.

**What would prove it wrong:** Freshdesk data showing tickets wait hours before anyone opens them while handle time is already short. Then the bottleneck is staffing, shifts or routing, not writing replies. The fix would be auto-acknowledgement and better routing, not drafting. We would ask Arpita for one week of ticket timestamps (created, first opened, first replied) to check this before scaling.
