"""
test_items.py — unit tests for _Items: connect/disconnect, overload, node use,
single-object invariant, and hot-reload.
"""

import configparser
import pytest
from _Items import _Items, Item


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_items(item_config_file):
    return _Items(item_config_file)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_item_count(self, item_config_file):
        items = make_items(item_config_file)
        assert len(items.items) == 2

    def test_items_and_ids_same_object(self, item_config_file):
        """items dict and itemsIDs dict must point to the same Item instance."""
        items = make_items(item_config_file)
        for name, item in items.items.items():
            assert items.itemsIDs[item.ID] is item

    def test_initial_connected_state(self, item_config_file):
        items = make_items(item_config_file)
        assert items.items['widget'].connected is False
        assert items.items['gadget'].connected is True

    def test_source_loaded(self, item_config_file):
        items = make_items(item_config_file)
        assert items.source == 20


# ---------------------------------------------------------------------------
# Node use
# ---------------------------------------------------------------------------

class TestNodeUse:
    def test_node_use_counts_only_connected(self, item_config_file):
        items = make_items(item_config_file)
        # only gadget is connected, load=8
        assert items.calculateNodeUse() == 8

    def test_node_use_zero_when_all_disconnected(self, item_config_file):
        items = make_items(item_config_file)
        items.items['gadget'].disconnectItem()
        assert items.calculateNodeUse() == 0


# ---------------------------------------------------------------------------
# Connect / disconnect
# ---------------------------------------------------------------------------

class TestConnection:
    def test_connect_item(self, item_config_file):
        items = make_items(item_config_file)
        items.currentItemName = 'widget'
        items.connectItem()
        assert items.items['widget'].connected is True

    def test_disconnect_item(self, item_config_file):
        items = make_items(item_config_file)
        items.currentItemName = 'gadget'
        items.disconnectItem()
        assert items.items['gadget'].connected is False

    def test_connect_persists_to_file(self, item_config_file):
        items = make_items(item_config_file)
        items.currentItemName = 'widget'
        items.connectItem()
        parser = configparser.ConfigParser()
        parser.read(item_config_file)
        assert parser.getint('widget', 'connected') == 1

    def test_disconnect_all(self, item_config_file):
        items = make_items(item_config_file)
        items.disconnectAll()
        assert all(not item.connected for item in items.items.values())

    def test_overload_disconnects_all(self, item_config_file):
        """Connecting both items exceeds source=20 (5+8=13 is fine, but
        if we lower the source we can trigger overload). We patch source."""
        items = make_items(item_config_file)
        items.source = 5   # force overload on next connect
        items.currentItemName = 'widget'
        items.connectItem()
        # overload: all items should be disconnected
        assert all(not item.connected for item in items.items.values())

    def test_connect_updates_both_dicts(self, item_config_file):
        """After connect, both items and itemsIDs reflect the new state."""
        items = make_items(item_config_file)
        items.currentItemName = 'widget'
        items.connectItem()
        assert items.itemsIDs["000003E9"].connected is True


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------

class TestLookup:
    def test_get_item_by_id(self, item_config_file):
        items = make_items(item_config_file)
        item = items.getItemByID("000003E9")
        assert item.name == 'widget'

    def test_get_item_by_unknown_id_returns_none(self, item_config_file):
        items = make_items(item_config_file)
        assert items.getItemByID("0000270F") is None


# ---------------------------------------------------------------------------
# write_tag / hot-reload
# ---------------------------------------------------------------------------

class TestWriteTag:
    def test_write_tag_updates_memory(self, item_config_file):
        items = make_items(item_config_file)
        items.write_tag('widget', '000015B3')
        assert items.items['widget'].ID == '000015B3'
        assert '000015B3' in items.itemsIDs

    def test_write_tag_persists_to_file(self, item_config_file):
        items = make_items(item_config_file)
        items.write_tag('widget', '000015B3')
        parser = configparser.ConfigParser()
        parser.read(item_config_file)
        assert parser.get('widget', 'id') == '000015B3'

    def test_reload_preserves_connected_state(self, item_config_file):
        items = make_items(item_config_file)
        items.currentItemName = 'widget'
        items.connectItem()
        items.reload()
        assert items.items['widget'].connected is True
