# Discovery Note: Dhaga & Co.

**Date:** _group to add when the discovery discussion took place (the first code commit was 30 Sep 2026; written up 3 Oct 2026)_ · **Group:** _names_
§ = section of the client brief · **(calc)** = our arithmetic on brief numbers

**1. The problem in one sentence**
> Customers tell us what's wrong in their own words, in tickets and in the Other box, and we can only read a few hundred at a time: first replies take nine hours and most returns go unexplained.

That's Arpita's "agents copy and paste the same four replies all day… nine hours" and Neha's "I can only read a few hundred at a time" (§05) in one sentence.

**2–4. Who owns it, the evidence, and what it costs**

| | Support (owner: Arpita, Head of CX) | Returns (owner: Neha, Category Head) |
|---|---|---|
| What they do today | 34 agents on Freshdesk and WhatsApp paste one of four canned replies; tickets tagged only "when agents remember" (§03, §04) | Reads "Other" return comments by hand (§05) |
| Evidence | 9,000 tickets/week, 58% "where is my order" (§04, §05), ≈ **5,220 a week** (calc) | 31% of orders returned, 44% marked "Other" (§04, §05) |
| Cost | **9-hour average first response** (§05), a number Arpita already tracks | 48,000 orders/week (§02) × 31% ≈ 14,880 returns, × 44% ≈ **6,550 unexplained returns a week** (calc), against "a few hundred" read |
| Data that already holds the answer | Orders: 11M rows with status history, "clean and trustworthy" (§04) | Return reason field plus the "Other" text (§04) |

Both arrive in free text, often Hinglish (§02, §06). Repeat purchase has been stuck at 22% for six quarters (§05). Slow support and unexplained returns may feed it; that's a hypothesis, not a claim.

**5. What success looks like, measured with data they already hold**

| | Measure | Their data | Proposed target, to agree with the owner |
|---|---|---|---|
| Support | First response on "where is my order" tickets | Freshdesk created vs first-reply times | Under 1 hour during a 2-week pilot, with no lost-parcel, damage or RTO ticket answered without a person |
| Returns | Share of returns with a usable reason | Returns table | Down from 44% unexplained to under 10% for pilot categories |
| Returns | Return rate of a flagged product, size or colour after its listing is fixed | Orders + returns | Lower than unchanged products over 6 weeks |

**6. Ranked shortlist** (H = high, M = medium, L = low)

| # | Problem (owner, §) | Measured pain | Data ready | Demoable | Risk if wrong | Why here |
|---|---|---|---|---|---|---|
| **1** | **Support swamped by "where is my order"** (Arpita, §05) | H | H | H | L | The answer is already in the orders table, and a person approves every reply |
| **2** | **Returns with no real reason** (Neha, §05) | H | M | M | L | Same fix as #1, one system; the payoff waits on the category team acting |
| 3 | COD return-to-origin (Faizan, §05) | **H: ≈ 7,600 RTOs × ₹120 ≈ ₹9.1 lakh/week** (calc) | L | L | H | Biggest money, but it needs customer and address history and messages customers before dispatch. Next engagement. |
| 4 | Slow product copy (Vivek, §04, §05) | M | H | H | M | 200 descriptions/week, but copy is one step of a 6–9 day pipeline that includes the shoot |
| 5 | Reviews nobody reads (no owner, §04) | L | H | H | L | No owner today: useful later as input to #2 and #4 |
| 6 | Two-week analyst queue (Karthik, §05) | M | H | L | H | A general "ask the data" tool is broad, and wrong numbers are costly |

**Why two, not one:** #1 and #2 are the same fix (read the customer's words, turn them into a reason, let a person decide) for two owners, built as one system. A ticket about a return links straight to that product's return history.

**7. Biggest assumption, and what would prove it wrong**
**Most important:** the 9-hour first response is caused by agents' time per ticket, not by tickets waiting unopened. **Wrong if** a week of Freshdesk timestamps shows tickets sit for hours before anyone opens them while handling is quick. Then staffing and routing are the fix, not drafted replies.
**Also:** "Other" comments hold a real reason, mostly fit as Neha believes. **Wrong if** 200 comments labelled by her team are mostly "ok" or "return karna hai". Then a better dropdown is the fix.
