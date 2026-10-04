# Decision record

## Mission

Build a standalone GenLayer Intelligent Contract for the official idea **"Under-collateralized Lending: enable
lending with less collateral by linking real-world identity to on-chain reputation, allowing borrowers to
leverage their good standing for better loan terms."**

The repository was empty at the start (state A), so the primitive was scouted rather than inherited. The topic
was fixed by the task; the decision below is *which primitive inside that topic* is worth building.

## What a lending contract actually cannot do alone

An under-collateralized loan needs three things a normal contract cannot produce by itself:

1. **A link between an address and a real-world identity** that nobody can forge or hand-assign.
2. **A judgment of standing** from public, messy, natural-language evidence ("is this person an officer of a real
   organisation, for how long, vouched by whom?").
3. **A collateral requirement derived from (1) and (2)**, plus repayment history, that every lender can read
   without re-implementing the machinery.

Credo supplies exactly that and nothing else. It never holds funds.

## Portfolio collision map (owner repositories reviewed)

I listed every repository of the owner (`gh`-equivalent REST listing, 70+ repos) and read the README of each
repository that could plausibly share a lane.

| Repo | Core trust question | Evidence | Stateful primitive | Same lane as Credo? |
|---|---|---|---|---|
| Tally (`UptimeSLA`) | Did an API meet its SLA? | live HTTP probes | probe ring + claims | No. Observes a service, not a person. Shares the consumer-gate pattern only. |
| Cross-Model-Commitment-Receipt | Did a frozen claim about the world come true? | primary sources | commitments | No. Adjudicates one claim, no identity, no tiers. |
| APPS-Oracle | Did a parametric event occur? | multi-source web | one agreement per instance | No. |
| intelligent-escrow-protocol, DeliverableQA, Splitbench, RfpFit | Did a deliverable meet a brief? | submitted artifact | escrow + verdict | No. They move money on deliverable quality; Credo prices *risk before* a loan. |
| BlameCourt | Which agent is at fault? | workflow evidence | fault split | No. |
| OpenNotum | What did a public page say at a time? | fetched pages | receipt | Adjacent: both fetch pages. Credo uses pages as identity proof and standing evidence, with policy scoring. |
| ParcelCourt, SkyVerdict, Resolve, Parish | parcel condition, flight delay, market outcome | web facts | claim/market | No. |
| SemanticDuplicateRegistry | Is a submission a semantic duplicate? | registry contents | dedup registry | No. |
| circle-court, Arc Resolut, ArcRelay | disputes / agent payments (apps) | n/a | n/a | No (applications, not primitives). |
| Meridian | cross-chain escrow adjudication | submitted evidence | escrow | No. |

No existing repository decides *standing* or *identity binding*, and none exposes a collateral quote.

## Ecosystem collision map

Checked the official GenLayer "ideas", "when to use GenLayer" and "typical use cases" pages on the build date.

* The ideas list contains **On-chain Identity Verification** (social-profile challenge message linked to an
  on-chain account) and **Under-collateralized Lending** as separate entries. Credo composes the first into the
  second on purpose: identity binding by challenge message is a *component* here, not the product.
* The "typical use cases" page lists reputation updates and policy evaluation as fitting GenLayer. Credo is a
  reputation/standing primitive with a deterministic tier table, which is the part those pages leave open.
* I did not find a reusable credit-standing quote primitive in the official examples. This is a statement about
  what I looked at, not a guarantee that none exists in the wider community.

## Candidates considered

Scored 0 to 10 against the prompt's twelve axes, summarised here as five columns:
**N** = GenLayer necessity, **E** = independently checkable evidence, **R** = reuse across unrelated consumers,
**S** = state/safety design depth, **T** = live testability on Studionet. (Novelty against the portfolio is
described in the verdict.)

| # | Candidate | N | E | R | S | T | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | **Credo: identity-bound standing to collateral quote with repayment history** | 9 | 8 | 9 | 9 | 8 | **Selected** |
| 2 | On-chain credit score from wallet history only | 2 | 9 | 7 | 6 | 9 | Rejected: fully deterministic, a normal contract does it. |
| 3 | KYC attestation oracle (passport/bank documents) | 6 | 1 | 6 | 5 | 3 | Rejected: load-bearing evidence is private; validators cannot check it. |
| 4 | Income verification from uploaded statements | 6 | 1 | 5 | 5 | 3 | Rejected: private evidence, only one party can produce it. |
| 5 | Loan default adjudication court | 8 | 6 | 6 | 7 | 6 | Rejected: same lane as the owner's escrow/dispute repos. |
| 6 | Social vouching / web-of-trust staking pool | 5 | 3 | 6 | 6 | 5 | Rejected: collusion and sybil attacks dominate, and there is no external evidence to ground vouches. |
| 7 | SME business-health monitor from public pages | 7 | 6 | 6 | 6 | 6 | Rejected: periodic-observation shape duplicates Tally. Credo's `assess` can take such pages as evidence. |
| 8 | Real-world collateral appraisal from listings | 7 | 5 | 6 | 6 | 5 | Rejected: market-data oracle, different problem, unstable evidence. |
| 9 | Identity binding only (challenge message to address) | 6 | 8 | 7 | 4 | 8 | Rejected as a product: too thin, it is already an official idea. Kept as a component. |
| 10 | Credit-record dispute and appeal desk | 8 | 6 | 5 | 7 | 5 | Rejected: appeals lane, overlaps adjudication repos, and needs a mature record first. |
| 11 | Loan covenant compliance monitor | 7 | 6 | 5 | 7 | 5 | Rejected: overlaps the commitment-receipt lane. |
| 12 | Cross-lender repayment ledger only | 2 | 9 | 7 | 5 | 9 | Rejected as a product: deterministic. Kept as a component (reporter-written ledger). |

## Selected primitive: Credo

> Credo is a reusable GenLayer primitive that binds a borrower's address to a public identity by proof of control,
> judges that identity's standing from public evidence against an immutable lender policy, and exposes
> deterministic, freshness-aware collateral terms so lending contracts can demand less collateral without trusting
> any single KYC provider.

### Delete-GenLayer test

Remove GenLayer and one party becomes the authority. Either the lender's own backend decides who "is" the person
and whether they are in good standing (so it can favour or exclude anyone and nobody can audit the reading of the
evidence), or a single KYC vendor does. With GenLayer, independent validators each fetch the identity page and the
evidence pages themselves and must reproduce the leader's finding, including a verbatim quote that exists in
*their own* snapshot. The borrower cannot choose the judge; the lender cannot choose the verdict.

### Three-consumer test

Three materially different contracts can use the same `quote` / `meets` interface unchanged:

1. A **lending pool** that sets a per-loan collateral ratio.
2. A **credit-line / BNPL contract** that sets a rate discount from `rate_discount_bps`.
3. A **marketplace or DAO treasury** that lets only fresh, unblocked, qualified members post a smaller performance
   bond or receive an advance.

### Machine-readable output

`quote` returns a status enum (`OK`, `UNBOUND`, `UNATTESTED`, `STALE`, `BLOCKED`, `POLICY_INACTIVE`), integer
`collateral_bps`, `rate_discount_bps`, tier numbers, the policy fingerprint and the expiry. No prose.

### Model-is-not-the-contract test

The model never decides money or tiers. It answers only: *"does this page support this criterion (with a verbatim
quote)?"*, *"is this page about the named subject?"*, and *"is the challenge in owner-controlled content?"*.
Admission, origin independence, corroboration floors, required criteria, score, tier, collateral, freshness,
history lift and default lockout are deterministic code over the consensus-agreed observations.

### Hardest technical risk

Validator agreement on LLM extraction. Mitigations: narrow factual criteria, an equality rule only over the
decision-critical fields (reachability, subject match, per-criterion met bits), quotes that must be grounded in
each validator's own snapshot, and fail-closed handling of every disagreement (a protocol-level undetermined
transaction changes no state).

## Design choices worth defending

* **No funds.** Money movement would add a settlement surface without adding to the trust property. Lenders keep
  custody and read a quote.
* **No private data.** Identity is *public control of a public page*, never documents. A page bound to an address
  must contain a challenge derived from that address; a challenge in a comment box is rejected by the validators'
  owner-control judgment.
* **Honest scope of "real-world identity".** Credo proves control of a persistent public identity (a profile, site
  or organisation page) plus public evidence about it. It is not government KYC and does not claim to be.
* **Evidence must be independent of the identity page.** Evidence from the same registrable domain as the bound
  page is rejected at admission; corroboration counts distinct registrable domains.
* **Quotes are the audit trail.** A criterion counts only if its quote is a substring of the validator's own
  fetched page. A leader cannot invent support.
* **Outages are not downgrades.** Unreachable pages return `INCONCLUSIVE` and leave the prior attestation untouched.
  A page that is reachable but no longer carries the proof moves the binding to `LOST` (fail closed).
* **History is bounded and reporter-gated.** Only reporters named in the immutable policy can write repayments or
  defaults; history can lift at most `max_history_steps` (<= 2) tiers and can never lift a borrower whose attested
  tier is 0.

## Why this belongs in standalone Intelligent Contracts

One contract, no frontend, no backend, no funds. It is infrastructure that other contracts call, with the
trust model carried entirely by consensus and deterministic code.
