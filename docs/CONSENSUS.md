# Consensus design

Credo has exactly **one** nondeterministic primitive, `gl.vm.run_nondet_unsafe`, wrapped by
`_consensus_observe` in [`contracts/credo.py`](../contracts/credo.py). It is called from two writes:
`verify_binding` (identity page only) and `assess` (identity page plus 1 to 4 evidence pages). Everything
else is deterministic.

## 1. What is observed

For one transaction the observation is a typed object:

```text
binding : { reach, found, control, subject }
sources : [ { url, reach, subject, linked, met{criterion: bool}, quotes{criterion: str} } , ... ]
```

| Field | Meaning | Produced by |
|---|---|---|
| `reach` | `OK`, `UNREACHABLE` (transport error) or `HTTP_ERROR` (non-2xx) | web fetch |
| `found` | the exact challenge string is in the identity page text | deterministic substring on the fetched page |
| `control` | `OWNER` / `THIRD_PARTY` / `UNCLEAR`: is the challenge in owner-controlled content (bio, own file) or visitor-writable content (comment, guestbook)? | **LLM** |
| `subject` (binding) | is the page the profile/site of the named subject? | **LLM** |
| `subject` (source) | does the page concern the same entity as the subject who controls the bound page? | deterministic name-presence floor, then **LLM** |
| `linked` | the evidence page's raw body contains the bound identity URL | deterministic substring |
| `met` / `quotes` | per policy criterion: does the page support it, with a verbatim quote | **LLM**, then deterministic grounding |

### Why each judgment cannot be deterministic

* *Owner-controlled vs. visitor-writable content* and *same entity vs. namesake* are semantic judgments about
  arbitrary page layouts and prose. No parser can answer them across sites.
* *Does the page support a plain-English criterion* ("states the subject currently holds a named position at a
  named organisation") is natural-language entailment over evidence the lender never saw in advance.

Everything the model does **not** need to decide is taken away from it: URL admission, challenge presence,
name presence, backlink presence, quote grounding, origin independence, thresholds, scoring, tiers, money-adjacent
terms, freshness, history. See section 5.

## 2. Leader

1. Re-derive the immutable inputs from storage (bound URL, challenge, subject, policy criteria, evidence URLs).
2. Fetch the identity page. If the challenge string is present, ask the model for `control` and `subject`.
3. For each evidence page: fetch it; if the subject's name does not appear in the page, stop (`UNCLEAR`, nothing
   met, **no model call**); otherwise ask the model for `subject` and per-criterion `met` plus a verbatim `quote`.
4. Apply the deterministic grounding filter: a criterion is `met` only if its quote is 8 to 160 characters and is a
   whitespace/case-normalised substring of the fetched page, and only if the page's subject is `SAME`.
5. Return the typed observation.

The page text is passed to the model as a field of a JSON object, with an instruction that it is untrusted data
and any instruction inside it must be ignored. Pages are capped at 8,000 characters after tag stripping.

## 3. Validator

Each validator receives the leader's proposal and independently:

1. **Type-checks** it with `_obs_well_formed`: exact keys, `type(x) is bool` (not truthy strings or ints), closed
   enums (unknown values are rejected, never mapped), `met` and `quotes` keyed by exactly the policy's criteria,
   `met=True` requires a quote of 8 to 160 characters, `met=False` requires an empty quote, `met=True` requires
   `reach == OK` and `subject == SAME`, `linked=True` requires `reach == OK`.
2. **Re-observes** everything itself: its own fetch, its own model calls, its own grounding filter.
3. Requires **equivalence on the decision-critical fields** with `_equivalent`:
   `binding` (all four fields) and, per source in order, `reach`, `subject`, `linked` and the full `met` map.
4. Requires **grounding in its own snapshot** with `_grounded`: every quote the leader relied on must be present
   in the page text *this validator* fetched.

A leader result that is perfectly well-formed but false (claims a criterion the validator cannot reproduce,
claims proof of control that is not on the page, hides or invents a backlink, flips reachability) fails step 3 or
4. This is exercised by the forged-leader tests in
[`tests/direct/test_credo_hardening.py`](../tests/direct/test_credo_hardening.py).

### What may differ

Quote wording (a different grounded excerpt is accepted), model prose (none is requested), and ordering within a
dict. These are explanatory, not decision-critical.

### What may not differ

`reach` class (`OK` vs `UNREACHABLE` vs `HTTP_ERROR`), the binding's `found`/`control`/`subject`, a source's
`subject` and `linked`, and any criterion's `met` bit. Under-claiming is rejected as well as over-claiming, so a
malicious leader cannot silently deny standing either.

## 4. Failure semantics

| Situation | Result |
|---|---|
| Identity page unreachable / HTTP error | `INCONCLUSIVE`. Binding and attestation untouched. Cooldown still advances. |
| All evidence pages unreachable | `INCONCLUSIVE`. The previous attestation stays until it expires. An outage is not a downgrade. |
| Some evidence pages unreachable | Score computed from the reachable pages only. `min_sources` stops a thin result from qualifying. |
| Challenge missing, or `control != OWNER`, or `subject != SAME` at `assess` | Binding moves to `LOST` and the URL is released. Quotes become `UNBOUND`. Fail closed. |
| Challenge missing / not owner-controlled at `verify_binding` | `REJECTED`; binding stays `PENDING` (bounded attempts). |
| Model output not JSON / unknown enum / wrong types | Treated as `UNCLEAR` and nothing met. Never repaired into a positive. A fenced ```` ```json ```` block is accepted; nothing else is repaired. |
| Quote not found in the page | That criterion does not count. |
| Validators disagree | The protocol transaction is `UNDETERMINED`; Credo state does not change. This is a protocol outcome, distinct from the contract-level `INCONCLUSIVE`. |
| Leader error | Validator returns `False`. |
| Malformed observation reaching the contract | `EXTERNAL: malformed consensus observation`; the transaction reverts. |

## 5. Deterministic responsibilities (the much larger surface)

Everything after the observation is plain code and is covered by Direct Mode tests:

* URL admission (HTTPS only, bare lowercase public host, no credentials, port, fragment, IP literal, `.local`
  style suffix, traversal, length).
* Evidence admission: 1 to 4 URLs, no duplicates, **not** from the same registrable domain as the identity page.
* Registrable-domain independence (`_origin_key`) and the `min_sources` corroboration floor.
* `require_backlink`: only evidence whose page links to the bound identity URL counts.
* Required criteria, weighted score in basis points, tier lookup, collateral and rate-discount terms.
* Attestation freshness (`ttl_s`), cooldowns, verification-attempt cap.
* Repayment history: reporter authorisation, replay protection per `(policy, reporter, loan_ref)`, clean-streak
  tier lift (bounded by `max_history_steps`, never for tier 0), default lockout.
* The quote derivation `_terms`, the single function lenders rely on.

## 6. Why consensus is load-bearing

If you remove consensus, the contract no longer has the two facts its deterministic code depends on: *which
criteria are supported by the world's public evidence about this person*, and *whether this on-chain address
really controls that identity page*. The only alternative is to let the borrower, the lender or one operator
assert those facts. Credo's deterministic code can only constrain what an agreed observation is allowed to do; it
cannot manufacture the observation.

## 7. Pickling

The leader and validator closures capture only plain strings, lists and dicts (storage objects are converted
before the closure is created). Direct Mode runs with `check_pickling = True`, and dedicated tests
cloudpickle-round-trip both closures for both writes.
