from types import SimpleNamespace

import pytest

from wizwalker import MemoryReadError, XYZ
from wizwalker.client import Client
from wizwalker.extensions.wizsprinter.sprinty_client import SprintyClient
from wizwalker.extensions.wizsprinter.wiz_sprinter import upgrade_clients


class Behavior:
    def __init__(self, type_name, aggressive=False):
        self.type_name = type_name
        self.aggressive = aggressive

    async def read_type_name(self):
        return self.type_name

    async def read_value_from_offset(self, offset, primitive):
        assert offset == 288
        return self.aggressive


class Entity:
    def __init__(self, name, gid, xyz, *, behaviors=(), unreadable=False):
        self.name, self.gid, self.xyz = name, gid, XYZ(*xyz)
        self.behaviors = list(behaviors)
        self.unreadable = unreadable

    async def global_id_full(self):
        return self.gid

    async def location(self):
        return self.xyz

    async def object_template(self):
        return SimpleNamespace(object_name=self._name)

    async def _name(self):
        return self.name

    async def inactive_behaviors(self):
        if self.unreadable:
            raise MemoryReadError(0)
        return self.behaviors


def mob(name, gid, xyz):
    return Entity(name, gid, xyz, behaviors=[Behavior("NPCBehavior", aggressive=True)])


@pytest.fixture
def world(monkeypatch):
    entities = [
        Entity("WispHealth", 1, (100, 0, 0)),
        Entity("WispHealth", 2, (2000, 0, 0)),
        Entity("WispMana", 3, (50, 0, 0)),
        mob("Ice Wraith", 4, (150, 0, 0)),
        Entity("Shopkeeper", 5, (10, 0, 0), behaviors=[Behavior("NPCBehavior", aggressive=False)]),
        Entity("Broken", 6, (0, 0, 0), unreadable=True),
    ]

    async def base_entities(self):
        return list(entities)

    monkeypatch.setattr(Client, "get_base_entity_list", base_entities)
    client = SprintyClient.__new__(SprintyClient)

    async def position():
        return XYZ(0, 0, 0)

    client.body = SimpleNamespace(position=position)
    client.teleported_to = []

    async def teleport(xyz, *args, **kwargs):
        client.teleported_to.append(tuple(xyz))

    client.teleport = teleport
    return client


async def test_finds_wisps_by_name(world):
    assert [e.gid for e in await world.get_health_wisps()] == [1, 2]
    assert [e.gid for e in await world.get_mana_wisps()] == [3]


async def test_leaves_out_excluded_entities(world):
    assert [e.gid for e in await world.get_health_wisps(excluded_ids={1})] == [2]


async def test_mobs_are_the_aggressive_npcs(world):
    assert [e.gid for e in await world.get_mobs()] == [4]


async def test_the_closest_of_several(world):
    assert (await world.find_closest_health_wisp()).gid == 1


async def test_only_safe_skips_what_stands_near_a_mob(world):
    # The near wisp is 50 units from the Ice Wraith
    assert (await world.find_closest_health_wisp(only_safe=True)).gid == 2


async def test_nothing_to_find_is_none(world):
    assert await world.find_closest_by_name("Unicorn") is None


async def test_teleports_to_the_closest_mob(world):
    assert await world.tp_to_closest_mob()
    assert world.teleported_to == [(150, 0, 0)]


async def test_a_teleport_to_nothing_is_false(world):
    assert await world.tp_to(None) is False


class Stats:
    def __init__(self, health, max_health, mana, max_mana, potions):
        self.values = dict(health=health, max_health=max_health, mana=mana, max_mana=max_mana, potions=potions)

    async def current_hitpoints(self):
        return self.values["health"]

    async def max_hitpoints(self):
        return self.values["max_health"]

    async def current_mana(self):
        return self.values["mana"]

    async def max_mana(self):
        return self.values["max_mana"]

    async def potion_charge(self):
        return self.values["potions"]


def wizard(**stats):
    client = SprintyClient.__new__(SprintyClient)
    client.stats = Stats(**stats)
    return client


@pytest.mark.parametrize(
    "health, mana, needs",
    [(1000, 100, False), (150, 100, True), (1000, 5, True)],
)
async def test_needs_a_potion_when_low(health, mana, needs):
    client = wizard(health=health, max_health=1000, mana=mana, max_mana=100, potions=1.0)
    assert await client.needs_potion() is needs


async def test_a_potion_is_used_only_when_there_is_one():
    client = wizard(health=100, max_health=1000, mana=100, max_mana=100, potions=0.5)
    assert await client.use_potion_if_needed() is False


def test_upgrading_clients_makes_them_sprinty():
    client = Client.__new__(Client)
    assert upgrade_clients([client]) == [client]
    assert isinstance(client, SprintyClient)
