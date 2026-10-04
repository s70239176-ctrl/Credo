# Deployment evidence

## Canonical deployment (Studionet)

| | |
|---|---|
| Network | GenLayer Studionet |
| RPC / chain id | `https://studio.genlayer.com/api` / 61999 |
| Contract | `0x70189B81E0Bd90ba29AaBBbB1fdA11380D599592` |
| Explorer | https://explorer-studio.genlayer.com/address/0x70189B81E0Bd90ba29AaBBbB1fdA11380D599592 |
| Deployed by | the project owner, through Studio (deployer `0x0d204FfEdEbd600CbF182865e04ab9A2877b23F0`) |
| Deployment tx | `0x6eabb7ad6fcd4d4fd3095662a2ba979f4683ecdee975aae3815a15595241ecbf` |
| Deployment lifecycle | **FINALIZED**, observed through `sim_getTransactionsForAddress` on 2026-10-04. The receipt records validator votes `idle, agree, agree, idle`; its `result` field was empty, so no consensus-result label is claimed for the deployment itself. |
| Deployed source | 41,270 bytes, SHA-256 `a3ed55f7a9e2dc913e0949f9dea899138aa796b34f9b9c0d288cfe45e1c74cff` |
| Contract git blob | `8f0a0f9d15f171a83a8db0afbe5b5225a63e5efa` |
| Source parity | **MATCH**: the code read back with `gen_getContractCode` is byte-identical to `contracts/credo.py` at commit `83ceb07` and at every later commit that leaves that file unchanged (compare `git rev-parse HEAD:contracts/credo.py` with the blob above) |
| Deployed schema | `gen_getContractSchema` lists the 15 expected methods, including `assess` and `begin_binding`; no-argument constructor |

Tooling for the runs below: Python 3.14.3, genlayer-test 0.29.2, genlayer-py 0.16.3, genvm-linter 0.11.0, GenVM SDK v0.2.16.

## Live evidence on the canonical contract

Produced by `tests/evidence/test_canonical_evidence.py` against the address above. Borrower
`0x2B5BB93c5257D377B5A201d03fFe541620cB6a7e` (the Studio default account for that session) and lender/reporter
`0x619Ea1Fc48269A347de5556a3cD9C028E121643f` (generated for the run; no key is printed or stored). Evidence pages are
the public fixtures in `fixtures/evidence/` served via jsDelivr pinned to commit
`83ceb07971c155cf43eb32b8e34b6ea93ef0c2d2`; the identity page is generated per run as a stateless
`httpbin.org/base64/...` page carrying the borrower's challenge. Every transaction below reported status
**ACCEPTED** and result **MAJORITY_AGREE** when recorded. A later read of the chain showed **all 29 transactions on
the canonical contract FINALIZED**, including every hash cited in this table.

| Scenario | Action | Tx | Stored result |
|---|---|---|---|
| setup | lender creates policy 2 | `0x4bbe1e65d3624985bbd104871e00fe2f73ca05a6cac056e3d786fb03a2119e24` | policy hash `bd6e488d…b3076` |
| negative | `verify_binding` on a visitor-writable guestbook page carrying a stranger's challenge (binding 3) | `0xebfdee3a02d5ff3ec307fd6376f01efc0b58648e215ebdd08f4e9ef758b029dd` | binding stays **PENDING**; quote `UNBOUND` |
| success | `verify_binding` on an owner-controlled page (binding 5) | `0x7259b136befe9a658dfc94d925fe99986623fb7fbc9d9b41856a98e3a0fe8fc9` | binding **VERIFIED** |
| negative | `assess` a page containing a prompt-injection attempt | `0x4c7593c49ff846cbb2bb17c6bf2c4a189a3e08801b08cc28aeff619a53476689` | tier **0**, score 0, quote stays at base 15000 bps |
| success | `assess` the genuine registry page | `0x7654d588054a10b9a0100f7fe9b9c758d45fec82ea880b233e7c5d7ade781cd3` | tier **2**, score 7000 bps (employment and tenure met), quote `OK`, **8000 bps**, rate discount 500 bps |
| success | `record_outcome` REPAID `loan-1` | `0x26054a5c70dbb924dc7fa84516e5a0710581a8f415d4fa066ac691e923a9dc82` | clean streak 1 |
| success | `record_outcome` REPAID `loan-2` | `0xeaf7cddd2c82e71b36dad52286662d3a158fce9164ccdeaa48d6e874cd9e2186` | history lifts one tier: effective tier 3, **5000 bps**, discount 1000 bps |
| recovery | `record_outcome` DEFAULTED `loan-3` | `0xef9936eada2c720986982d1d34e0b2b81980b4cc49c6dd301f6612601f7a21af` | quote `BLOCKED`, 15000 bps |
| recovery | `revoke_binding` | `0xf436474417acf05cbbb98b9936ebe32f17f29411b4faccdc8f9f89fb13faa363` | binding `REVOKED`; quote `UNBOUND` |

Two things were asserted by reading state, not just receipts: every setup write was followed by a state read, and the
`meets(...)` gate returned true for the 8000 bps quote under the pinned policy hash.

Covered live separately (next section): `BINDING_LOST`. Not covered live: `require_backlink` (the generated identity page
cannot be linked from a committed fixture; covered in Direct Mode) and the stale/expiry path (a 1-hour minimum TTL makes
it impractical to wait for; covered in Direct Mode).

### State left on the canonical contract

A first run of the evidence test aborted after creating **policy 1** and one throwaway **binding 1** (a helper bug
produced an over-long URL, which the contract's own validation rejected). Both belong to a Studio session account
that is no longer used, and are inert. The successful run created **policy 2** and **bindings 2 to 5** for the borrower
above: 2 and 4 are deliberate throwaways used to learn the next binding id, 3 is the guestbook attempt (PENDING), and 5
is the verified binding (later revoked). None of it affects future use. Each further run of the evidence test appends
more.

## Integration suite (disposable contracts)

`gltest tests/integration/ -v -s --network studionet`: **4 passed** in 16m38s. Each test deploys its own disposable
contract; these are not the canonical deployment. `test_live_negative_paths_fail_closed` was also run on its own: **1 passed** in 3m59s. The other three tests deploy
their own contract the same way and share no state, but only this one was re-run individually.

Two earlier attempts failed and are reported here for honesty:

1. With no transport workaround, all four tests failed with a connect timeout to `studio.genlayer.com:443` before any
   transaction was submitted. Cause: this host's IPv6 route to Cloudflare is black-holed and one IPv4 address
   intermittently stalls. Not a contract result. Fixed for the test process only by the opt-in
   `tests/support/host_net_shim.py`.
2. With the transport fixed, two tests failed because the identity binding stayed `PENDING`. Cause: the fixture
   identity page carried the challenge for a hard-coded account, but Studio's default account is random per session,
   so validators correctly found no proof. The tests now generate the identity page at run time. The contract behaved
   correctly in both cases.

## Local gates

Direct Mode 201 passed (with `check_pickling` on); a 13-mutant mutation check was caught 13/13; `genvm-lint lint`
passed; `genvm-lint check` passed (exit 0, 15 methods). `check` also reports that a newer GenVM runner exists than the
one pinned in the contract header; the pin was not changed.

## Clean-clone reproduction (2026-10-04)

Everything was re-run from a fresh clone of `origin/main` at `af80f37`, with new virtualenvs built only from the committed
dependency files (genlayer-test 0.29.2, genlayer-py 0.16.3, genvm-linter 0.11.0, Python 3.14.3):

| Gate | Result |
|---|---|
| Direct Mode | 202 passed at `af80f37`. A redundant temporary smoke test was removed afterwards; the suite is now 201 passed (139 + 62), same contract. |
| `genvm-lint lint` / `check` / `check --json` | passed / passed / exit 0 (15 methods) |
| Deployed code vs `contracts/credo.py` | MATCH (41,270 bytes) |
| `tests/integration` (disposable contracts) | 4 passed in 13m44s |
| `tests/evidence` (canonical contract) | 1 passed in 8m48s; 9 transactions ACCEPTED / MAJORITY_AGREE |

The second canonical run created **policy 3** on the canonical contract and reproduced the same outcomes as the first:
guestbook binding stays PENDING, owner page VERIFIED, injection page tier 0, genuine evidence tier 2 at 8000 bps, history
lift to 5000 bps, default BLOCKED at 15000 bps, revoke UNBOUND. Its transaction hashes are in that run's console output
and are not duplicated here; the first run's hashes above are the cited evidence.

## Live BINDING_LOST check (disposable contract, two phases)

`tests/evidence/test_binding_lost_live.py`. Needs an identity page whose proof disappears after verification, so it uses
the committed fixture `fixtures/identity/lost-check.md` and a fixed throwaway borrower
`0x2E1285f2a0F895429ea49e12e0E51c1AC3328CF4` (key only in the gitignored `.env.credo-test`, never printed). Contract:
`0x7C88218a09a04Ce953F31AA866B4c02CF95AB50D` (disposable, not canonical).

| Phase | What happened | Result |
|---|---|---|
| A (commit `2405c3e`, proof on the page) | bind, verify, assess the registry fixture | binding VERIFIED, quote `OK` at **8000 bps** (1 passed, 2m46s) |
| page change (commit `c223d16`) | the challenge line was removed and the raw URL was polled until it served the new text | page no longer carries the proof |
| B (proof gone) | assess again, tx `0x8a8843f617596dab1922c5ff7a1c4d4ba2b3578bc39b004076bf43934973b948` (ACCEPTED / MAJORITY_AGREE, later FINALIZED) | binding **LOST**, quote `UNBOUND` at 15000 bps, `reduced = false`; another address could then begin binding the released page (1 passed, 4m44s) |

Note the fixture at `main` now shows the phase-B text, so re-running phase A needs the proof line restored first.
