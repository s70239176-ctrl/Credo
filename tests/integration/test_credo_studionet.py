"""Real-consensus Studionet tests. Each test deploys its own DISPOSABLE contract (not the canonical one).

Run:  gltest tests/integration/ -v -s --network studionet

Fixtures are public pages in this repository:
  * the identity page is served by raw.githubusercontent.com (origin githubusercontent.com),
  * evidence pages are served by cdn.jsdelivr.net (origin jsdelivr.net), pinned to CREDO_FIXTURE_REF.
They describe a fictional person, "Ada Fixture". The identity page carries the binding challenge for the
Studio default account for binding ids 1..5 (a fresh deployment's first binding is id 1).

Assertions use settlement-critical fields only (status, tier, criterion bits, quote status), never LLM prose.
"""
import json
import os
import time

from gltest import create_account, get_contract_factory, get_default_account
from gltest.assertions import tx_execution_succeeded

REPO = "s70239176-ctrl/Credo"
REF = os.environ.get("CREDO_FIXTURE_REF", "main")
IDENTITY = f"https://raw.githubusercontent.com/{REPO}/main/fixtures/identity/ada-fixture.md"
GUESTBOOK = f"https://raw.githubusercontent.com/{REPO}/main/fixtures/identity/guestbook.md"
REGISTRY = f"https://cdn.jsdelivr.net/gh/{REPO}@{REF}/fixtures/evidence/registry.md"
HOSTILE = f"https://cdn.jsdelivr.net/gh/{REPO}@{REF}/fixtures/evidence/hostile.md"
SUBJECT = "Ada Fixture"
BASE_BPS = 15000

CRITERIA = [
    {"id": "employment", "text": "The page states that the subject currently holds a named position at a named organisation.",
     "weight": 4000, "required": True},
    {"id": "tenure", "text": "The page states that the subject has been a registered member or officer since a stated year.",
     "weight": 3000, "required": False},
    {"id": "peer_vouch", "text": "The page contains a named third party vouching for the subject's reliability.",
     "weight": 3000, "required": False},
]


def spec(reporter):
    return json.dumps({
        "base_collateral_bps": BASE_BPS,
        "criteria": CRITERIA,
        "tiers": [
            {"min_score_bps": 4000, "collateral_bps": 11000, "rate_discount_bps": 200},
            {"min_score_bps": 7000, "collateral_bps": 8000, "rate_discount_bps": 500},
            {"min_score_bps": 10000, "collateral_bps": 5000, "rate_discount_bps": 1000},
        ],
        "min_sources": 1, "ttl_s": 7 * 86400, "cooldown_s": 60, "reporters": [reporter.lower()],
        "default_lockout_s": 86400, "repay_step_every": 2, "max_history_steps": 1,
        "require_backlink": True,
    })


def _deploy():
    factory = get_contract_factory(contract_file_path="credo.py")
    return factory.deploy(account=get_default_account(), consensus_max_rotations=3)


def _ok(receipt):
    assert tx_execution_succeeded(receipt)
    return receipt


def _make_policy(c, lender):
    r = c.connect(lender).create_policy(args=[spec(lender.address)]).transact(consensus_max_rotations=3)
    _ok(r)
    assert c.get_policy(args=[1]).call()["owner"].lower() == lender.address.lower()  # setup really created state
    return 1


def _bind(c, borrower, url=IDENTITY):
    _ok(c.connect(borrower).begin_binding(args=[url, SUBJECT]).transact(consensus_max_rotations=3))
    b = c.get_binding(args=[borrower.address]).call()
    assert b["binding_id"] == 1 and b["challenge"] == f"credo-bind:{borrower.address.lower()}:1"
    _ok(c.connect(borrower).verify_binding().transact(consensus_max_rotations=3))
    return c.get_binding(args=[borrower.address]).call()


def _quote(c, borrower, pid=1):
    return c.quote(args=[borrower.address, pid, int(time.time())]).call()


def test_deploy_and_public_surface():
    c = _deploy()
    lender = create_account()
    pid = _make_policy(c, lender)
    p = c.get_policy(args=[pid]).call()
    assert p["active"] is True and len(p["policy_hash"]) == 64
    assert p["spec"]["base_collateral_bps"] == BASE_BPS
    borrower = get_default_account()
    assert c.get_binding(args=[borrower.address]).call()["status"] == "NONE"
    assert _quote(c, borrower)["status"] == "UNBOUND"


def test_live_identity_binding_and_standing_lowers_collateral():
    c = _deploy()
    lender, borrower = create_account(), get_default_account()
    pid = _make_policy(c, lender)
    assert _bind(c, borrower)["status"] == "VERIFIED"  # real validators confirmed the proof of control

    _ok(c.connect(borrower).assess(args=[pid, [REGISTRY]]).transact(consensus_max_rotations=3))
    att = c.get_attestation(args=[borrower.address, pid]).call()
    assert att["tier"] >= 1 and att["met_mask"] & 1 == 1  # the required employment criterion was corroborated
    q = _quote(c, borrower, pid)
    assert q["status"] == "OK" and q["reduced"] is True and q["collateral_bps"] < BASE_BPS
    assert c.meets(args=[borrower.address, pid, int(time.time()), q["policy_hash"], q["collateral_bps"]]).call() is True

    # on-chain repayment history written by the policy's trusted reporter lifts the tier one step
    for ref in ("loan-1", "loan-2"):
        _ok(c.connect(lender).record_outcome(args=[borrower.address, pid, ref, "REPAID"]).transact(consensus_max_rotations=3))
    led = c.get_ledger(args=[borrower.address, pid]).call()
    assert led["repaid"] == 2 and led["clean_streak"] == 2
    q2 = _quote(c, borrower, pid)
    assert q2["history_steps"] == 1 and q2["collateral_bps"] <= q["collateral_bps"]


def test_live_negative_paths_fail_closed():
    c = _deploy()
    lender, borrower = create_account(), get_default_account()
    pid = _make_policy(c, lender)

    # (1) a challenge planted in a visitor-writable guestbook is NOT proof of control
    _ok(c.connect(borrower).begin_binding(args=[GUESTBOOK, SUBJECT]).transact(consensus_max_rotations=3))
    _ok(c.connect(borrower).verify_binding().transact(consensus_max_rotations=3))
    assert c.get_binding(args=[borrower.address]).call()["status"] == "PENDING"  # never VERIFIED
    assert _quote(c, borrower, pid)["status"] == "UNBOUND"
    # a still-pending binding cannot be used for an assessment
    r = c.connect(borrower).assess(args=[pid, [REGISTRY]]).transact(consensus_max_rotations=3)
    assert not tx_execution_succeeded(r)
    assert c.get_attestation(args=[borrower.address, pid]).call()["status"] == "NONE"


def test_live_hostile_evidence_cannot_buy_standing_and_default_blocks():
    c = _deploy()
    lender, borrower = create_account(), get_default_account()
    pid = _make_policy(c, lender)
    assert _bind(c, borrower)["status"] == "VERIFIED"

    # a page that tries to instruct the model must not raise standing
    _ok(c.connect(borrower).assess(args=[pid, [HOSTILE]]).transact(consensus_max_rotations=3))
    att = c.get_attestation(args=[borrower.address, pid]).call()
    assert att["tier"] == 0
    q = _quote(c, borrower, pid)
    assert q["status"] == "OK" and q["reduced"] is False and q["collateral_bps"] == BASE_BPS

    # recovery path: a recorded default blocks the borrower, and revoking the binding drops all standing
    _ok(c.connect(lender).record_outcome(args=[borrower.address, pid, "loan-9", "DEFAULTED"]).transact(consensus_max_rotations=3))
    assert _quote(c, borrower, pid)["status"] == "BLOCKED"
    _ok(c.connect(borrower).revoke_binding().transact(consensus_max_rotations=3))
    assert c.get_binding(args=[borrower.address]).call()["status"] == "REVOKED"
    assert _quote(c, borrower, pid)["status"] == "UNBOUND"
