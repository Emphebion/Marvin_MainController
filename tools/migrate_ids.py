#!/usr/bin/env python3
"""
migrate_ids.py — One-shot left-pad of every RFID `id` field to 10 hex chars.

The canonical RFID width on the wire is 10 hex characters (matches the firmware
sending 4 raw tag bytes plus the controller's left-pad). Historical configs
stored 8-char ids; this tool pads them with leading zeros so they line up with
the new controller-side `:010X` formatter.

Idempotent: running it twice is safe — files unchanged on the second run.

Usage:
    py -3 tools/migrate_ids.py
"""

import configparser
import os
import sys


SENTINEL_TARGET_WIDTH = 10


def pad_ids(path):
    """Pad every `id` option in ``path`` to SENTINEL_TARGET_WIDTH hex chars.

    Returns the number of sections rewritten, or -1 if the file does not exist.
    """
    if not os.path.isfile(path):
        return -1

    parser = configparser.ConfigParser()
    parser.read(path)

    changed = 0
    for section in parser.sections():
        if not parser.has_option(section, 'id'):
            continue
        current = parser.get(section, 'id').strip().upper()
        if len(current) < SENTINEL_TARGET_WIDTH:
            padded = current.zfill(SENTINEL_TARGET_WIDTH)
            parser.set(section, 'id', padded)
            changed += 1

    if changed:
        with open(path, 'w') as f:
            parser.write(f)

    return changed


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(here)
    targets = [
        os.path.join(project_root, 'characterconfig.txt'),
        os.path.join(project_root, 'itemconfig.txt'),
    ]

    rc = 0
    for path in targets:
        n = pad_ids(path)
        if n < 0:
            print(f"skip {os.path.basename(path)}: not found")
            rc = 1
        elif n == 0:
            print(f"ok   {os.path.basename(path)}: already 10-char wide")
        else:
            print(f"pad  {os.path.basename(path)}: {n} section(s) updated")
    return rc


if __name__ == '__main__':
    sys.exit(main())
