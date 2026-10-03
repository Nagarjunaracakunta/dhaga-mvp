# Discovery note (DRAFT for the group to review and agree)

> Date: ____ (the brief requires this to pre-date the first commit; if code was already committed, say so honestly here, do not backdate)
> Page numbers refer to the FDE Academy brief "The Dhaga & Co. Engagement". **[brief]** = stated in the brief, **[assumed]** = our estimate.

**1. The problem, in the client's words.** "Returns are thirty-one percent overall. When I read the Other box by hand, most of it is about fit,
but I can only read a few hundred at a time." (Neha, Category Head, p.4)

**2. Who owns it today, and what they do instead.** Neha. She reads the "Other" free-text box by hand, a few hundred comments at a time, so most reasons are never read.

**3. Evidence.** 44% of returns land in "Other" (Returns row, p.3). Overall return rate 31% (Neha, p.4). About 48,000 orders a week (p.2).
Arithmetic: 48,000 x 31% = **14,880 returns/week**; x 44% = **6,547 "Other" returns/week** [brief]. At "a few hundred" (we assume 300) Neha covers **about 5%** of them [assumed].
Customers write in Hinglish (p.2, p.4), so keyword search does not work, and size charts differ per vendor (Catalogue row, p.3), which is a plausible cause of fit returns.

**4. What it costs them.** Cost per return is not in the brief (the Rs 120 quoted by Faizan is for return-to-origin on COD, a different flow), so we must ask for it.
What we can state: 14,880 returns a week are 31% of orders [brief], and about 6.5k a week carry reasons nobody reads. Every fit problem that stays invisible keeps recurring on
a live catalogue of 14,000 SKUs that is re-listed every Tuesday and Friday (p.1).

**5. What success looks like.** (a) Neha sees *all* ~6.5k weekly "Other" comments as ranked, evidence-backed briefs instead of ~300 read by hand.
(b) Agreement with Neha's own labels on a 300-comment sample, on trusted rows (proposed bar: 85%, to be agreed with her). (c) After a fix, the return rate of the flagged product/size
falls versus its own before-period, measured from the orders and returns tables they already hold (Postgres, p.3). (d) Cost per 1,000 comments, reported on every run.

**6. Ranked shortlist (read first, choose second).**

| # | Problem (owner) | Evidence | Why it sits here |
|---|---|---|---|
| 1 | **High returns hidden in "Other"** (Neha) | 44% Other; 31% returns; "only a few hundred at a time" | Named owner who says it herself. The data is already held. The blocker is reading capacity on messy Hinglish, which is language work a model is suited to. Internal use, so a human-review step is natural. Success is measurable with existing metrics |
| 2 | **"Where is my order" tickets** (Arpita) | 58% of ~9,000 weekly tickets = ~5,200/week; 9-hour first response | Big, measurable and owned. But the core fix is order-status lookup plus templated replies (not model work), needs integration the brief puts out of scope, and replies are customer-facing |
| 3 | **COD return-to-origin** (Faizan) | 26% RTO, ~Rs 120 each; 61% of orders are COD | Most quantifiable money: 48,000 x 61% x 26% x Rs 120 = **about Rs 9.1 lakh/week** (assumes 26% applies to COD orders) [brief numbers, our arithmetic]. Ranked lower because the lever is prediction or order-confirmation outreach, which needs data the brief does not describe and ML skills Dhaga does not have (Dev, p.4) |
| 4 | **Slow, inconsistent listing** (Vivek) | 6-9 days sample to live; colour typed ~90 ways; 4 people hand-write ~200 descriptions a week | Strong model fit (extraction, copy) and an owner, but output is customer-facing (needs designed review), and the cost of a slipped drop is not quantified in the brief |
| 5 | **410,000 unread reviews** | "Nobody reads them" | Same text-analysis shape as #1, but no named person is losing something today. Natural extension of #1's pipeline |
| 6 | **Repeat purchase stuck at 22%** (Ritu) | 22% for six quarters | An outcome, not a problem: many causes, no single fix to build in an MVP |

**7. Biggest assumption, and what would prove it wrong.** That the "Other" comments are mostly fit and concentrated enough in specific products and sizes that fixing a size chart or listing would cut returns (Neha's belief, p.4; not yet tested).
It is wrong if, on a hand-labelled sample of 300 to 500 "Other" comments, fit is well under half of them (proposed cut-off: 40%), or if the top flagged product/size segments explain only a small share of fit returns (the briefs would not be actionable).
The cheapest test is exactly that: Neha labels 300 comments, we compare.

**Still to ask the client:** cost per return (reverse pickup, inspection, resale loss), whether 31% is of orders, what fraction of "Other" has a comment, and who acts on a flagged product (listing team? vendor?).
