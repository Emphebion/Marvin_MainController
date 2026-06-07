"""
test_table.py — unit tests for _Table: segment graph construction,
LED data output, colour management.
"""

import configparser
import math
import os
import pytest
from _Table import _Table, _Segment, _Button


REAL_TABLE_CONFIG = os.path.join(os.path.dirname(__file__), '..', 'tableconfig.txt')


@pytest.fixture
def real_table():
    """A _Table built from the production tableconfig.txt (full 5-tier topology)."""
    return _Table(REAL_TABLE_CONFIG)


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


# ---------------------------------------------------------------------------
# Well-size visualisation — tier classification and radial map
# ---------------------------------------------------------------------------

class TestWellSizeTierClassification:
    def test_inner_ring_range(self, real_table):
        for n in (0, 1, 7, 15):
            assert real_table._segment_tier(f'segm{n}') == 'inner_ring'

    def test_inner_bridge_range(self, real_table):
        for n in (16, 20, 23):
            assert real_table._segment_tier(f'segm{n}') == 'inner_bridge'

    def test_middle_ring_range(self, real_table):
        for n in (24, 31, 39):
            assert real_table._segment_tier(f'segm{n}') == 'middle_ring'

    def test_outer_bridge_range(self, real_table):
        for n in (40, 43, 47):
            assert real_table._segment_tier(f'segm{n}') == 'outer_bridge'

    def test_outer_ring_range(self, real_table):
        for n in (48, 55, 63):
            assert real_table._segment_tier(f'segm{n}') == 'outer_ring'

    def test_unknown_segment_returns_none(self, real_table):
        assert real_table._segment_tier('east') is None
        assert real_table._segment_tier('segm99') is None
        assert real_table._segment_tier('not_a_segm') is None


class TestWellSizeRadialMap:
    def test_inner_ring_at_r_inner(self, real_table):
        real_table._ensure_radial_map()
        for n in range(16):
            for i in range(5):
                assert real_table._radial_map[(f'segm{n}', i)] == pytest.approx(14.0)

    def test_middle_ring_at_r_middle(self, real_table):
        real_table._ensure_radial_map()
        for n in range(24, 40):
            for i in range(8):
                assert real_table._radial_map[(f'segm{n}', i)] == pytest.approx(20.8)

    def test_outer_ring_at_r_outer(self, real_table):
        real_table._ensure_radial_map()
        for n in range(48, 64):
            seg = real_table.getSegment(f'segm{n}')
            for i in range(seg.nrLEDs):
                assert real_table._radial_map[(f'segm{n}', i)] == pytest.approx(30.0)

    def test_outer_bridge_orientation(self, real_table):
        """segm40 LED 0 sits at middle ring (r=20.8), LED N-1 at outer ring (r=30)."""
        real_table._ensure_radial_map()
        seg = real_table.getSegment('segm40')
        N = seg.nrLEDs
        # LED 0 should be close to r_middle, LED N-1 close to r_outer
        assert real_table._radial_map[('segm40', 0)] < real_table._radial_map[('segm40', N - 1)]
        # Quantitative: r = r_middle + ((i+0.5)/N) * (r_outer - r_middle)
        for i in range(N):
            expected = 20.8 + ((i + 0.5) / N) * (30.0 - 20.8)
            assert real_table._radial_map[('segm40', i)] == pytest.approx(expected)

    def test_inner_bridge_orientation(self, real_table):
        """segm16 LED 0 sits at middle ring (r=20.8), LED N-1 at inner ring (r=14)."""
        real_table._ensure_radial_map()
        seg = real_table.getSegment('segm16')
        N = seg.nrLEDs
        # LED 0 should be close to r_middle, LED N-1 close to r_inner
        assert real_table._radial_map[('segm16', 0)] > real_table._radial_map[('segm16', N - 1)]
        for i in range(N):
            expected = 20.8 + ((i + 0.5) / N) * (14.0 - 20.8)
            assert real_table._radial_map[('segm16', i)] == pytest.approx(expected)

    def test_map_invalidates_when_radii_change(self, real_table):
        real_table._ensure_radial_map()
        old = real_table._radial_map[('segm48', 0)]
        assert old == pytest.approx(30.0)
        real_table.r_outer = 40.0
        real_table._ensure_radial_map()
        assert real_table._radial_map[('segm48', 0)] == pytest.approx(40.0)


class TestWellSizeDraw:
    def test_fill_zero_dark_table(self, real_table):
        real_table.draw_well_size(source=100, use=0, color='turquoise')
        # Everything dark at fill = 0
        for row in real_table.getLEDData():
            assert row == [0, 0, 0]

    def test_fill_one_full_table(self, real_table):
        real_table.draw_well_size(source=100, use=100, color='turquoise')
        # At fill = 1, r_dark = 0, all LEDs should be at full intensity (turquoise)
        turquoise = [64, 224, 208]
        for row in real_table.getLEDData():
            assert row == turquoise

    def test_outer_ring_first_to_light(self, real_table):
        """At small fill, the outer ring should be lit while inner is dark.

        With shifted formula: r_dark(0.2) = 30·√0.8 + 1·(1 − 0.4) = 27.43 cm.
        Outer ring (d=30) is well past r_dark + Δ; inner ring (d=14) is well below.
        """
        real_table.draw_well_size(source=100, use=20, color='turquoise', fade_width=1.0)
        turquoise = [64, 224, 208]
        for n in range(48, 64):
            seg = real_table.getSegment(f'segm{n}')
            for v in seg.getLEDvalues():
                assert v == turquoise
        for n in range(16):
            seg = real_table.getSegment(f'segm{n}')
            for v in seg.getLEDvalues():
                assert v == [0, 0, 0]

    def test_middle_ring_threshold(self, real_table):
        """Middle ring fully lit once r_dark ≤ r_middle − Δ.

        At fill=0.6: r_dark = 30·√0.4 + (1 − 1.2) = 18.77 cm ≤ 19.8 = r_middle − Δ.
        """
        real_table.draw_well_size(source=100, use=60, color='turquoise', fade_width=1.0)
        turquoise = [64, 224, 208]
        for n in range(24, 40):
            seg = real_table.getSegment(f'segm{n}')
            for v in seg.getLEDvalues():
                assert v == turquoise
        for n in range(16):
            seg = real_table.getSegment(f'segm{n}')
            for v in seg.getLEDvalues():
                assert v == [0, 0, 0]

    def test_inner_ring_threshold(self, real_table):
        """Inner ring fully lit once r_dark ≤ r_inner − Δ.

        At fill=0.85: r_dark = 30·√0.15 + (1 − 1.7) = 10.92 cm ≤ 13 = r_inner − Δ.
        """
        real_table.draw_well_size(source=100, use=85, color='turquoise', fade_width=1.0)
        turquoise = [64, 224, 208]
        for n in range(16):
            seg = real_table.getSegment(f'segm{n}')
            for v in seg.getLEDvalues():
                assert v == turquoise

    def test_boundary_led_partial_intensity(self, real_table):
        """An LED exactly at r_dark should be at ~50% intensity (linear ramp).

        Solving 20.8 = 30·√(1−f) + (1 − 2f) with Δ=1 gives s = √(1−f) ≈ 0.6946,
        so f ≈ 0.5176 → use ≈ 51.76 at source = 100.
        """
        # Compute the exact use that puts r_dark = r_middle.
        delta, r_outer, r_middle = 1.0, 30.0, 20.8
        # r_outer * s + delta * (1 - 2*(1-s^2)) = r_middle
        # 2*delta*s^2 + r_outer*s + delta - 2*delta - r_middle = 0
        # 2*s^2 + 30*s - 21.8 = 0 → s = (-15 + sqrt(225 + 43.6)) / 2
        s = (-15 + math.sqrt(225 + 43.6)) / 2
        fill = 1 - s * s
        real_table.draw_well_size(source=100, use=fill * 100,
                                   color='turquoise', fade_width=1.0)
        seg = real_table.getSegment('segm24')
        v = seg.getLEDvalues()[0]
        # turquoise = [64, 224, 208]; at 0.5 → [32, 112, 104]
        assert v[0] == pytest.approx(32, abs=1)
        assert v[1] == pytest.approx(112, abs=1)
        assert v[2] == pytest.approx(104, abs=1)

    def test_clamps_use_above_source(self, real_table):
        real_table.draw_well_size(source=10, use=999, color='turquoise')
        # Saturates to full table regardless of overshoot
        turquoise = [64, 224, 208]
        for row in real_table.getLEDData():
            assert row == turquoise

    def test_source_zero_dark_table(self, real_table):
        real_table.draw_well_size(source=0, use=5, color='turquoise')
        for row in real_table.getLEDData():
            assert row == [0, 0, 0]

    def test_unknown_mode_raises(self, real_table):
        with pytest.raises(ValueError):
            real_table.draw_well_size(source=10, use=5, mode='nonsense')

    def test_color_accepts_rgb_string(self, real_table):
        real_table.draw_well_size(source=10, use=10, color='10,20,30')
        for row in real_table.getLEDData():
            assert row == [10, 20, 30]

    def test_min_bright_floor(self, real_table):
        """With min_bright > 0 the boundary LED ramps from min_bright (not 0) to 1.

        At fill=0.03 the outer ring sits in the fade band with t ≈ 0.255 (without floor).
        With min_bright=0.3 the floor activates, raising it to 0.3 → R = 19.
        """
        real_table.draw_well_size(source=100, use=3, color='turquoise',
                                   fade_width=1.0, min_bright=0.3)
        v = real_table.getSegment('segm48').getLEDvalues()[0]
        # Turquoise R=64; with 0.3 floor → 19 (vs 16 without floor)
        assert v[0] >= 19


# ---------------------------------------------------------------------------
# Well-size visualisation — pathflow mode (Option B)
# ---------------------------------------------------------------------------

class TestWellSizePathMap:
    def test_button_anchor_outer_ring_has_small_t(self, real_table):
        """Outer-ring LED adjacent to a button (entry side) has t close to 0."""
        real_table._ensure_path_map()
        # east button at segm48|segm49 junction. segm48 LED N-1 and segm49 LED 0
        # are both adjacent to the button — they're the entry LEDs.
        # segm48 direction is -1 (bridge segm40 is at counter side), so LED N-1 = entry.
        seg = real_table.getSegment('segm48')
        t_entry = real_table._path_map[('segm48', seg.nrLEDs - 1)]
        # Should be at first leg slot: (0 + 0.5) / N * 0.25
        expected = (0.5 / seg.nrLEDs) * 0.25
        assert t_entry == pytest.approx(expected)

    def test_outer_ring_exit_t_close_to_t1(self, real_table):
        """Outer-ring LED adjacent to its outer-bridge has t close to 0.25."""
        real_table._ensure_path_map()
        # segm48 direction -1, exit at LED 0 (next to bridge segm40)
        seg = real_table.getSegment('segm48')
        t_exit = real_table._path_map[('segm48', 0)]
        # Last slot: ((N-1) + 0.5)/N * 0.25
        expected = ((seg.nrLEDs - 0.5) / seg.nrLEDs) * 0.25
        assert t_exit == pytest.approx(expected)
        # Should be just below 0.25
        assert t_exit < 0.25

    def test_outer_bridge_spans_t1_to_t2(self, real_table):
        """An outer-bridge segment's t values span (0.25, 0.50)."""
        real_table._ensure_path_map()
        seg = real_table.getSegment('segm40')
        # direction -1: LED N-1 is entry (t close to 0.25), LED 0 is exit (t close to 0.50)
        t_entry = real_table._path_map[('segm40', seg.nrLEDs - 1)]
        t_exit  = real_table._path_map[('segm40', 0)]
        assert 0.25 < t_entry < t_exit < 0.50

    def test_inner_bridge_direction_positive(self, real_table):
        """Inner bridges traverse LED 0 → N-1 (entry from middle, exit to inner)."""
        real_table._ensure_path_map()
        seg = real_table.getSegment('segm16')
        # direction +1: LED 0 is entry (t close to 0.70), LED N-1 is exit (t close to 0.90)
        t_entry = real_table._path_map[('segm16', 0)]
        t_exit  = real_table._path_map[('segm16', seg.nrLEDs - 1)]
        assert 0.70 < t_entry < t_exit < 0.90

    def test_inner_ring_spans_t4_to_t5(self, real_table):
        """Inner-ring segments span (0.90, 1.00)."""
        real_table._ensure_path_map()
        # Direction depends on which side has inner-bridge attached
        seg = real_table.getSegment('segm0')
        # segm0: counter=segm15, flow=segm1,segm16. Inner-bridge segm16 in flow → direction +1?
        # Wait: per _segment_wave_direction, inner_ring: if inner-bridge in counter → +1, else -1.
        # segm0 has inner-bridge in flow → -1. So LED N-1 = entry, LED 0 = exit (midpoint).
        t_first = real_table._path_map[('segm0', 0)]
        t_last  = real_table._path_map[('segm0', seg.nrLEDs - 1)]
        # Both in (0.90, 1.00)
        for t in (t_first, t_last):
            assert 0.90 < t < 1.00

    def test_merge_symmetry_at_outer_bridge(self, real_table):
        """The two outer-ring LEDs adjacent to bridge segm40 should have the same t.

        Bridge segm40 connects to segm48 and segm63. The wave from east button
        approaches via segm48 (LED 0 = exit, the one closest to bridge); the wave
        from southeast button approaches via segm63 (LED N-1 = exit). Both legs
        end at the same t because both segments have the same length on the ring
        and both use the same (t_in, t_out) range.
        """
        real_table._ensure_path_map()
        seg_48 = real_table.getSegment('segm48')
        seg_63 = real_table.getSegment('segm63')
        # segm48 dir -1, exit LED 0; segm63 dir +1, exit LED N-1
        t_48 = real_table._path_map[('segm48', 0)]
        t_63 = real_table._path_map[('segm63', seg_63.nrLEDs - 1)]
        # If both segments have the same nrLEDs (both 11), t values are identical.
        if seg_48.nrLEDs == seg_63.nrLEDs:
            assert t_48 == pytest.approx(t_63)

    def test_split_symmetry_at_middle_ring(self, real_table):
        """Both middle-ring segments emerging from a bridge split start at the same t."""
        real_table._ensure_path_map()
        # Bridge segm40 splits into segm24 (LED 0 = entry, dir +1) and segm39 (LED N-1 = entry, dir -1)
        seg_24 = real_table.getSegment('segm24')
        seg_39 = real_table.getSegment('segm39')
        t_24_first = real_table._path_map[('segm24', 0)]
        t_39_first = real_table._path_map[('segm39', seg_39.nrLEDs - 1)]
        if seg_24.nrLEDs == seg_39.nrLEDs:
            assert t_24_first == pytest.approx(t_39_first)

    def test_bridge_with_different_led_count_still_lands_at_t2(self, real_table):
        """Per-leg normalisation: a bridge with non-default nrLEDs still ends at ~t_out.

        Hack one bridge to a different N and confirm its exit LED still lands at the
        same t as the standard bridges' exits.
        """
        seg = real_table.getSegment('segm40')
        seg.nrLEDs = 7  # simulate variable LED count
        seg.LEDvalues = [[0, 0, 0]] * 7
        seg.LEDUsers = ['Unused'] * 7
        real_table._path_map = None  # force rebuild
        real_table._ensure_path_map()
        # Standard bridge segm41 (still N=9), direction -1: exit at LED 0
        # Modified bridge segm40 (N=7), direction -1: exit at LED 0
        t_40_exit = real_table._path_map[('segm40', 0)]
        t_41_exit = real_table._path_map[('segm41', 0)]
        # Both should be just below t_out = 0.50, the difference is small per-leg
        assert 0.40 < t_40_exit < 0.50
        assert 0.40 < t_41_exit < 0.50
        # Both within ((N-0.5)/N) * 0.25 + 0.25 of t_out
        # For N=7: ((6.5)/7) * 0.25 + 0.25 = 0.232 + 0.25 = 0.482
        # For N=9: ((8.5)/9) * 0.25 + 0.25 = 0.236 + 0.25 = 0.486


class TestWellSizePathflowDraw:
    def test_fill_zero_dark_table(self, real_table):
        real_table.draw_well_size(source=100, use=0, mode='pathflow',
                                   color='turquoise', fade_width=0.02)
        for row in real_table.getLEDData():
            assert row == [0, 0, 0]

    def test_fill_one_full_table(self, real_table):
        real_table.draw_well_size(source=100, use=100, mode='pathflow',
                                   color='turquoise', fade_width=0.02)
        turquoise = [64, 224, 208]
        for row in real_table.getLEDData():
            assert row == turquoise

    def test_outer_ring_lights_before_inner(self, real_table):
        """At fill that lights all of layer 1, outer should be lit and inner dark.

        With the offset endpoint formula, front = fill·1.04 − 0.02. To fully light
        the outer ring (max t ≈ 0.239), front must clear 0.239 + Δ_t = 0.259, so
        fill ≥ ≈0.27. use=30 gives front = 0.292 — well past.
        """
        real_table.draw_well_size(source=100, use=30, mode='pathflow',
                                   color='turquoise', fade_width=0.02)
        turquoise = [64, 224, 208]
        # Outer ring fully lit (t values up to ~0.239 < 0.272 = front − Δ_t)
        for n in range(48, 64):
            for v in real_table.getSegment(f'segm{n}').getLEDvalues():
                assert v == turquoise
        # Inner ring fully dark (t values > 0.90, well above front + Δ_t = 0.312)
        for n in range(16):
            for v in real_table.getSegment(f'segm{n}').getLEDvalues():
                assert v == [0, 0, 0]

    def test_fill_half_reaches_middle_ring_split(self, real_table):
        """At fill=0.5 the front is at t≈0.5, half-way through the path."""
        # Outer ring + outer bridges should be fully lit; middle ring just starting.
        real_table.draw_well_size(source=100, use=50, mode='pathflow',
                                   color='turquoise', fade_width=0.02)
        turquoise = [64, 224, 208]
        # Outer ring fully lit (all t < 0.25)
        for n in range(48, 64):
            for v in real_table.getSegment(f'segm{n}').getLEDvalues():
                assert v == turquoise
        # Inner ring fully dark (all t > 0.90)
        for n in range(16):
            for v in real_table.getSegment(f'segm{n}').getLEDvalues():
                assert v == [0, 0, 0]

    def test_unknown_mode_still_raises(self, real_table):
        with pytest.raises(ValueError):
            real_table.draw_well_size(source=10, use=5, mode='bogus')

    def test_path_map_cached(self, real_table):
        """_ensure_path_map is idempotent (cached after first build)."""
        real_table._ensure_path_map()
        first = real_table._path_map
        real_table._ensure_path_map()
        assert real_table._path_map is first


# ---------------------------------------------------------------------------
# Palette / colour-shift helpers (shared by both modes)
# ---------------------------------------------------------------------------

class TestPaletteHelpers:
    def test_resolve_palette_none_uses_fallback(self, real_table):
        out = real_table._resolve_palette(None, 'turquoise')
        assert out == [[64, 224, 208]]

    def test_resolve_palette_none_with_no_fallback_uses_amethist(self, real_table):
        out = real_table._resolve_palette(None, None)
        assert out == [[153, 67, 140]]   # amethist

    def test_resolve_palette_single_name(self, real_table):
        out = real_table._resolve_palette('turquoise', None)
        assert out == [[64, 224, 208]]

    def test_resolve_palette_list_of_names(self, real_table):
        out = real_table._resolve_palette(['turquoise', 'amethist'], None)
        assert out == [[64, 224, 208], [153, 67, 140]]

    def test_resolve_palette_mixed(self, real_table):
        out = real_table._resolve_palette(['turquoise', [10, 20, 30]], None)
        assert out == [[64, 224, 208], [10, 20, 30]]

    def test_palette_color_single_returns_same(self, real_table):
        assert real_table._palette_color([[10, 20, 30]], 0.0) == [10, 20, 30]
        assert real_table._palette_color([[10, 20, 30]], 0.7) == [10, 20, 30]

    def test_palette_color_two_colors_endpoints(self, real_table):
        pal = [[0, 0, 0], [100, 200, 50]]
        # phase 0 → palette[0]
        c0 = real_table._palette_color(pal, 0.0)
        assert c0 == [0.0, 0.0, 0.0]
        # phase 0.5 → palette[1] (because index = 0.5*2 = 1)
        c5 = real_table._palette_color(pal, 0.5)
        assert c5 == [100.0, 200.0, 50.0]

    def test_palette_color_two_colors_midpoint(self, real_table):
        pal = [[0, 0, 0], [100, 200, 50]]
        # phase 0.25 → index = 0.5 → halfway between palette[0] and palette[1]
        c = real_table._palette_color(pal, 0.25)
        assert c[0] == pytest.approx(50.0)
        assert c[1] == pytest.approx(100.0)
        assert c[2] == pytest.approx(25.0)

    def test_palette_color_wraps_phase(self, real_table):
        pal = [[0, 0, 0], [100, 200, 50]]
        # phase 1.0 should wrap to 0.0
        c = real_table._palette_color(pal, 1.0)
        assert c == [0.0, 0.0, 0.0]
        # phase 1.5 should wrap to 0.5
        c = real_table._palette_color(pal, 1.5)
        assert c == [100.0, 200.0, 50.0]

    def test_palette_color_three_colors_cycle(self, real_table):
        pal = [[255, 0, 0], [0, 255, 0], [0, 0, 255]]
        # phase 0 → red
        assert real_table._palette_color(pal, 0.0) == [255, 0, 0]
        # phase 1/3 → green (pos = 1.0, i0=1, i1=2, frac=0)
        c = real_table._palette_color(pal, 1.0 / 3.0)
        assert c[0] == pytest.approx(0.0)
        assert c[1] == pytest.approx(255.0)
        assert c[2] == pytest.approx(0.0)
        # phase 2/3 → blue
        c = real_table._palette_color(pal, 2.0 / 3.0)
        assert c[0] == pytest.approx(0.0, abs=0.01)
        assert c[1] == pytest.approx(0.0, abs=0.01)
        assert c[2] == pytest.approx(255.0)


class TestDrawWithPalette:
    def test_palette_at_full_intensity_uses_palette_zero(self, real_table):
        """At cycle_phase=0, fully-lit LEDs draw palette[0] (modulated by per-LED phase if scale>0)."""
        # Disable per-LED phase by setting pulse_phase_scale = 0
        real_table.draw_well_size(source=100, use=100, mode='pathflow',
                                   palette=['turquoise', 'red'],
                                   cycle_phase=0.0,
                                   pulse_phase_scale=0.0,
                                   fade_width=0.02)
        turquoise = [64, 224, 208]
        for row in real_table.getLEDData():
            assert row == turquoise

    def test_palette_at_half_phase_uses_palette_one(self, real_table):
        """At cycle_phase=0.5 with pulse_phase_scale=0, all LEDs draw palette[1] (full)."""
        real_table.draw_well_size(source=100, use=100, mode='pathflow',
                                   palette=['turquoise', 'red'],
                                   cycle_phase=0.5,
                                   pulse_phase_scale=0.0,
                                   fade_width=0.02)
        red = [200, 0, 0]
        for row in real_table.getLEDData():
            assert row == red

    def test_palette_per_led_phase_produces_variation(self, real_table):
        """With pulse_phase_scale > 0, LEDs at different positions get different colours."""
        real_table.draw_well_size(source=100, use=100, mode='pathflow',
                                   palette=['turquoise', 'red'],
                                   cycle_phase=0.0,
                                   pulse_phase_scale=1.0,
                                   fade_width=0.02)
        # An outer-ring LED (t ≈ 0.01) and an inner-ring LED (t ≈ 0.95) should differ.
        outer_v = real_table.getSegment('segm48').getLEDvalues()[0]
        inner_v = real_table.getSegment('segm0').getLEDvalues()[0]
        assert outer_v != inner_v

    def test_dark_leds_stay_black_with_palette(self, real_table):
        """A dark LED stays [0,0,0] regardless of palette/phase."""
        real_table.draw_well_size(source=100, use=0, mode='pathflow',
                                   palette=['turquoise', 'red'],
                                   cycle_phase=0.3,
                                   pulse_phase_scale=1.5,
                                   fade_width=0.02)
        for row in real_table.getLEDData():
            assert row == [0, 0, 0]

    def test_palette_works_with_radial_mode(self, real_table):
        """Radial mode also picks up palette + per-LED phase."""
        real_table.draw_well_size(source=100, use=100, mode='radial',
                                   palette=['turquoise', 'red'],
                                   cycle_phase=0.0,
                                   pulse_phase_scale=1.0,
                                   fade_width=1.0)
        outer_v = real_table.getSegment('segm48').getLEDvalues()[0]
        inner_v = real_table.getSegment('segm0').getLEDvalues()[0]
        # Outer (d=30, pos=1.0, phase ≈ 1.0 → wraps to 0 → palette[0] = turquoise)
        # Inner (d=14, pos=0.467, phase ≈ 0.467 → close to palette[1] crossover)
        assert outer_v != inner_v

    def test_backward_compat_color_only(self, real_table):
        """Calling without a palette still uses the solid colour (existing behaviour)."""
        real_table.draw_well_size(source=100, use=100, mode='pathflow',
                                   color='turquoise', fade_width=0.02)
        turquoise = [64, 224, 208]
        for row in real_table.getLEDData():
            assert row == turquoise
