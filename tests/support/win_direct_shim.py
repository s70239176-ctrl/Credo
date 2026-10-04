"""Host-only pytest plugin: Windows workaround for genlayer-test's Direct Mode loader.

Problem (reproduced with genlayer-test 0.29.2 on Windows, before any contract code runs):
`gltest.direct.loader._inject_message_to_fd0` creates a temp file, dup2()s it onto fd 0,
then `os.unlink()`s it while fd 0 still holds it open. Windows refuses with
`PermissionError: [WinError 32]`.

This plugin replaces ONLY that one function with an identical copy whose unlink is
deferred to interpreter exit. It does not touch `os.unlink` globally, the contract, or
the test package on disk. It is a no-op on non-Windows hosts.

Use:  pytest tests/direct -p tests.support.win_direct_shim   (or PYTHONPATH=. pytest -p ...)
"""
import atexit
import os
import sys
import tempfile

_pending: list[str] = []


def _cleanup() -> None:
    for path in _pending:
        try:
            os.unlink(path)
        except OSError:
            pass


def _patched_inject(vm) -> None:
    from genlayer.py import calldata
    from genlayer.py.types import Address

    def addr(v):
        return Address(v) if isinstance(v, bytes) else v

    encoded = calldata.encode({
        "contract_address": addr(vm._contract_address),
        "sender_address": addr(vm.sender),
        "origin_address": addr(vm.origin),
        "stack": [],
        "value": vm._value,
        "datetime": vm._datetime,
        "is_init": False,
        "chain_id": vm._chain_id,
        "entry_kind": 0,
        "entry_data": b"",
        "entry_stage_data": None,
    })
    fd, path = tempfile.mkstemp()
    try:
        os.write(fd, encoded)
        os.lseek(fd, 0, os.SEEK_SET)
        vm._original_stdin_fd = os.dup(0)
        os.dup2(fd, 0)
    finally:
        os.close(fd)
        _pending.append(path)  # unlink deferred: fd 0 still references the file


def pytest_configure(config) -> None:
    if sys.platform != "win32":
        return
    import gltest.direct.loader as loader

    loader._inject_message_to_fd0 = _patched_inject
    atexit.register(_cleanup)
