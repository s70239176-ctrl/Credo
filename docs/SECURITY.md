# Threat model

## Assets

* **The quote.** A lending contract that trusts `quote` extends credit for less collateral. A false reduction is a
  direct loss to a lender.
* **The identity binding.** An address must not be linkable to an identity its owner does not control.
* **The repayment ledger.** It must not be writable by anyone but the policy's reporters.

Credo holds no funds and has no admin or upgrade path.

## Actors and assumptions

| Actor | Trusted for | Not trusted for |
|---|---|---|
| Borrower | nothing | choosing the identity page's owner-control judgment, the evidence's meaning, their tier |
| Policy owner / lender | choosing criteria, tiers, reporters of *their own* policy | other policies; consumers must pin the policy hash they reviewed |
| Reporter | reporting outcomes of loans it made | anything outside its policy |
| Page content (identity, evidence) | nothing | being instructions; it is hostile data |
| Leader | proposing an observation | being right |
| Validator majority | honest re-observation | not assumed to be all-honest; a minority cannot decide |
| Downstream consumer | its own use of `quote` | |

Standard GenLayer assumptions apply: an honest validator majority, working web egress and model access, and
validators seeing substantially the same public page.

## Attacks considered and what stops them

| Attack | Defence | Test |
|---|---|---|
| Bind someone else's identity page | The challenge embeds the borrower's address; a page without it is rejected. A challenge for another address is rejected. | `test_verify_rejects_challenge_for_another_address` |
| Plant the challenge in a visitor-writable area (comment, guestbook) of a victim's page | Validators must judge `control == OWNER`; `THIRD_PARTY`/`UNCLEAR` never verifies, and re-checked at every `assess` (`BINDING_LOST`). | `test_verify_rejected_unless_owner_controlled_and_same_subject`, live guestbook test |
| Bind a namesake or impersonation page, then submit real evidence about the real person | Evidence must name the subject, be judged the same entity, and (when the policy sets `require_backlink`) **link to the bound identity page**, which an impersonator cannot make a third party do. | `test_backlink_*` |
| Self-asserted evidence | Evidence from the identity page's own registrable domain is rejected at admission; `min_sources` counts distinct registrable domains. | `test_assess_evidence_admission`, `test_corroboration_floor_counts_distinct_origins` |
| Prompt injection from a page | Page text is passed as a JSON data field with an explicit ignore-instructions rule; the model's output can only set typed fields; ungrounded claims are dropped; unknown enums fail closed. | `test_prompt_injection_page_cannot_raise_standing`, live hostile-page test |
| Forged or lazy leader | Well-formed-but-false proposals fail validator equivalence and grounding; malformed types (bool-as-int, strings for bools, floats, unknown enums, extra/missing keys) fail the shape check. | `tests/direct/test_credo_hardening.py` |
| Fabricated supporting quote | A criterion counts only if its quote is present in the validator's own snapshot. | `test_fabricated_quote_rejected_*` |
| Outage manufacturing a downgrade or an upgrade | Unreachable pages return `INCONCLUSIVE` and change nothing; unreachable pages never count toward a criterion. | `test_inconclusive_*` |
| Stale standing | Attestations expire (`ttl_s`); `quote` returns `STALE` and the base collateral. | `test_quote_goes_stale_at_expiry` |
| Re-use of a good attestation under a new binding or policy | Attestation records `binding_id` and `policy_hash`; `quote` requires both to match. | `test_rebind_after_revoke_*`, `test_meets_gate` |
| Reporter spam / replay / flipping an outcome | Reporter allow-list per policy; `(policy, reporter, loan_ref)` is single-use; reporters cannot report on themselves. | `test_loan_ref_replay_rejected`, `test_reporter_cannot_report_on_itself` |
| Buying standing with history | History lifts at most `max_history_steps` (<= 2) and never rescues attested tier 0. | `test_history_cannot_rescue_unqualified_identity` |
| SSRF / odd URLs | HTTPS only, bare lowercase public hostname, no credentials, port, fragment, IP literal or local suffix, no traversal, 200-character cap. | `test_bad_urls_rejected` |
| Unbounded state or cost | Caps on policies (10,000), criteria, tiers, reporters, evidence URLs, spec size, page size (8,000 chars), quote size, verification attempts; cooldowns on `assess` and `verify_binding`. | admission tests |

## Fail-open / fail-closed table

| Condition | Default |
|---|---|
| Unknown / unparsable model output | nothing met, subject `UNCLEAR` (**closed**) |
| Missing or untrusted proof of control | binding not verified / `LOST` (**closed**) |
| Evidence unreachable | `INCONCLUSIVE`, prior state kept, prior attestation still expires on schedule |
| Attestation expired, unbound, unattested, blocked, policy inactive | base collateral, `reduced = false` (**closed**) |
| Validators disagree | transaction `UNDETERMINED`, state unchanged |

## Limitations (read these)

* **This is not government KYC and does not prove a legal person.** It proves control of a public identity page
  and public evidence about that identity. A person can hold more than one identity and obtain standing for each;
  Credo does not prevent sybil identities beyond requiring independent, backlinked evidence. Lenders choose how
  much that is worth by setting tiers conservatively.
* **A borrower who controls a page named after a famous person can claim that name.** `require_backlink: true`
  defeats the straightforward version of this by requiring evidence pages to link to the bound page. A policy
  with `require_backlink: false` accepts that risk.
* **Independence is approximate.** Registrable domain is derived from a small built-in list of second-level
  suffixes, not the full public-suffix list. Two sites with different domains can still be owned by one party,
  and one domain (for example a large hosting platform) can host unrelated people; Credo treats the latter
  conservatively (one origin).
* **Model variance.** Honest validators can disagree on borderline pages; the result is an `UNDETERMINED`
  transaction, not a wrong state, and the borrower can retry after the cooldown. Write crisp factual criteria.
* **Truncation.** Pages are cut to 8,000 characters after tag stripping. A decisive fact beyond that is invisible.
* **Reporter trust.** A reporter can lie about its own policy's loans. The blast radius is bounded by the policy
  (`max_history_steps`) and by the consumer pinning the policy hash.
* **No SSRF or prompt-injection guarantee.** The URL checks and data framing are defence in depth; validator egress
  policy and model robustness still matter.
* **Page-controlled content can change after attestation.** Standing is only as fresh as `ttl_s`; the identity
  page is re-checked on every `assess`, not continuously.
* **Studionet is a development network.** The deployment is evidence of behaviour, not a production audit.
