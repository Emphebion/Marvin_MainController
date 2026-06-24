"""
_CrashTracer.py — Forensic crash logger for MARVIN.

Replaces the original append-everything crash log that, on the 2026-06-24
overnight cascade, grew to ~7 GB of identical S1 tracebacks and buried the
first (and only useful) entry.

Design:
    * The *first* novel failure is always written in full, including a
      snapshot of the last 500 stdout lines (FRAME B / FRAME T / device
      messages — the diagnostic signal for the deep-dive's top causes).
    * Subsequent identical failures (same exception class + filename + line)
      bump a counter that is flushed at most once per minute as a one-line
      summary. The original entry stays at the top of the file.
    * Genuinely-new failures after the first are written, capped.
    * Two independent size caps guarantee disk safety even if the dedup
      logic above ever fails: per-process write cap (default 256 KB) and
      per-file rotate-on-open cap (default 10 MB).

See docs/plans/260624_crash_trace_and_recovery.md for the full rationale.
"""

import collections
import os
import sys
import time
import traceback


class _ConsoleBuffer:
    """Tee for sys.stdout: writes through to the real stream and also keeps
    the last ``capacity`` lines in memory for inclusion in crash dumps.

    Each ``write()`` is split on newlines so the deque holds whole lines,
    not arbitrary chunk boundaries — keeps the snapshot readable.
    """

    def __init__(self, real_stdout, capacity=500):
        self._real = real_stdout
        self._buf = collections.deque(maxlen=capacity)
        self._partial = ""

    def write(self, s):
        try:
            self._real.write(s)
        except Exception:
            pass
        # Accumulate partial line, then flush completed lines into the deque.
        text = self._partial + s
        lines = text.splitlines(keepends=True)
        if lines and not lines[-1].endswith(("\n", "\r")):
            self._partial = lines.pop()
        else:
            self._partial = ""
        for line in lines:
            self._buf.append(line)

    def flush(self):
        try:
            self._real.flush()
        except Exception:
            pass

    def isatty(self):
        try:
            return self._real.isatty()
        except Exception:
            return False

    def snapshot(self):
        """Return the buffered lines as a single string, oldest first."""
        out = "".join(self._buf)
        if self._partial:
            out += self._partial
        return out


class _CrashTracer:
    """Dedup-aware crash logger with hard size caps.

    Lifecycle:
        tracer = _CrashTracer(path, console_buffer)
        ...
        try: ...
        except Exception as exc:
            tracer.record(state, exc)
    """

    _SEPARATOR = "=" * 60
    _REPEAT_FLUSH_INTERVAL_S = 60.0

    def __init__(self, path, console_buffer=None,
                 max_per_process_bytes=256 * 1024,
                 max_file_bytes=10 * 1024 * 1024):
        self.path = path
        self._console = console_buffer
        self._max_per_process = max_per_process_bytes
        self._bytes_written = 0
        self._first_signature = None
        self._first_written = False
        self._repeat_count = 0
        # Seed to "now" so the first repeat doesn't immediately flush
        # (the comparison is then "60 s since process start", not "60 s
        # since the unix epoch", which would trigger on the first repeat).
        self._last_repeat_flush = time.time()
        self._secondary_signatures = set()
        self._pid = os.getpid()
        self._start_time = time.time()

        self._rotate_if_oversized(max_file_bytes)

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #

    def record(self, state_value, exc):
        """Log ``exc`` raised while in state ``state_value``.

        First novel failure: full traceback + console snapshot.
        Repeat of first failure: counter increment, flushed at most once/min.
        New failure after first: short entry, capped to a handful unique sigs.
        """
        sig = self.signature(exc)
        if self._first_signature is None:
            self._first_signature = sig
            self._write_first(state_value, exc, sig)
            self._first_written = True
            return
        if sig == self._first_signature:
            self._repeat_count += 1
            self._maybe_flush_repeat_count()
            return
        if sig in self._secondary_signatures:
            # Already noted this distinct follow-up; treat like a repeat
            # to avoid a slow drift to disk-fill if many distinct bugs fire.
            self._repeat_count += 1
            self._maybe_flush_repeat_count()
            return
        self._secondary_signatures.add(sig)
        self._write_secondary(state_value, exc, sig)

    @staticmethod
    def signature(exc):
        """Stable (exception class, final-frame file, final-frame line) tuple.

        Ignores message text so transient values (addresses, timestamps,
        item IDs) don't fragment the dedup key.
        """
        tb = exc.__traceback__
        if tb is None:
            return (type(exc).__name__, "<no-traceback>", 0)
        while tb.tb_next is not None:
            tb = tb.tb_next
        return (type(exc).__name__,
                tb.tb_frame.f_code.co_filename,
                tb.tb_lineno)

    # ------------------------------------------------------------------ #
    # Writers                                                            #
    # ------------------------------------------------------------------ #

    def _write_first(self, state_value, exc, sig):
        parts = [
            self._SEPARATOR,
            self._header(state_value, exc, sig),
            f"RUN: pid={self._pid}  uptime_s={int(time.time() - self._start_time)}",
            f"SIG: {sig!r}",
            "",
            "-- Traceback --",
            "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).rstrip(),
        ]
        if self._console is not None:
            parts.extend([
                "",
                "-- Console (oldest first) --",
                self._console.snapshot().rstrip(),
            ])
        parts.append("")
        self._append("\n".join(parts) + "\n")

    def _write_secondary(self, state_value, exc, sig):
        parts = [
            self._SEPARATOR,
            self._header(state_value, exc, sig) + "  (new signature after first)",
            f"SIG: {sig!r}",
            "",
            "-- Traceback --",
            "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).rstrip(),
            "",
        ]
        self._append("\n".join(parts) + "\n")

    def _maybe_flush_repeat_count(self):
        now = time.time()
        if now - self._last_repeat_flush < self._REPEAT_FLUSH_INTERVAL_S:
            return
        self._last_repeat_flush = now
        line = (f"-- repeat: {self._repeat_count} more occurrences of "
                f"{self._first_signature!r} since first entry --\n")
        self._append(line)

    # ------------------------------------------------------------------ #
    # Helpers                                                            #
    # ------------------------------------------------------------------ #

    def _header(self, state_value, exc, sig):
        cls, fname, lineno = sig
        return (f"{time.strftime('%Y-%m-%d %H:%M:%S')}  state={state_value}  "
                f"exc={cls}  origin={os.path.basename(fname)}:{lineno}")

    def _append(self, text):
        """Write ``text`` to the crash log, honouring the per-process cap.

        Once the cap is reached, fall back to stderr so the first crash and
        a handful of follow-ups always make it to disk but a pathological
        loop can't ever fill it.
        """
        encoded = text.encode("utf-8", errors="replace")
        if self._bytes_written + len(encoded) > self._max_per_process:
            try:
                sys.__stderr__.write(text)
            except Exception:
                pass
            return
        try:
            with open(self.path, "ab") as f:
                f.write(encoded)
            self._bytes_written += len(encoded)
        except Exception:
            # Disk full, permission error, etc. — fall back to stderr.
            try:
                sys.__stderr__.write(text)
            except Exception:
                pass

    def _rotate_if_oversized(self, max_file_bytes):
        """If the existing log exceeds ``max_file_bytes``, move it to .1 and
        start fresh. Overwrites any prior .1 — a single previous run's log
        is kept as evidence, no further history.
        """
        try:
            size = os.path.getsize(self.path)
        except OSError:
            return
        if size <= max_file_bytes:
            return
        rotated = self.path + ".1"
        try:
            if os.path.exists(rotated):
                os.remove(rotated)
            os.replace(self.path, rotated)
        except OSError:
            # If rotation fails, truncate as a last resort so the new run
            # can't append to a multi-GB file.
            try:
                open(self.path, "wb").close()
            except OSError:
                pass
