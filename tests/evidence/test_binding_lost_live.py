"""Two-phase live check of BINDING_LOST on a disposable contract.

BINDING_LOST needs an identity page whose proof disappears after verification, so it cannot use the stateless
generated pages of the other live tests. This check uses a committed fixture page and a FIXED throwaway borrower
account (its address is in the fixture; its key lives only in the gitignored file .env.credo-test and is never printed).

    # phase A: proof is on the page
    CREDO_PHASE=A gltest tests/evidence/test_binding_lost_live.py -s --network studionet
    # then commit a version of fixtures/identity/lost-check.md WITHOUT the challenge, push, wait for the raw URL to update
    CREDO_PHASE=B gltest tests/evidence/test_binding_lost_live.py -s --network studionet

Phase A deploys a fresh contract, creates a policy, binds, verifies and qualifies the borrower, then stores the contract
address in the gitignored .binding_lost_state.json. Phase B assesses again and expects the binding to be LOST.
"""
import json
import os
import time

import pytest
from genlayer_py import create_account as account_from_key
from gltest import create_account, get_contract_factory, get_default_account
from gltest.assertions import tx_execution_succeeded

from tests.integration.test_credo_studionet import REGISTRY, SUBJECT, spec

PAGE = "https://raw.githubusercontent.com/s70239176-ctrl/Credo/main/fixtures/identity/lost-check.md"
STATE = ".binding_lost_state.json"
PHASE = os.environ.get("CREDO_PHASE", "")


def _borrower():
    for line in open(".env.credo-test", encoding="utf-8"):
        if line.startswith("CREDO_TEST_KEY="):
            return account_from_key(line.split("=", 1)[1].strip())
    raise RuntimeError("CREDO_TEST_KEY missing from .env.credo-test")


def _ok(r):
    assert tx_execution_succeeded(r)
    return r


@pytest.mark.skipif(PHASE != "A", reason="phase A only")
def test_phase_a_bind_and_qualify():
    borrower, lender = _borrower(), create_account()
    c = get_contract_factory(contract_file_path="credo.py").deploy(
        account=get_default_account(), consensus_max_rotations=3)
    _ok(c.connect(lender).create_policy(args=[spec(lender.address)]).transact(consensus_max_rotations=3))
    _ok(c.connect(borrower).begin_binding(args=[PAGE, SUBJECT]).transact(consensus_max_rotations=3))
    b = c.get_binding(args=[borrower.address]).call()
    assert b["binding_id"] == 1 and b["challenge"] == f"credo-bind:{borrower.address.lower()}:1"
    _ok(c.connect(borrower).verify_binding().transact(consensus_max_rotations=3))
    assert c.get_binding(args=[borrower.address]).call()["status"] == "VERIFIED"
    _ok(c.connect(borrower).assess(args=[1, [REGISTRY]]).transact(consensus_max_rotations=3))
    q = c.quote(args=[borrower.address, 1, int(time.time())]).call()
    assert q["status"] == "OK" and q["reduced"] is True
    json.dump({"contract": c.address, "borrower": borrower.address}, open(STATE, "w"))
    print("PHASE_A_OK", c.address, q["status"], q["collateral_bps"])


@pytest.mark.skipif(PHASE != "B", reason="phase B only")
def test_phase_b_binding_lost():
    st = json.load(open(STATE))
    borrower = _borrower()
    assert borrower.address == st["borrower"]
    c = get_contract_factory(contract_file_path="credo.py").build_contract(st["contract"], account=borrower)
    before = c.quote(args=[borrower.address, 1, int(time.time())]).call()
    assert before["status"] == "OK"  # standing still stands until the contract re-checks the identity page
    time.sleep(70)  # assessment cooldown (60 s of chain time)
    r = c.connect(borrower).assess(args=[1, [REGISTRY]]).transact(consensus_max_rotations=3)
    assert tx_execution_succeeded(r)
    ev = {"contract": st["contract"], "assess_tx": r["hash"], "tx_status": r.get("status_name"),
          "tx_result": r.get("result_name")}
    b = c.get_binding(args=[borrower.address]).call()
    q = c.quote(args=[borrower.address, 1, int(time.time())]).call()
    ev.update(binding_status=b["status"], quote_status=q["status"], collateral_bps=q["collateral_bps"], reduced=q["reduced"])
    print("BINDING_LOST_EVIDENCE", json.dumps(ev))
    assert b["status"] == "LOST"          # the proof is gone from the page: fail closed
    assert q["status"] == "UNBOUND" and q["reduced"] is False
    # the page was released: another address may now begin binding it
    other = create_account()
    _ok(c.connect(other).begin_binding(args=[PAGE, SUBJECT]).transact(consensus_max_rotations=3))
    assert c.get_binding(args=[other.address]).call()["status"] == "PENDING"
