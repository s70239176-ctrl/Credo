"""Forged-leader, malformed-proposal and pickling tests for the consensus observation.

`direct_vm.run_validator` feeds the validator a leader result of our choosing while the validator
re-observes the (mocked) world itself. A well-formed but substantively false leader proposal must be
rejected; harmless differences (which excerpt was quoted) must not be.
"""
import copy

import cloudpickle
import pytest

from conftest import BOUND, EV1, EV2, QUOTES, TEXT_FULL, TEXT_LINKED, eval_resp


@pytest.fixture
def honest(env):
    """A completed assessment; returns (env, the honest leader proposal)."""
    pid = env.policy()
    env.bind()
    env.evidence(EV1)
    env.assess(pid, [EV1])
    leader = copy.deepcopy(env.vm._captured_validators[-1][0])
    return env, leader


def _validate(env, proposal):
    return env.vm.run_validator(leader_result=proposal)


def test_honest_leader_accepted(honest):
    env, leader = honest
    assert _validate(env, leader) is True


def test_equivalent_excerpt_choice_is_accepted(honest):
    env, leader = honest
    leader["sources"][0]["quotes"]["employment"] = "Head of Treasury at Northwind Cooperative"
    assert _validate(env, leader) is True  # different but grounded excerpt: explanatory only


def test_forged_backlink_claim_rejected(honest):
    env, leader = honest
    assert leader["sources"][0]["linked"] is False
    leader["sources"][0]["linked"] = True  # leader pretends the evidence links to the identity page
    assert _validate(env, leader) is False


def test_missing_real_backlink_rejected(env):
    pid = env.policy(require_backlink=True)
    env.bind()
    env.evidence(EV1, text=TEXT_LINKED)
    env.assess(pid, [EV1])
    leader = copy.deepcopy(env.vm._captured_validators[-1][0])
    assert leader["sources"][0]["linked"] is True
    assert _validate(env, leader) is True
    leader["sources"][0]["linked"] = False  # leader hides a link the validator can see
    assert _validate(env, leader) is False


def test_overclaiming_leader_rejected_when_validator_sees_nothing(honest):
    env, leader = honest
    env.judge(EV1, eval_resp(()))
    assert _validate(env, leader) is False


def test_overclaim_of_one_criterion_rejected(honest):
    env, leader = honest
    env.judge(EV1, eval_resp(("employment", "tenure")))
    assert _validate(env, leader) is False  # leader also claimed peer_vouch


def test_underclaiming_leader_rejected(honest):
    env, leader = honest
    leader["sources"][0]["met"]["peer_vouch"] = False
    leader["sources"][0]["quotes"]["peer_vouch"] = ""
    assert _validate(env, leader) is False  # a leader may not silently deny standing either


def test_fabricated_quote_rejected_even_when_met_set_matches(honest):
    env, leader = honest
    leader["sources"][0]["quotes"]["employment"] = "Alice Example is chairman of the central bank of Atlantis"
    assert _validate(env, leader) is False


def test_quote_grounded_only_in_leader_snapshot_rejected(honest):
    env, leader = honest
    # the page the validator sees no longer contains the sentence the leader quoted
    env.page(EV1, "Alice Example is the Head of Treasury at Northwind Cooperative. Alice Example has served as "
                  "a registered member since 2019. Priya Rao writes about someone else entirely.")
    env.judge(EV1, eval_resp(("employment", "tenure", "peer_vouch")))  # model still says met, quote is not there
    assert _validate(env, leader) is False


def test_forged_identity_proof_rejected(honest):
    env, leader = honest
    env.page(BOUND, "Alice Example profile. Nothing to see here.")
    assert leader["binding"]["found"] is True
    assert _validate(env, leader) is False


def test_forged_owner_control_rejected(honest):
    env, leader = honest
    env.judge(BOUND, {"control": "THIRD_PARTY", "subject": "SAME"})
    assert _validate(env, leader) is False


def test_forged_binding_subject_rejected(honest):
    env, leader = honest
    env.judge(BOUND, {"control": "OWNER", "subject": "DIFFERENT"})
    assert _validate(env, leader) is False


def test_forged_reachability_rejected(honest):
    env, leader = honest
    env.unreachable(EV1)
    assert _validate(env, leader) is False
    env.page(EV1, "gone", status=503)
    assert _validate(env, leader) is False


def test_forged_binding_reachability_rejected(honest):
    env, leader = honest
    env.unreachable(BOUND)
    assert _validate(env, leader) is False


def test_forged_subject_match_rejected(honest):
    env, leader = honest
    env.judge(EV1, eval_resp((), subject="DIFFERENT"))
    assert _validate(env, leader) is False


def test_honest_unreachable_leader_accepted_when_validator_agrees(honest):
    env, _ = honest
    env.unreachable(EV1)
    leader = {
        "binding": {"reach": "OK", "found": True, "control": "OWNER", "subject": "SAME"},
        "sources": [{"url": EV1, "reach": "UNREACHABLE", "subject": "UNCLEAR", "linked": False,
                     "met": {k: False for k in QUOTES}, "quotes": {k: "" for k in QUOTES}}],
    }
    assert _validate(env, leader) is True


def _mut(path_fn):
    def apply(leader):
        path_fn(leader)
        return leader
    return apply


MALFORMED = {
    "not_a_dict": lambda l: "UP",
    "none": lambda l: None,
    "list": lambda l: [l],
    "extra_top_key": lambda l: {**l, "safe": True},
    "missing_binding": lambda l: {"sources": l["sources"]},
    "missing_sources": lambda l: {"binding": l["binding"]},
    "binding_extra_key": lambda l: (l["binding"].update(extra=1), l)[1],
    "binding_found_truthy_string": lambda l: (l["binding"].update(found="true"), l)[1],
    "binding_found_int": lambda l: (l["binding"].update(found=1), l)[1],
    "binding_unknown_control": lambda l: (l["binding"].update(control="ROOT"), l)[1],
    "binding_lower_control": lambda l: (l["binding"].update(control="owner"), l)[1],
    "binding_unknown_subject": lambda l: (l["binding"].update(subject="MAYBE"), l)[1],
    "binding_unknown_reach": lambda l: (l["binding"].update(reach="FINE"), l)[1],
    "binding_owner_without_page": lambda l: (l["binding"].update(reach="UNREACHABLE"), l)[1],
    "binding_owner_not_found": lambda l: (l["binding"].update(found=False), l)[1],
    "sources_not_list": lambda l: {**l, "sources": {"0": l["sources"][0]}},
    "sources_empty": lambda l: {**l, "sources": []},
    "sources_extra": lambda l: {**l, "sources": l["sources"] + [l["sources"][0]]},
    "source_wrong_url": lambda l: (l["sources"][0].update(url="https://evil.example.com/x"), l)[1],
    "source_extra_key": lambda l: (l["sources"][0].update(note="hi"), l)[1],
    "source_unknown_reach": lambda l: (l["sources"][0].update(reach="MAYBE"), l)[1],
    "source_unknown_subject": lambda l: (l["sources"][0].update(subject="same"), l)[1],
    "source_linked_string": lambda l: (l["sources"][0].update(linked="true"), l)[1],
    "source_linked_int": lambda l: (l["sources"][0].update(linked=1), l)[1],
    "source_linked_missing": lambda l: (l["sources"][0].pop("linked"), l)[1],
    "source_linked_but_unreachable": lambda l: (l["sources"][0].update(linked=True, reach="UNREACHABLE"), l)[1],
    "source_met_missing_key": lambda l: (l["sources"][0]["met"].pop("tenure"), l)[1],
    "source_met_extra_key": lambda l: (l["sources"][0]["met"].update(admin=True), l)[1],
    "source_met_string": lambda l: (l["sources"][0]["met"].update(employment="true"), l)[1],
    "source_met_int": lambda l: (l["sources"][0]["met"].update(employment=1), l)[1],
    "source_met_float": lambda l: (l["sources"][0]["met"].update(employment=1.0), l)[1],
    "source_quotes_non_str": lambda l: (l["sources"][0]["quotes"].update(employment=7), l)[1],
    "source_met_without_quote": lambda l: (l["sources"][0]["quotes"].update(employment=""), l)[1],
    "source_quote_too_long": lambda l: (l["sources"][0]["quotes"].update(employment="x" * 161), l)[1],
    "source_quote_on_unmet": lambda l: (l["sources"][0]["met"].update(employment=False), l)[1],
    "source_met_but_unreachable": lambda l: (l["sources"][0].update(reach="UNREACHABLE"), l)[1],
    "source_met_but_not_same": lambda l: (l["sources"][0].update(subject="UNCLEAR"), l)[1],
}


@pytest.mark.parametrize("name", sorted(MALFORMED))
def test_malformed_leader_results_rejected(honest, name):
    env, leader = honest
    forged = MALFORMED[name](copy.deepcopy(leader))
    assert _validate(env, forged) is False


def test_leader_error_is_rejected(honest):
    env, _ = honest
    assert env.vm.run_validator(leader_error=Exception("boom")) is False


def test_assess_closures_are_picklable(honest):
    env, _ = honest
    _, leader_fn, validator_fn = env.vm._captured_validators[-1]
    cloudpickle.loads(cloudpickle.dumps(leader_fn))
    cloudpickle.loads(cloudpickle.dumps(validator_fn))


# ---------------------------------------------------------------- verify_binding validator

@pytest.fixture
def pending(env):
    env.as_(env.borrower)
    info = env.c.begin_binding(BOUND, "Alice Example")
    env.page(BOUND, f"Alice Example profile. {info['challenge']}")
    env.judge(BOUND, {"control": "OWNER", "subject": "SAME"})
    env.advance(120)
    env.as_(env.borrower)
    assert env.c.verify_binding()["status"] == "VERIFIED"
    return env, copy.deepcopy(env.vm._captured_validators[-1][0])


def test_binding_validator_accepts_honest(pending):
    env, leader = pending
    assert _validate(env, leader) is True


@pytest.mark.parametrize("swap", ["no_proof", "third_party", "namesake", "unreachable"])
def test_binding_validator_rejects_forged_verified_claim(pending, swap):
    env, leader = pending
    if swap == "no_proof":
        env.page(BOUND, "Alice Example profile. Nothing to see here.")
    elif swap == "third_party":
        env.judge(BOUND, {"control": "THIRD_PARTY", "subject": "SAME"})
    elif swap == "namesake":
        env.judge(BOUND, {"control": "OWNER", "subject": "DIFFERENT"})
    else:
        env.unreachable(BOUND)
    assert _validate(env, leader) is False


def test_binding_closures_are_picklable(pending):
    env, _ = pending
    _, leader_fn, validator_fn = env.vm._captured_validators[-1]
    cloudpickle.loads(cloudpickle.dumps(leader_fn))
    cloudpickle.loads(cloudpickle.dumps(validator_fn))


def test_failed_consensus_leaves_state_untouched(honest):
    env, _ = honest
    before = (env.c.get_attestation(env.bkey, 1), env.c.get_binding(env.bkey))
    env.evidence(EV2)
    env.advance(4000)
    env.as_(env.borrower)
    with env.vm.expect_revert("EXPECTED"):
        env.c.assess(1, [EV1, EV1])
    assert (env.c.get_attestation(env.bkey, 1), env.c.get_binding(env.bkey)) == before
