"""
_atomic.py — Atomic file write helpers for MARVIN.

The Pi's SD card can stall for hundreds of milliseconds during wear-
levelling. If a stall plus a power loss (or kernel-level write reorder)
interrupts a config write mid-flush, the file is left half-written and
the next read fails — typically with configparser raising on a malformed
section header. The pattern below prevents readers from ever observing
a partially-written file:

    1. Write the full content to a sibling `.tmp` file.
    2. flush() + os.fsync() so the data is on the device, not in the
       kernel page cache.
    3. os.replace() the .tmp over the original. This is atomic on
       POSIX and (since Python 3.3) on Windows.

If any step fails, the .tmp is removed and the original is untouched —
callers see the same exception they would have seen from a plain open(w).

See docs/plans/260624_idle_crash_deepdive.md §K for the failure mode
this defends against.
"""

import os


def atomic_write_parser(parser, path):
    """Atomically write a configparser to `path`.

    Args:
        parser -- a configparser.ConfigParser (or compatible) instance
        path   -- destination file path (overwritten on success)

    Raises:
        OSError if the .tmp file cannot be created or the rename fails.
        Anything parser.write() raises (e.g. ValueError on bad interpolation).
    """
    tmp = path + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            parser.write(f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        # Best-effort cleanup so a failed write doesn't leak .tmp files.
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
