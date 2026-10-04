# Integrating Credo

A lending contract needs **no web access, no model, no equivalence principle and no parsing** to use Credo. It
makes one view call and reads integers.

## The interface

```python
@gl.contract_interface
class ICredo:
    class View:
        def quote(self, borrower: str, policy_id: int, as_of_ts: int) -> dict: ...
        def meets(self, borrower: str, policy_id: int, as_of_ts: int,
                  expected_policy_hash: str, max_collateral_bps: int) -> bool: ...
    class Write:
        pass
```

`quote` returns:

| Key | Meaning |
|---|---|
| `status` | `OK`, `UNBOUND`, `UNATTESTED`, `STALE`, `BLOCKED`, `POLICY_INACTIVE` |
| `collateral_bps` | collateral to demand, in basis points of principal. **Equals the policy's base collateral for every status other than `OK`**, so a pool needs no special case. |
| `rate_discount_bps` | rate discount earned (0 unless `status == OK`) |
| `reduced` | `True` only when `status == OK` and `collateral_bps < base` |
| `attested_tier`, `history_steps`, `effective_tier` | how the tier was derived (attestation tier plus repayment-history lift) |
| `score_bps` | weighted standing score from the last assessment |
| `policy_hash` | fingerprint of the exact policy the attestation was made under |
| `expires_ts`, `binding_id` | freshness and which identity binding backs it |

`meets(...)` is the one-call gate: fresh, unblocked, bound, assessed under exactly `expected_policy_hash`, and
`collateral_bps <= max_collateral_bps`.

## Pass your own clock

Views take `as_of_ts` because a view cannot be trusted to know "now". Pass the consumer's **own transaction
time**, never a caller-supplied value:

```python
now = int(datetime.datetime.fromisoformat(gl.message_raw["datetime"].replace("Z", "+00:00")).timestamp())
```

## A complete consumer

This contract passes `genvm-lint lint` and `genvm-lint check` (static validation; it has not been executed on a
network). It is shown for illustration and is **not** part of this repository's deployable surface.

```python
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
import datetime

from genlayer import *


@gl.contract_interface
class ICredo:
    class View:
        def quote(self, borrower: str, policy_id: int, as_of_ts: int) -> dict: ...
        def meets(self, borrower: str, policy_id: int, as_of_ts: int,
                  expected_policy_hash: str, max_collateral_bps: int) -> bool: ...
    class Write:
        pass


class CreditGate(gl.Contract):
    credo: Address
    policy_id: u256
    policy_hash: str

    def __init__(self, credo: str, policy_id: int, policy_hash: str):
        self.credo = Address(credo)
        self.policy_id = u256(policy_id)
        self.policy_hash = policy_hash

    @gl.public.write
    def required_collateral(self, principal: int) -> int:
        now = int(datetime.datetime.fromisoformat(
            gl.message_raw["datetime"].replace("Z", "+00:00")).timestamp())
        borrower = gl.message.sender_address.as_hex.lower()
        q = ICredo(self.credo).view().quote(borrower, int(self.policy_id), now)
        if q["policy_hash"] != self.policy_hash:
            raise gl.vm.UserError("EXPECTED: borrower was not assessed under the policy this pool accepts")
        return principal * q["collateral_bps"] // 10_000
```

Always pin the **policy hash** you reviewed. A policy is immutable and fingerprinted
(`sha256(owner || canonical spec)`), so a different policy, even from the same owner, has a different hash. Without
the pin, a borrower could create their own lenient policy and a colluding "reporter".

## Three unrelated consumers

1. **Lending pool.** `collateral = principal * collateral_bps / 10000`.
2. **Credit line / BNPL.** `rate = base_rate * (10000 - rate_discount_bps) / 10000`.
3. **Marketplace or DAO treasury.** `meets(..., max_collateral_bps)` as a membership gate for a smaller
   performance bond.

## Writing repayment history

Only addresses listed in the policy's `reporters` can call
`record_outcome(borrower, policy_id, loan_ref, "REPAID" | "DEFAULTED")`. Typical use: the lending pool contract is
the reporter and calls it when a loan closes. `loan_ref` is unique per `(policy, reporter)`, so an outcome cannot
be reported twice or flipped. A default blocks the borrower for the policy's `default_lockout_s`; clean
repayments lift the tier by at most `max_history_steps`, and never for a borrower whose attested tier is 0.

Cross-contract writes on GenLayer are asynchronous messages. Do not assume `record_outcome` has been applied in the
same transaction: read the ledger (`get_ledger`) or the next `quote` instead of relying on a synchronous return.

## Borrower flow (all calls are from the borrower's address)

```text
begin_binding(url, subject_name)  -> returns challenge  "credo-bind:<your address>:<binding id>"
   publish the challenge on a page only you control (profile bio, your own file or site)
verify_binding()                  -> validators confirm proof of control      (status VERIFIED)
assess(policy_id, [evidence urls]) -> validators judge public evidence         (status QUALIFIED / UNQUALIFIED)
```

Evidence must come from a different registrable domain than the identity page, and a policy with
`require_backlink: true` only counts evidence pages that link to the identity page.

## Writing a policy

`create_policy(spec_json)`. All fields are required:

```json
{
  "base_collateral_bps": 15000,
  "criteria": [
    {"id": "employment", "text": "The page states the subject currently holds a named position at a named organisation.", "weight": 4000, "required": true},
    {"id": "tenure", "text": "The page states the subject has been a registered member since a stated year.", "weight": 3000, "required": false}
  ],
  "tiers": [
    {"min_score_bps": 4000, "collateral_bps": 11000, "rate_discount_bps": 200},
    {"min_score_bps": 7000, "collateral_bps": 8000, "rate_discount_bps": 500}
  ],
  "min_sources": 1,
  "ttl_s": 2592000,
  "cooldown_s": 3600,
  "reporters": ["0x..."],
  "default_lockout_s": 2592000,
  "repay_step_every": 2,
  "max_history_steps": 1,
  "require_backlink": true
}
```

Bounds: 1 to 8 criteria (weight 1 to 10000, id `[a-z0-9_]` up to 24 chars, text 8 to 200 chars), 1 to 5 tiers with
strictly ascending `min_score_bps` and strictly decreasing `collateral_bps` below `base_collateral_bps`,
`min_sources` 1 to 3, `ttl_s` 1 hour to 1 year, `cooldown_s` 60 s to 30 days, up to 8 reporters,
`default_lockout_s` 1 day to 10 years, `max_history_steps` 0 to 2, spec at most 4,000 characters.

Write criteria as **factual statements a page can quote**, not as judgments ("is trustworthy"). The model is asked
only whether the page supports a statement and to quote the supporting text.
