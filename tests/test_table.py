"""
test_table.py — unit tests for _Table: segment graph construction,
LED data output, colour management.
"""

import configparser
import pytest
from _Table import _Table, _Segment, _Button


def make_table(table_config_file):
    parser = configparser.ConfigParser()
    return _Table(table_config_file)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_segment_count(self, table_config_file):
        table = make_table(table_config_file)
        assert len(table.segmentList) == 3

    def test_button_count(self, table_config_file):
        table = make_table(table_config_file)
        assert len(table.buttonList) == 1
        assert table.buttonList[0].name == 'east'

    def test_colors_loaded(self, table_config_file):
        table = make_table(table_config_file)
        assert 'black' in table.colorsLED
        assert table.colorsLED['black'] == [0, 0, 0]
        assert table.colorsLED['turquoise'] == [64, 224, 208]

    def test_status_loaded(self, table_config_file):
        table = make_table(table_config_file)
        assert table.status == 'Active'

    def test_segment_nrleds(self, table_config_file):
        table = make_table(table_config_file)
        for seg in table.segmentList:
            assert seg.nrLEDs == 5


# ---------------------------------------------------------------------------
# Segment lookups
# ---------------------------------------------------------------------------

class TestLookups:
    def test_get_segment_by_name(self, table_config_file):
        table = make_table(table_config_file)
        seg = table.getSegment('segm0')
        assert seg is not None
        assert seg.name == 'segm0'

    def test_get_segment_unknown_returns_none(self, table_config_file):
        table = make_table(table_config_file)
        assert table.getSegment('segm99') is None

    def test_get_button_by_name(self, table_config_file):
        table = make_table(table_config_file)
        btn = table.getButton('east')
        assert btn is not None
        assert btn.name == 'east'


# ---------------------------------------------------------------------------
# LED data
# ---------------------------------------------------------------------------

class TestLEDData:
    def test_led_data_length(self, table_config_file):
        """Total LED triples = sum of nrLEDs across all segments."""
        table = make_table(table_config_file)
        total = sum(seg.nrLEDs for seg in table.segmentList)
        data = table.getLEDData()
        assert len(data) == total

    def test_led_data_default_black(self, table_config_file):
        table = make_table(table_config_file)
        data = table.getLEDData()
        assert all(c == [0, 0, 0] for c in data)

    def test_set_all_table_leds(self, table_config_file):
        table = make_table(table_config_file)
        table.setAllTableLEDs([1, 2, 3])
        for seg in table.segmentList:
            assert all(v == [1, 2, 3] for v in seg.getLEDvalues())


# ---------------------------------------------------------------------------
# Segment internals
# ---------------------------------------------------------------------------

class TestSegment:
    def test_set_led_value(self):
        seg = _Segment('s0', 3, ['s1'], ['s2'], [0, 0, 0])
        seg.setLEDValue(1, [255, 0, 0])
        assert seg.getLEDvalues()[1] == [255, 0, 0]

    def test_set_led_value_out_of_range_ignored(self):
        seg = _Segment('s0', 3, ['s1'], ['s2'], [0, 0, 0])
        seg.setLEDValue(99, [255, 0, 0])  # should not raise
        assert len(seg.getLEDvalues()) == 3

    def test_flow_direction(self):
        seg = _Segment('s0', 3, ['s1'], ['s2'], [0, 0, 0])
        seg.addSegmentFlow(1)
        assert seg.getLastSegmentFlow() == 1

    def test_clear_segment(self):
        seg = _Segment('s0', 3, ['s1'], ['s2'], [0, 0, 0])
        seg.setLEDValue(0, [100, 100, 100])
        seg.addSegmentFlow(1)
        seg.clearSegment([0, 0, 0])
        assert all(v == [0, 0, 0] for v in seg.getLEDvalues())
        assert seg.flow == []


# ---------------------------------------------------------------------------
# Button
# ---------------------------------------------------------------------------

class TestButton:
    def test_get_random_button_segment(self, table_config_file):
        table = make_table(table_config_file)
        btn = table.getButton('east')
        seg_name = btn.getRandomButtonSegment()
        assert seg_name in ['segm0', 'segm1']  # east flow+counter
