"""
test_crash_tracer.py — unit tests for _CrashTracer and _ConsoleBuffer.

The tracer is the cascade-prevention layer that replaced the original
append-everything crash log (which grew to ~7 GB overnight on 2026-06-24).
A bug here silently disables the dedup guard, so coverage of the four
core behaviours — signature, dedup, rotate-on-open, per-process write cap —
is load-bearing for survival behaviour.
"""

import io
import os
import time

import pytest

from _CrashTracer import _ConsoleBuffer, _CrashTracer


# ---------------------------------------------------------------------------
# Helpers — make exceptions with predictable signatures
# ---------------------------------------------------------------------------

def _raise_a():
    raise ValueError('boom A')


def _raise_a_again():
    # Same exception class, same file, same line as repeated _raise_a calls,
    # but raised from a *different* line — distinct signature.
    raise ValueError('also boom A')


def _raise_b():
    raise RuntimeError('boom B')


def _captured(fn):
    try:
        fn()
    except Exception as e:
        return e
    pytest.fail(f"{fn.__name__} did not raise")


# ---------------------------------------------------------------------------
# _ConsoleBuffer
# ---------------------------------------------------------------------------

class TestConsoleBuffer:
    def test_capacity_drops_oldest_lines(self):
        buf = _ConsoleBuffer(io.StringIO(), capacity=3)
        buf.write('A\nB\nC\nD\n')
        assert buf.snapshot() == 'B\nC\nD\n'

    def test_passes_through_to_real_stdout(self):
        sink = io.StringIO()
        buf = _ConsoleBuffer(sink, capacity=10)
        buf.write('hello\n')
        assert sink.getvalue() == 'hello\n'

    def test_partial_lines_are_held_until_newline(self):
        buf = _ConsoleBuffer(io.StringIO(), capacity=10)
        buf.write('par')
        buf.write('tial\n')
        assert buf.snapshot() == 'partial\n'

    def test_snapshot_includes_dangling_partial(self):
        """A crash mid-print should still surface the unflushed text."""
        buf = _ConsoleBuffer(io.StringIO(), capacity=10)
        buf.write('full\n')
        buf.write('no-newline-yet')
        assert buf.snapshot() == 'full\nno-newline-yet'


# ---------------------------------------------------------------------------
# _CrashTracer.signature — stability is the contract dedup depends on
# ---------------------------------------------------------------------------

class TestSignature:
    def test_same_origin_same_signature(self):
        a = _captured(_raise_a)
        b = _captured(_raise_a)
        assert _CrashTracer.signature(a) == _CrashTracer.signature(b)

    def test_different_class_different_signature(self):
        a = _captured(_raise_a)      # ValueError
        b = _captured(_raise_b)      # RuntimeError
        assert _CrashTracer.signature(a) != _CrashTracer.signature(b)

    def test_different_origin_different_signature(self):
        a = _captured(_raise_a)
        b = _captured(_raise_a_again)
        # Same class but different raise-line → must split
        assert _CrashTracer.signature(a) != _CrashTracer.signature(b)

    def test_signature_ignores_message_text(self):
        def raise_with(msg):
            raise ValueError(msg)
        try:
            raise_with('first')
        except Exception as e1:
            sig1 = _CrashTracer.signature(e1)
        try:
            raise_with('second')
        except Exception as e2:
            sig2 = _CrashTracer.signature(e2)
        # Same raise site, different messages → same signature.
        assert sig1 == sig2

    def test_exception_with_no_traceback(self):
        """Stand-alone exception (never raised) has no traceback — must not crash."""
        sig = _CrashTracer.signature(ValueError('x'))
        assert sig[0] == 'ValueError'
        assert sig[1] == '<no-traceback>'


# ---------------------------------------------------------------------------
# _CrashTracer.record — dedup & cascade-prevention behaviour
# ---------------------------------------------------------------------------

class TestRecord:
    def test_first_failure_writes_full_entry(self, tmp_path):
        log = tmp_path / 'crash.log'
        t = _CrashTracer(str(log))
        t.record(1, _captured(_raise_a))
        content = log.read_text()
        assert 'ValueError' in content
        assert 'boom A' in content
        assert 'SIG:' in content
        assert 'RUN:' in content
        assert '-- Traceback --' in content

    def test_console_snapshot_included_on_first_entry(self, tmp_path):
        log = tmp_path / 'crash.log'
        cb = _ConsoleBuffer(io.StringIO())
        cb.write('FRAME B scrn=0x01\n')
        t = _CrashTracer(str(log), console_buffer=cb)
        t.record(1, _captured(_raise_a))
        assert 'FRAME B scrn=0x01' in log.read_text()
        assert '-- Console' in log.read_text()

    def test_repeat_of_first_signature_does_not_grow_log(self, tmp_path):
        log = tmp_path / 'crash.log'
        t = _CrashTracer(str(log))
        t.record(1, _captured(_raise_a))
        size = log.stat().st_size
        for _ in range(20):
            t.record(1, _captured(_raise_a))
        assert log.stat().st_size == size, \
            "repeats within the flush interval must not grow the log"

    def test_repeat_count_flushes_after_interval(self, tmp_path):
        """The repeat counter is allowed to flush once per minute."""
        log = tmp_path / 'crash.log'
        t = _CrashTracer(str(log))
        t.record(1, _captured(_raise_a))
        size_before_repeats = log.stat().st_size
        # Force the flush interval to have elapsed.
        t._last_repeat_flush = time.time() - (t._REPEAT_FLUSH_INTERVAL_S + 1)
        t.record(1, _captured(_raise_a))
        content = log.read_text()
        assert log.stat().st_size > size_before_repeats
        assert 'repeat:' in content

    def test_distinct_secondary_signature_is_logged(self, tmp_path):
        log = tmp_path / 'crash.log'
        t = _CrashTracer(str(log))
        t.record(1, _captured(_raise_a))
        size_a = log.stat().st_size
        t.record(1, _captured(_raise_b))
        content = log.read_text()
        assert log.stat().st_size > size_a
        assert 'boom A' in content and 'boom B' in content
        assert '(new signature after first)' in content

    def test_repeated_secondary_signature_dedups(self, tmp_path):
        """A secondary signature that itself recurs should not flood the log."""
        log = tmp_path / 'crash.log'
        t = _CrashTracer(str(log))
        t.record(1, _captured(_raise_a))
        t.record(1, _captured(_raise_b))
        size = log.stat().st_size
        for _ in range(10):
            t.record(1, _captured(_raise_b))
        assert log.stat().st_size == size


# ---------------------------------------------------------------------------
# Size caps — belt-and-braces against dedup ever failing
# ---------------------------------------------------------------------------

class TestSizeCaps:
    def test_oversized_log_is_rotated_to_dot_one(self, tmp_path):
        log = tmp_path / 'crash.log'
        log.write_bytes(b'x' * 200)
        _CrashTracer(str(log), max_file_bytes=100)
        assert (tmp_path / 'crash.log.1').exists()
        assert (tmp_path / 'crash.log.1').read_bytes() == b'x' * 200
        # The fresh log should be empty (or just not exist yet).
        assert not log.exists() or log.stat().st_size == 0

    def test_under_threshold_log_is_kept(self, tmp_path):
        log = tmp_path / 'crash.log'
        log.write_bytes(b'x' * 50)
        _CrashTracer(str(log), max_file_bytes=100)
        assert not (tmp_path / 'crash.log.1').exists()
        assert log.read_bytes() == b'x' * 50

    def test_per_process_cap_stops_writes(self, tmp_path):
        """Once the cap is reached, further records do not grow the log.

        Cap set well above one entry's size so the first record actually
        writes (and the file exists), but small enough that a hammering
        loop is caught within a few records.
        """
        log = tmp_path / 'crash.log'
        cap = 5000   # roughly 3-4 traceback entries
        t = _CrashTracer(str(log), max_per_process_bytes=cap)
        for _ in range(50):
            t.record(1, _captured(_raise_a))
            t.record(1, _captured(_raise_b))
        size = log.stat().st_size
        # Margin = one entry (~1.5 KB) for the last write that pushed past cap.
        assert size <= cap + 2000, \
            f"write cap breached: log grew to {size}B (cap was {cap})"
