# Credo

**Consensus-attested credit standing that turns a public identity into collateral terms.**

Credo is a standalone GenLayer Intelligent Contract. A borrower proves control of a public identity page, validators
independently judge that identity's standing from public evidence against a lender's immutable policy, and lending
contracts read a deterministic quote: how much collateral to demand and what rate discount is earned. It holds no
funds, has no admin key, and ships no frontend.

> Official GenLayer idea: *Under-collateralized Lending. Enable lending with less collateral by linking real-world
> identity to on-chain reputation, allowing borrowers to leverage their good standing for better loan terms.*

## Canonical deployment (Studionet)

| | |
|---|---|
| Network | GenLayer Studionet, chain id 61999, RPC `https://studio.genlayer.com/api` |
| Contract | `0x70189B81E0Bd90ba29AaBBbB1fdA11380D599592` |
| Explorer | https://explorer-studio.genlayer.com/address/0x70189B81E0Bd90ba29AaBBbB1fdA11380D599592 |
| Deployment tx | `0x6eabb7ad6fcd4d4fd3095662a2ba979f4683ecdee975aae3815a15595241ecbf` |
| Deployment status | **FINALIZED** (observed via RPC) |
| Source parity | **MATCH**: code read back from the chain is byte-identical to `contracts/credo.py` (git blob `8f0a0f9d15f171a83a8db0afbe5b5225a63e5efa`) |

Details and the live transaction table: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## What is verified

| Gate | Result |
|---|---|
| Direct Mode (`tests/direct`) | **202 passed**, 0 failed (pickling checks on) |
| Mutation check of the security-critical rules | 13 of 13 deliberate breakages caught by the suite |
| `genvm-lint lint` (0.11.0) | passed (3 checks) |
| `genvm-lint check` | passed, 15 methods (8 view, 7 write) |
| Studionet integration (`tests/integration`) | **4 passed**, real consensus, disposable deployments |
| Canonical live flow (`tests/evidence`) | passed against the canonical contract; 9 recorded transactions `ACCEPTED` / `MAJORITY_AGREE`, and all 29 transactions on the contract later read back as `FINALIZED` |
| Live `BINDING_LOST` (`tests/evidence/test_binding_lost_live.py`) | passed in two phases: proof removed from the page, binding went `LOST`, quote `UNBOUND` |

Environment: Python 3.14.3, genlayer-test 0.29.2, genlayer-py 0.16.3, GenVM SDK v0.2.16.
Two host-only test plugins are used on this Windows machine and are not part of the contract; see
[Reproducing the results](#reproducing-the-results).

## The problem

Under-collateralized lending needs three things a normal contract cannot produce alone: a trustworthy link between
an address and a real-world identity, a judgment of that identity's standing from messy public evidence, and a
collateral requirement derived from both plus repayment history. Today one party supplies them: the lender's
backend, a KYC vendor, or the borrower. Whoever supplies them decides who gets cheap credit.

## Why GenLayer, and what breaks without it

Remove GenLayer and one party becomes the authority that chooses the evidence, reads it, and authors the verdict.
With GenLayer, independent validators each fetch the identity page and the evidence pages themselves and must
reproduce the leader's finding, including a verbatim quote that exists in *their own* snapshot. The borrower
cannot pick the judge and the lender cannot pick the verdict. A deterministic contract cannot read a web page, and a
single LLM or API makes its operator the trusted reporter.

## How it works

```text
lender    create_policy(spec)           immutable, fingerprinted: criteria, tiers, ttl, reporters, lockout
borrower  begin_binding(url, name)      -> "credo-bind:<address>:<id>" challenge
          (publish the challenge on a page only you control)
borrower  verify_binding()              validators confirm proof of control      -> VERIFIED
borrower  assess(policy, [evidence])    validators judge public evidence         -> QUALIFIED / UNQUALIFIED
reporter  record_outcome(...)           REPAID / DEFAULTED history, per policy
lender    quote(borrower, policy, now)  status + collateral_bps + rate_discount_bps
```

### State machine

```text
binding:  PENDING --verify--> VERIFIED --revoke--> REVOKED
                     |             \--assess finds proof gone / not owner-controlled--> LOST
                     \--rejected: stays PENDING (10 attempts)
assess:   QUALIFIED | UNQUALIFIED | INCONCLUSIVE (outage, nothing changes) | BINDING_LOST
quote:    OK | UNBOUND | UNATTESTED | STALE | BLOCKED | POLICY_INACTIVE
```

### Nondeterministic operations (only where irreducible)

| Call | Where | Why it cannot be deterministic |
|---|---|---|
| `run_nondet_unsafe` observation | `verify_binding`, `assess` | live web pages, and judgments about owner-controlled vs visitor-writable content, same entity vs namesake, and whether a page supports a plain-English criterion |

### Deterministic responsibilities (the larger surface)

URL and evidence admission, challenge presence, name presence, backlink presence, quote grounding, registrable-domain
independence, the `min_sources` corroboration floor, required criteria, weighted score, tier lookup, collateral and
rate-discount terms, freshness, cooldowns, attempt caps, reporter authorisation, replay protection, the
repayment-history tier lift, the default lockout, and the single `quote` derivation.

### Equivalence and validator design

Every validator re-fetches and re-judges. The proposal must pass a strict shape check (no truthy-string booleans, no
unknown enums, exact keys), must match on the decision-critical fields (page reachability, binding
`found`/`control`/`subject`, per-source `subject`, `linked`, and every criterion's `met` bit), and every quote the
leader relied on must exist in the validator's own snapshot. Under-claiming is rejected as well as over-claiming.
Quote wording and prose are not compared. Full detail: [docs/CONSENSUS.md](docs/CONSENSUS.md).

### Failure semantics (fail closed)

Unparsable model output, unknown enums, ungrounded quotes and missing proof never become a positive. A page outage is
`INCONCLUSIVE` and changes nothing; a reachable page that no longer carries the proof moves the binding to `LOST`.
Validator disagreement leaves the transaction `UNDETERMINED` and state unchanged. See
[docs/SECURITY.md](docs/SECURITY.md).

## Reuse surface

A lending pool, a credit line and a treasury can all use the same two views without touching the web or a model:

```python
q = ICredo(credo).view().quote(borrower, policy_id, now)      # status, collateral_bps, rate_discount_bps, ...
ok = ICredo(credo).view().meets(borrower, policy_id, now, expected_policy_hash, max_collateral_bps)
```

Pin the policy hash you reviewed. Everything other than `status == "OK"` already returns the policy's base
collateral. Worked example and the policy format: [docs/INTEGRATION.md](docs/INTEGRATION.md).

## Limitations (please read)

* Not government KYC. It proves control of a public identity page and public evidence about it. A person can hold
  several identities; Credo does not stop that beyond requiring independent, backlinked evidence.
* A borrower who controls a page named after a famous person can claim that name. `require_backlink: true` defeats
  the straightforward attack by requiring evidence pages to link to the bound page; a policy that sets it to `false`
  accepts the risk. The live tests use `false` (the identity page is generated at run time), so the backlink rule is
  proven in Direct Mode only. Stale-attestation expiry is also proven in Direct Mode only (1-hour minimum TTL).
* Registrable-domain independence is approximate (built-in list of second-level suffixes). Pages are truncated to
  8,000 characters after tag stripping. Honest validators can disagree on borderline pages; the result is an
  `UNDETERMINED` transaction, and the borrower retries after the cooldown.
* Reporters can lie about their own policy's loans; the blast radius is bounded by the policy and by the consumer
  pinning the policy hash.
* The example consumer in the docs passes `genvm-lint` but has not been executed on a network.
* Studionet is a development network, and this is not a production audit. The canonical transactions were first
  observed `ACCEPTED`, and a later read showed all of them `FINALIZED`.

## Repository layout

```text
contracts/credo.py            the one deployable contract
tests/direct/                 Direct Mode (mocked web and LLM, real contract code), incl. forged-leader tests
tests/integration/            Studionet real-consensus tests (disposable contracts)
tests/evidence/               records live evidence against the canonical contract
tests/support/                host-only test plugins (not contract code)
fixtures/evidence/            public pages for a fictional "Ada Fixture", served via jsDelivr
docs/                         CONSENSUS, SECURITY, INTEGRATION, DEPLOYMENT
DECISION.md  SUBMISSION.md    why this primitive; copy-ready submission text
```

## Reproducing the results

```bash
python -m venv .venv-test && .venv-test/Scripts/pip install -r requirements-test.txt     # POSIX: .venv-test/bin
# Direct Mode. On Windows add the host plugin (genlayer-test 0.29.2's loader cannot unlink a temp file there):
PYTHONPATH=. .venv-test/Scripts/python -m pytest tests/direct -q -p tests.support.win_direct_shim

python -m venv .venv-lint && .venv-lint/Scripts/pip install genvm-linter
genvm-lint lint contracts/credo.py && genvm-lint check contracts/credo.py                # set PYTHONUTF8=1 on Windows

# Live (real validators, disposable contracts):
gltest tests/integration/ -v -s --network studionet
# On a host with a flaky route to Cloudflare add: CREDO_HOST_NET_FIX=1 PYTHONPATH=. ... -p tests.support.host_net_shim

# Canonical evidence (appends policies/bindings to the canonical contract; that is the evidence):
CANONICAL_ADDRESS=0x70189B81E0Bd90ba29AaBBbB1fdA11380D599592 gltest tests/evidence/ -v -s --network studionet
```

The two host plugins change no contract code and no assertion. `win_direct_shim` replaces one temp-file helper in the
test loader. `host_net_shim` (opt-in) filters name resolution to IPv4 and retries only `ConnectTimeout`, in the test
process only; it exists because this host's IPv6 route to Cloudflare is black-holed.
