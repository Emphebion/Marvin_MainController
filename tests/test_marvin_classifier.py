"""
test_marvin_classifier.py — tests for the catch-all classifier in MARVIN.py.

The classifier is the cascade-prevention guard added in PR B. A bug here
silently downgrades the response to "always retry", which is exactly the
behaviour that produced the 7 GB overnight log on 2026-06-24.
"""

import collections
import errno

import pytest

from MARVIN import _classify, _MIN_RECOVERY_INTERVAL_S, _RECENT_SIGS_LEN


SIG = ('ValueError', 'somefile.py', 42)


class TestClassify:
    def test_novel_exception_retries(self):
        assert _classify(ValueError('x'), SIG, collections.deque()) == 'retry'

    def test_repeated_signature_enters_service_mode(self):
        recent = collections.deque([SIG])
        assert _classify(ValueError('x'), SIG, recent) == 'service_mode'

    def test_memory_error_enters_service_mode_even_when_novel(self):
        assert _classify(MemoryError(), SIG, collections.deque()) == 'service_mode'

    def test_enospc_enters_service_mode(self):
        exc = OSError(errno.ENOSPC, 'No space left on device')
        assert _classify(exc, SIG, collections.deque()) == 'service_mode'

    def test_other_oserrors_retry(self):
        """Generic OSError (e.g. permission denied on a config write) is
        treated as recoverable input, not as a fatal resource exhaustion."""
        exc = OSError(errno.EACCES, 'Permission denied')
        assert _classify(exc, SIG, collections.deque()) == 'retry'

    def test_systemexit_propagates(self):
        assert _classify(SystemExit(), SIG, collections.deque()) == 'propagate'

    def test_keyboardinterrupt_propagates(self):
        assert _classify(KeyboardInterrupt(), SIG, collections.deque()) == 'propagate'

    def test_repeated_check_uses_sig_identity_not_exception_identity(self):
        """A *new* exception object with the same signature still escalates —
        because that's exactly what the overnight cascade looked like (a
        fresh ValueError per loop iteration, all at the same origin)."""
        recent = collections.deque([SIG])
        fresh_exc = ValueError('a')
        another_fresh_exc = ValueError('b')
        assert _classify(fresh_exc, SIG, recent) == 'service_mode'
        assert _classify(another_fresh_exc, SIG, recent) == 'service_mode'

    def test_memory_error_does_not_need_signature_match(self):
        """MemoryError is fatal first time — no need to wait for a second
        occurrence (the second might never come; the process may be dead)."""
        assert _classify(MemoryError(), SIG, collections.deque()) == 'service_mode'


class TestModuleConstants:
    """Sanity checks on the rate limit + deque length — defaults that escape
    review accidentally have been the source of past regressions."""

    def test_recovery_interval_is_at_least_500ms(self):
        # Lower than this and a tight cascade can still beat the dedup
        # tracer's signature-write path.
        assert _MIN_RECOVERY_INTERVAL_S >= 0.5

    def test_recent_sigs_length_is_at_least_2(self):
        # Need 2 just to detect a repeating signature; 5+ is safer.
        assert _RECENT_SIGS_LEN >= 2
