"""`turn_acted`: whether the round did anything with a card.

A host judging a stalled fight needs it, and `try_execute_config`'s result cannot answer:
it is True for a pass, and for a discard that found nothing to throw away.
"""

from __future__ import annotations

import pytest
from lark import Lark
from wizwalker.extensions.wizsprinter import sprinty_combat
from wizwalker.extensions.wizsprinter.combat_backends.combat_config_parser import (
    TreeToConfig,
    get_sprinty_grammar,
)
from wizwalker.extensions.wizsprinter.combat_backends.config_backend import CombatConfigProvider
from wizwalker.memory import EffectTarget, SpellEffects

from .fakes import Card, Effect, fake_combat

_ATTACK = [Effect(SpellEffects.damage, EffectTarget.enemy_single, 500)]
_ENCHANT = [Effect(SpellEffects.modify_card_outgoing_damage, EffectTarget.spell)]


@pytest.fixture(scope="module")
def move():
    """The first priority of a one-line DSL. One grammar per module: Lark costs ~77 ms to build."""
    parser = Lark(get_sprinty_grammar())

    def _parse(dsl: str):
        return TreeToConfig().transform(parser.parse(dsl)).infinite_rounds[0].priorities[0]

    return _parse


@pytest.fixture(autouse=True)
def short_waits(monkeypatch):
    monkeypatch.setattr(sprinty_combat, "HAND_SETTLE_INTERVAL", 0.02)


async def test_a_cast_acts(move):
    hand = []
    Card("Storm Shark", _ATTACK, hand)
    combat = fake_combat(hand)

    await combat.try_execute_config(move('"Storm Shark"'))

    assert combat.turn_acted


async def test_an_enchant_that_fuses_acts(move):
    hand = []
    Card("Sharpened Blade", _ENCHANT, hand)
    Card("Storm Shark", _ATTACK, hand)
    combat = fake_combat(hand)

    await combat.try_execute_config(move('sharp @ spell("Storm Shark")'))

    assert combat.turn_acted


async def test_an_enchant_the_game_refuses_does_not_act(move, monkeypatch):
    monkeypatch.setattr(sprinty_combat, "ENCHANT_TIMEOUT", 0.2)
    hand = []
    Card("Sharpened Blade", _ENCHANT, hand)
    Card("Storm Shark", _ATTACK, hand, fuses=False)
    combat = fake_combat(hand)

    await combat.try_execute_config(move('sharp @ spell("Storm Shark")'))

    assert not combat.turn_acted


@pytest.mark.parametrize("dsl", ["pass", "discard @ spell(any<heal>)", '"Storm Shark"'])
async def test_a_move_with_nothing_to_act_on_does_not_act(move, dsl):
    combat = fake_combat([])

    await combat.try_execute_config(move(dsl))

    assert not combat.turn_acted


@pytest.mark.parametrize("leaves", [True, False])
async def test_a_discard_acts_only_once_the_card_leaves(leaves):
    hand = []
    card = Card("Storm Shark", _ATTACK, hand)
    combat = fake_combat(hand)

    async def discard(*, sleep_time=None):
        pass

    async def count():
        return 1

    async def changed(before):
        return leaves

    card.discard = discard
    combat.get_num_card_windows = count
    combat._wait_for_card_count_change = changed

    await combat.disc_on_target(card)

    assert combat.turn_acted is leaves


async def test_a_round_past_every_numbered_line_is_passed():
    provider = CombatConfigProvider.from_string("{1} pass", cast_time=0)
    combat = fake_combat([], provider=provider, round_number=4)

    await combat.handle_round()

    assert combat.passes == 1
    assert not combat.turn_acted


async def test_each_round_starts_with_nothing_done():
    combat = fake_combat([])
    combat.turn_acted = True

    async def play():
        pass

    combat._play_round = play
    await combat.handle_round()

    assert not combat.turn_acted
