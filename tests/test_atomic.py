"""
test_atomic.py — unit tests for atomic_write_parser.

The atomic-rename pattern is what prevents an SD-card stall + power loss
from leaving readers staring at a half-written config (deep-dive case K).
A bug here re-introduces the failure mode silently.
"""

import configparser
import os

import pytest

from _atomic import atomic_write_parser


def _make_parser():
    p = configparser.ConfigParser()
    p.add_section('common')
    p.set('common', 'names', 'a,b,c')
    p.add_section('a')
    p.set('a', 'id', '00000001')
    return p


class TestAtomicWriteParser:
    def test_writes_full_content(self, tmp_path):
        path = str(tmp_path / 'cfg.txt')
        atomic_write_parser(_make_parser(), path)
        rp = configparser.ConfigParser()
        rp.read(path)
        assert rp.get('common', 'names') == 'a,b,c'
        assert rp.get('a', 'id') == '00000001'

    def test_no_tmp_file_left_behind_on_success(self, tmp_path):
        path = str(tmp_path / 'cfg.txt')
        atomic_write_parser(_make_parser(), path)
        assert not os.path.exists(path + '.tmp')
        assert os.path.exists(path)

    def test_overwrites_existing_file_atomically(self, tmp_path):
        path = str(tmp_path / 'cfg.txt')
        # Pre-populate with stale content.
        with open(path, 'w', encoding='utf-8') as f:
            f.write('[old]\nfoo = bar\n')

        atomic_write_parser(_make_parser(), path)
        rp = configparser.ConfigParser()
        rp.read(path)
        # Old section is gone; new content is present.
        assert not rp.has_section('old')
        assert rp.has_section('common')

    def test_original_untouched_when_write_raises(self, tmp_path, monkeypatch):
        """If parser.write raises, the original file is left intact and no
        .tmp leaks. That's the failure-atomicity guarantee."""
        path = str(tmp_path / 'cfg.txt')
        good = _make_parser()
        atomic_write_parser(good, path)

        bad = _make_parser()
        # Force the write step to blow up.
        def boom(*_args, **_kw):
            raise RuntimeError('disk full simulator')
        monkeypatch.setattr(bad, 'write', boom)

        with pytest.raises(RuntimeError, match='disk full'):
            atomic_write_parser(bad, path)

        # Original survived intact.
        rp = configparser.ConfigParser()
        rp.read(path)
        assert rp.get('common', 'names') == 'a,b,c'
        # No leaked .tmp file.
        assert not os.path.exists(path + '.tmp')

    def test_works_when_target_does_not_exist_yet(self, tmp_path):
        """First-ever write must create the file without complaining about
        a missing target."""
        path = str(tmp_path / 'fresh.txt')
        assert not os.path.exists(path)
        atomic_write_parser(_make_parser(), path)
        assert os.path.exists(path)
