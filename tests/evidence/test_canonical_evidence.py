"""Records live evidence against the CANONICAL deployment (not a disposable one).

    CANONICAL_ADDRESS=0x... gltest tests/evidence/ -v -s --network studionet

Success path:  bind identity -> assess public evidence -> reduced collateral quote -> repayment history lifts a tier.
Negative path: visitor-writable page is refused as proof of control; a prompt-injection evidence page buys no standing.
Recovery path: a reported default blocks the borrower, revoking the binding drops all standing.

Every run appends new policies/bindings to the canonical contract's state; that is the evidence. It prints every
transaction hash and the stored results as JSON between EVIDENCE markers. Accounts are generated in-process (Studio
default account + one created account); no key is ever printed.
"""
import json
import os
import time

from gltest import create_account, get_contract_factory, get_default_account
from gltest.assertions import tx_execution_succeeded

from tests.integration.test_credo_studionet import (
    BASE_BPS, HOSTILE, REGISTRY, begin_binding, guestbook_page, owner_page, spec,
)


def _tx(r):
    return {"hash": r["hash"], "status": r.get("status_name", r.get("status")),
            "result": r.get("result_name", r.get("result"))}


def _count(c):
    n = 0
    while True:
        try:
            c.get_policy(args=[n + 1]).call()
            n += 1
        except Exception:
            return n


def test_canonical_flow():
    address = os.environ["CANONICAL_ADDRESS"]
    factory = get_contract_factory(contract_file_path="credo.py")
    borrower, lender = get_default_account(), create_account()
    c = factory.build_contract(address, account=borrower)
    ev = {"contract": address, "borrower": borrower.address, "lender": lender.address, "txs": {}, "state": {}}

    def send(label, fn, who=None):
        r = (c.connect(who) if who else c)
        r = fn(r).transact(consensus_max_rotations=3)
        ev["txs"][label] = _tx(r)
        return r

    def q():
        return c.quote(args=[borrower.address, pid, int(time.time())]).call()

    # --- policy (lender)
    before = _count(c)
    assert tx_execution_succeeded(send("create_policy", lambda x: x.create_policy(args=[spec(lender.address)]), lender))
    pid = before + 1
    assert c.get_policy(args=[pid]).call()["owner"].lower() == lender.address.lower()
    ev["policy_id"], ev["policy_hash"] = pid, c.policy_hash(args=[pid]).call()

    # --- negative 1: a stranger's challenge in a visitor-writable page is not proof of control
    begin_binding(c, borrower, guestbook_page)
    ev["txs"]["begin_binding_guestbook"] = None
    assert tx_execution_succeeded(send("verify_guestbook", lambda x: x.verify_binding(), borrower))
    b = c.get_binding(args=[borrower.address]).call()
    ev["state"]["guestbook_binding"] = b
    assert b["status"] == "PENDING" and q()["status"] == "UNBOUND"

    # --- success: owner-controlled page verifies
    b = begin_binding(c, borrower, owner_page)
    assert tx_execution_succeeded(send("verify_owner_page", lambda x: x.verify_binding(), borrower))
    b = c.get_binding(args=[borrower.address]).call()
    ev["state"]["binding"] = b
    assert b["status"] == "VERIFIED"

    # --- negative 2: injection page cannot buy standing
    assert tx_execution_succeeded(send("assess_hostile", lambda x: x.assess(args=[pid, [HOSTILE]]), borrower))
    att = c.get_attestation(args=[borrower.address, pid]).call()
    ev["state"]["attestation_hostile"] = att
    assert att["tier"] == 0 and q()["collateral_bps"] == BASE_BPS

    # --- success: genuine evidence lowers collateral (after the 60 s assessment cooldown)
    time.sleep(70)
    assert tx_execution_succeeded(send("assess_registry", lambda x: x.assess(args=[pid, [REGISTRY]]), borrower))
    att = c.get_attestation(args=[borrower.address, pid]).call()
    ev["state"]["attestation_registry"] = att
    quote = q()
    ev["state"]["quote_after_assess"] = quote
    assert att["tier"] >= 1 and att["met_mask"] & 1 == 1
    assert quote["status"] == "OK" and quote["reduced"] is True and quote["collateral_bps"] < BASE_BPS
    assert c.meets(args=[borrower.address, pid, int(time.time()), quote["policy_hash"], quote["collateral_bps"]]).call()

    # --- repayment history lifts a tier
    for ref in ("loan-1", "loan-2"):
        assert tx_execution_succeeded(send(f"record_repaid_{ref}", lambda x, ref=ref: x.record_outcome(args=[borrower.address, pid, ref, "REPAID"]), lender))
    quote2 = q()
    ev["state"]["quote_after_history"] = quote2
    assert quote2["history_steps"] == 1 and quote2["collateral_bps"] <= quote["collateral_bps"]

    # --- recovery: default blocks, revoke drops standing
    assert tx_execution_succeeded(send("record_default", lambda x: x.record_outcome(args=[borrower.address, pid, "loan-3", "DEFAULTED"]), lender))
    ev["state"]["quote_after_default"] = q()
    assert q()["status"] == "BLOCKED" and q()["collateral_bps"] == BASE_BPS
    assert tx_execution_succeeded(send("revoke_binding", lambda x: x.revoke_binding(), borrower))
    ev["state"]["quote_after_revoke"] = q()
    assert q()["status"] == "UNBOUND"

    print("EVIDENCE_BEGIN")
    print(json.dumps(ev, indent=2, default=str))
    print("EVIDENCE_END")
