"""The planning phase's windows, found by their paths under it (CombatHandler's).

A search of the whole UI by name took about 30 ms a time, and took the first window
with the name, which can be another one.
"""

from __future__ import annotations

from types import SimpleNamespace

from wizwalker.extensions.wizsprinter.combat_backends.combat_api import DrawSpell, Move, MoveConfig
from wizwalker.extensions.wizsprinter.sprinty_combat import SprintyCombat


class _Window:
    def __init__(self, name: str, *children: _Window, visible: bool = True, grayed: bool = False):
        self._name = name
        self._children = list(children)
        self.visible = visible
        self.grayed = grayed

    async def name(self):
        return self._name

    async def children(self):
        return self._children

    async def is_visible(self):
        return self.visible

    async def is_control_grayed(self):
        return self.grayed

    async def get_child_by_name(self, name):
        for child in self._children:
            if child._name == name:
                return child
        raise ValueError(name)

    async def get_windows_with_name(self, name):
        raise AssertionError(f"the whole UI was searched for {name}")

    get_windows_with_type = get_windows_with_name


class _Mouse:
    def __init__(self, cards):
        self.cards = cards
        self.clicked = []

    async def click_window(self, window, **kwargs):
        self.clicked.append(window)
        if window._name == "Draw":
            next(card for card in self.cards if not card.visible).visible = True


def _ui(held: int):
    cards = [_Window(f"Card{i}", visible=i <= held) for i in range(1, 8)]
    draw = _Window("Draw")
    root = _Window(
        "root",
        # A grayed Draw ahead of the real one, the first a search by name finds
        _Window("Draw", grayed=True),
        _Window(
            "WorldView",
            _Window(
                "PlanningPhase",
                _Window(
                    "Alignment",
                    _Window(
                        "PlanningPhaseSubWindow",
                        _Window(
                            "SpellSelection",
                            _Window("Hand", *cards, _Window("PetCard")),
                            _Window("ActionButtons", _Window("Focus"), draw, _Window("Flee")),
                        ),
                    ),
                ),
            ),
        ),
    )
    return root, cards, draw


async def test_a_draw_clicks_the_draw_button_under_the_planning_phase():
    root, cards, draw = _ui(held=4)
    mouse = _Mouse(cards)
    combat = SprintyCombat(SimpleNamespace(root_window=root, mouse_handler=mouse), SimpleNamespace(cast_time=0))

    assert await combat.try_execute_config(MoveConfig(Move(DrawSpell(2)))) is True
    assert mouse.clicked == [draw, draw]
    assert await combat.get_num_card_windows() == 6


async def test_a_grayed_draw_button_draws_nothing():
    root, cards, draw = _ui(held=4)
    draw.grayed = True
    mouse = _Mouse(cards)
    combat = SprintyCombat(SimpleNamespace(root_window=root, mouse_handler=mouse), SimpleNamespace(cast_time=0))

    assert await combat.try_execute_config(MoveConfig(Move(DrawSpell(1)))) is True
    assert mouse.clicked == []
