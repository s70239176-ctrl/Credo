import datetime
import json
import re
import sys

import pytest

BASE = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)

BOUND = "https://raw.githubusercontent.com/alice-example/id/main/profile.md"
EV1 = "https://registry.example.org/members/alice-example"
EV2 = "https://news.example.net/profiles/alice-example"
EV3 = "https://registry.example.org/other/alice-page"  # same registrable domain as EV1
SUBJECT = "Alice Example"

CRITERIA = [
    {"id": "employment", "text": "The page states the subject is currently employed by or an officer of a named organisation.",
     "weight": 4000, "required": True},
    {"id": "tenure", "text": "The page states the subject has held a public role or account for at least three years.",
     "weight": 3000, "required": False},
    {"id": "peer_vouch", "text": "The page contains a named third party vouching for the subject's professional reliability.",
     "weight": 3000, "required": False},
]

TEXT_FULL = (
    "Alice Example is the Head of Treasury at Northwind Cooperative. Alice Example has served as a registered "
    "member since 2019. Priya Rao writes: I vouch for Alice Example as consistently reliable."
)
TEXT_LINKED = TEXT_FULL + " Member profile: " + BOUND
QUOTES = {
    "employment": "Alice Example is the Head of Treasury at Northwind Cooperative",
    "tenure": "has served as a registered member since 2019",
    "peer_vouch": "I vouch for Alice Example as consistently reliable",
}


def iso(offset_s: int) -> str:
    return (BASE + datetime.timedelta(seconds=offset_s)).isoformat().replace("+00:00", "Z")


def spec_dict(reporters, **over):
    spec = {
        "base_collateral_bps": 15000,
        "criteria": CRITERIA,
        "tiers": [
            {"min_score_bps": 4000, "collateral_bps": 11000, "rate_discount_bps": 200},
            {"min_score_bps": 7000, "collateral_bps": 8000, "rate_discount_bps": 500},
            {"min_score_bps": 10000, "collateral_bps": 5000, "rate_discount_bps": 1000},
        ],
        "min_sources": 1,
        "ttl_s": 30 * 86400,
        "cooldown_s": 3600,
        "reporters": reporters,
        "default_lockout_s": 30 * 86400,
        "repay_step_every": 2,
        "max_history_steps": 1,
        "require_backlink": False,
    }
    spec.update(over)
    return spec


def eval_resp(met=(), subject="SAME", quotes=None):
    q = quotes or QUOTES
    return {
        "subject": subject,
        "criteria": {c["id"]: ({"met": True, "quote": q[c["id"]]} if c["id"] in met else {"met": False, "quote": ""})
                     for c in CRITERIA},
    }


class Env:
    def __init__(self, vm, contract, alice, bob, carol, dave):
        self.vm, self.c = vm, contract
        self.borrower, self.lender, self.other, self.dave = alice, bob, carol, dave
        self.t = 0
        self.web = {}
        self.llm = {}

    # ---- clock / identity
    def warp(self, offset_s):
        # genlayer-test 0.29.2: vm.warp() does not refresh the already-loaded
        # gl.message_raw['datetime'] that the contract reads, so sync it here.
        self.vm.warp(iso(offset_s))
        sys.modules["genlayer.gl"].message_raw["datetime"] = iso(offset_s)

    def advance(self, dt):
        self.t += dt
        self.warp(self.t)

    def as_(self, who):
        self.vm.sender = who

    @property
    def bkey(self):
        return self.borrower.as_hex.lower()

    # ---- mocks (re-registered wholesale so a test can swap what a validator "sees")
    def page(self, url, text, status=200):
        self.web[url] = (status, text)
        self._apply()

    def unreachable(self, url):
        self.web.pop(url, None)
        self._apply()

    def judge(self, url, resp):
        self.llm[url] = resp
        self._apply()

    def _apply(self):
        self.vm.clear_mocks()
        for url, (status, body) in self.web.items():
            self.vm.mock_web("^" + re.escape(url) + "$", {"method": "GET", "status": status, "body": body})
        for url, resp in self.llm.items():
            pat = re.escape('"page_url":"' + url + '"')
            self.vm.mock_llm(pat, json.dumps(resp) if not isinstance(resp, str) else resp)

    # ---- flows
    def policy(self, **over):
        self.as_(self.lender)
        spec = spec_dict([self.lender.as_hex.lower()], **over)
        return self.c.create_policy(json.dumps(spec))

    def bind(self, url=BOUND, who=None, verify=True):
        who = who or self.borrower
        self.as_(who)
        info = self.c.begin_binding(url, SUBJECT)
        if verify:
            self.page(url, f"Alice Example profile. Verification: {info['challenge']}")
            self.judge(url, {"control": "OWNER", "subject": "SAME"})
            self.advance(120)
            self.as_(who)
            res = self.c.verify_binding()
            assert res["status"] == "VERIFIED", res
        return info

    def evidence(self, url, met=("employment", "tenure", "peer_vouch"), text=TEXT_FULL, subject="SAME"):
        self.page(url, text)
        self.judge(url, eval_resp(met, subject))

    def assess(self, pid, urls, dt=4000, who=None):
        self.advance(dt)
        self.as_(who or self.borrower)
        return self.c.assess(pid, urls)

    def report(self, pid, ref, outcome, borrower=None, who=None):
        self.as_(who or self.lender)
        return self.c.record_outcome((borrower or self.borrower).as_hex, pid, ref, outcome)

    def quote(self, pid, dt=0):
        return self.c.quote(self.borrower.as_hex, pid, self.t + dt)


@pytest.fixture
def env(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    direct_vm.check_pickling = True
    direct_vm.warp(iso(0))
    contract = direct_deploy("contracts/credo.py")
    # A real network delivers calldata addresses as genlayer Address, not raw bytes.
    from genlayer.py.types import Address  # importable once the loader has staged the SDK
    a, b, c = (Address(x) if isinstance(x, bytes) else x for x in (direct_alice, direct_bob, direct_charlie))
    d = Address("0x" + "04" * 20)
    e = Env(direct_vm, contract, a, b, c, d)
    e.warp(0)
    return e
