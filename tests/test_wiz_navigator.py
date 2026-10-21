import asyncio

import pytest

from wizwalker.extensions.wizsprinter import wiz_navigator

WORLD_DOOR_NAMES = [
    "Wizard City", "Krokotopia", "Marleybone", "MooShu", "Dragonspyre", "Grizzleheim", "Celestia",
    "Wysteria", "Zafaria", "Avalon", "Azteca", "Khrysalis",
]


class Window:
    def __init__(self, name, text=None, label=None):
        self._name, self.text, self.label = name, text, label

    async def name(self):
        return self._name

    async def maybe_text(self):
        return self.text


class SpiralDoor:
    """The World Gate's list: four worlds a page, a page shown a moment after its click."""

    def __init__(self, page: int, pages: int = 3):
        self.page, self.pages = page, pages
        self.clicks = []
        self.page_count = Window("pageCount")
        self.options = [Window(f"opt{i}") for i in range(4)]
        self._show()

    def _show(self):
        self.page_count.text = f"<center>{self.page}/{self.pages}</center>"
        for i, option in enumerate(self.options):
            index = (self.page - 1) * 4 + i
            option.label = WORLD_DOOR_NAMES[index] if index < len(WORLD_DOOR_NAMES) else ""

    def _turn(self, step):
        self.page = min(max(self.page + step, 1), self.pages)
        self._show()

    # --- the option window --------------------------------------------------

    async def children(self):
        return [self.page_count, *self.options]


class Player:
    def __init__(self, door: SpiralDoor):
        self.door = door
        self.npc_range = [True, True, False]
        self.mouse_handler = self
        self.root_window = self
        self.zone_changes = 0

    async def is_in_npc_range(self):
        return self.npc_range.pop(0) if self.npc_range else False

    async def send_key(self, key, seconds=0):
        pass

    async def wait_for_zone_change(self):
        self.zone_changes += 1

    async def get_windows_with_name(self, name):
        assert name == "optionWindow"
        return [self.door]

    async def activate_mouseless(self):
        pass

    async def deactivate_mouseless(self):
        pass

    async def click_window_with_name(self, name):
        self.door.clicks.append(name)
        loop = asyncio.get_running_loop()
        if name == "rightButton":
            loop.call_later(0.03, self.door._turn, 1)
        elif name == "leftButton":
            loop.call_later(0.03, self.door._turn, -1)


@pytest.fixture
def labels(monkeypatch):
    async def read_label(checkbox):
        return checkbox.label

    monkeypatch.setattr(wiz_navigator, "read_control_checkbox_text", read_label)


async def test_the_spiral_door_turns_one_click_a_page(labels):
    # The page was read straight after each click and the click repeated while it
    # read the same, so a page shown a frame late was clicked past, up to 30 times
    door = SpiralDoor(page=3)
    player = Player(door)
    await asyncio.wait_for(wiz_navigator.goToNewWorld(player, "Celestia"), 10)
    assert door.clicks.count("leftButton") == 2
    assert door.clicks.count("rightButton") == 1
    assert door.clicks[-2:] == ["wbtnCelestia", "teleportButton"]
    assert player.zone_changes == 1


async def test_a_world_on_the_first_page_needs_no_turning(labels):
    door = SpiralDoor(page=1)
    await asyncio.wait_for(wiz_navigator.goToNewWorld(Player(door), "Krokotopia"), 10)
    assert door.clicks == ["wbtnKrokotopia", "teleportButton"]


async def test_a_cancel_reaches_the_caller_of_to_zone(monkeypatch):
    # A bare except turned it into a failed trip and carried on
    class Client:
        async def zone_name(self):
            return "WizardCity/WC_Hub"

    async def cancelled(*args):
        raise asyncio.CancelledError()

    monkeypatch.setattr(wiz_navigator, "goToDestination", cancelled)
    with pytest.raises(asyncio.CancelledError):
        await wiz_navigator.toZone([Client()], "WizardCity/WC_Ravenwood")


async def test_reads_a_worlds_zone_map():
    stack = await wiz_navigator.createStack("WizardCity")
    assert stack and all(isinstance(path, list) for path in stack)
