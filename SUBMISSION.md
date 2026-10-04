# Submission

| | |
|---|---|
| Category | Standalone Intelligent Contracts |
| Title | Credo: identity-bound credit standing to collateral quotes |
| One-line thesis | Credo is a reusable GenLayer primitive that binds a borrower's address to a public identity by proof of control, judges that identity's standing from public evidence against an immutable lender policy, and exposes deterministic, freshness-aware collateral terms for lending contracts. |
| Repository | https://github.com/s70239176-ctrl/Credo |
| Canonical Studionet address | `0x70189B81E0Bd90ba29AaBBbB1fdA11380D599592` |
| Explorer URL (contract) | https://explorer-studio.genlayer.com/address/0x70189B81E0Bd90ba29AaBBbB1fdA11380D599592 |
| Deployment tx | `0x6eabb7ad6fcd4d4fd3095662a2ba979f4683ecdee975aae3815a15595241ecbf` (FINALIZED) |
| Deployment source | `contracts/credo.py`, git blob `8f0a0f9d15f171a83a8db0afbe5b5225a63e5efa`, byte-identical to the code read back from the chain |

## Portal description (753 characters)

Credo is a standalone GenLayer Intelligent Contract for under-collateralized lending. A borrower proves control of a public identity page; validators independently judge public evidence against a lender's immutable policy and must reproduce each claim with a verbatim quote from their own fetch. Deterministic code then derives tiers, freshness, repayment-history lift and default lockout, and exposes quote()/meets() so lenders demand less collateral without trusting one KYC provider. No funds, no frontend. Verified: 202 Direct Mode tests incl. forged-leader cases, GenVM lint and SDK validation, 4 live Studionet integration tests, and a canonical Studionet deployment (0x70189B81E0Bd90ba29AaBBbB1fdA11380D599592) whose full flow was exercised live.

## Why GenLayer is required

Without GenLayer one party (the lender's backend, a KYC vendor or the borrower) chooses the evidence, reads it and authors the
verdict. Here independent validators each fetch the pages themselves and must reproduce the leader's finding, including
a quote present in their own snapshot. See [DECISION.md](DECISION.md) and [docs/CONSENSUS.md](docs/CONSENSUS.md).

## Consensus mechanism

One `run_nondet_unsafe` observation (identity page plus up to 4 evidence pages). Validators type-check the proposal,
re-observe independently, require equality on reachability, binding proof/control/subject, per-source subject and
backlink, and every criterion's met bit, and require every relied-on quote to exist in their own snapshot.

## Deterministic responsibilities

URL/evidence admission, challenge and backlink presence, quote grounding, registrable-domain independence, corroboration
floors, required criteria, score, tiers, collateral and rate discount, freshness, cooldowns, reporter authorisation,
replay protection, repayment-history lift, default lockout.

## Failure policy

Fail closed: unparsable output, unknown enums, ungrounded quotes and missing proof never become a positive. Outages are
`INCONCLUSIVE` and change nothing; lost proof moves the binding to `LOST`; validator disagreement leaves the transaction
`UNDETERMINED` and state unchanged.

## Reuse surface

`quote(borrower, policy_id, as_of_ts)` and `meets(borrower, policy_id, as_of_ts, expected_policy_hash, max_collateral_bps)`.
A pool, a credit line and a treasury can use them unchanged. See [docs/INTEGRATION.md](docs/INTEGRATION.md).

## Test results

* Direct Mode: 202 passed (pickling checks on), including 56 forged-leader and malformed-proposal tests.
* Mutation check: 13 of 13 deliberate breakages of security-critical rules caught.
* `genvm-lint` 0.11.0: lint passed, SDK `check` passed (15 methods).
* Studionet integration: 4 passed (real consensus, disposable deployments).

## Live evidence

Canonical flow against the contract above (all 9 transactions ACCEPTED / MAJORITY_AGREE): a stranger's challenge in a
guestbook was refused; an owner-controlled page verified; a prompt-injection page earned tier 0; genuine evidence earned
tier 2 and a quote of 8000 bps against a 15000 bps base; two repayments lifted it to 5000 bps; a default blocked the
borrower; revoking the binding dropped all standing. All 29 transactions on the canonical contract read back FINALIZED. A separate live check removed the proof from an identity page and the binding moved to LOST. Transaction table: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Limitations

Not government KYC; approximate registrable-domain independence; `require_backlink` and stale-expiry proven in Direct Mode only; model
variance can yield `UNDETERMINED`; Studionet is a development network. Full list: README and
[docs/SECURITY.md](docs/SECURITY.md).

## Reviewer fast path

```bash
PYTHONPATH=. .venv-test/Scripts/python -m pytest tests/direct -q -p tests.support.win_direct_shim   # Windows; omit -p elsewhere
genvm-lint check contracts/credo.py
CANONICAL_ADDRESS=0x70189B81E0Bd90ba29AaBBbB1fdA11380D599592 gltest tests/evidence/ -v -s --network studionet
```
