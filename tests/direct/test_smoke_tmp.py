from conftest import *

def test_smoke(env):
    pid = env.policy()
    assert pid == 1
    info = env.bind()
    assert info["challenge"] == f"credo-bind:{env.bkey}:1"
    env.evidence(EV1)
    r = env.assess(pid, [EV1])
    print(r)
    assert r["status"] == "QUALIFIED" and r["tier"] == 3
    print(env.quote(pid))
