"""Casts the game drops, and casts aimed at combatants it has rebuilt since they were read.

Seen in a four-player Heretical Academy run: a fused card cast once and never checked,
whose click the game had dropped, so the card sat in hand and the round counted a fizzle;
and a Balaur head read at the start of a round, rebuilt by the game while an enchant
fused, so the cast picked its card up and clicked a window that was no longer there. Each
fight that lost a cast ran past the strategy's last line, and the players with no line
sat out until the game's idle popup made them flee.
"""

from __future__ import annotations

import asyncio
import logging

import pytest
from lark import Lark
from wizwalker.memory import EffectTarget, SpellEffects

from wizwalker.extensions.wizsprinter import sprinty_combat
from wizwalker.extensions.wizsprinter.combat_backends.combat_config_parser import (
    TreeToConfig,
    get_sprinty_grammar,
)

from .fakes import Card, Effect, Member, Slot, fake_combat

_STRIKE = [Effect(SpellEffects.damage, EffectTarget.enemy_single, 500)]
_SHARPEN = [Effect(SpellEffects.modify_card_damage, EffectTarget.spell, 100)]


@pytest.fixture(scope="module")
def move():
    """The first priority of a one-line DSL. One grammar per module: Lark costs ~77 ms to build."""
    parser = Lark(get_sprinty_grammar())

    def _parse(dsl: str):
        return TreeToConfig().transform(parser.parse(dsl)).infinite_rounds[0].priorities[0]

    return _parse


@pytest.fixture(autouse=True)
def short_waits(monkeypatch):
    monkeypatch.setattr(sprinty_combat, "CAST_LAND_TIMEOUT", 0.2)
    monkeypatch.setattr(sprinty_combat, "COMBATANTS_SETTLE_TIMEOUT", 0.3)
    monkeypatch.setattr(sprinty_combat, "COMBATANTS_SETTLE_INTERVAL", 0.05)
    monkeypatch.setattr(sprinty_combat, "HAND_SETTLE_INTERVAL", 0.02)


class Dropping(Card):
    """A card the game ignores the first `drops` casts of at a combatant."""

    def __init__(self, *args, drops: int = 0, **kwargs):
        super().__init__(*args, **kwargs)
        self.drops = drops
        self.attempts = []

    async def cast(self, target, *, sleep_time=None, debug_paint=False):
        if not isinstance(target, (Card, Slot)):
            self.attempts.append(target)
            if self.drops:
                self.drops -= 1
                return
        await super().cast(target, sleep_time=sleep_time, debug_paint=debug_paint)


class Rebuilt(Member):
    """A combatant whose window the game can rebuild: once `gone`, nothing on it reads."""

    gone = False

    async def get_participant(self):
        if self.gone:
            raise ValueError("Unable to read memory")
        return self.participant


def fight(*, drops: int = 0, enemies=None):
    hand = []
    strike = Dropping("Strike", _STRIKE, hand, template_id=1, drops=drops)
    sharpen = Card("Sharpen", _SHARPEN, hand, template_id=2)
    enemies = enemies or [Member("Head", boss=True)]
    combat = fake_combat(hand, enemies=enemies)
    return combat, strike, sharpen, enemies


async def timed(coro):
    loop = asyncio.get_running_loop()
    started = loop.time()
    result = await coro
    return result, loop.time() - started


# ---------------------------------------------------------------------------
# A fused card's cast is seen to land
# ---------------------------------------------------------------------------


async def test_a_fused_card_that_lands_is_cast_once(move):
    combat, strike, _, (head,) = fight()

    assert await combat.try_execute_config(move("strike[sharpen] @ enemy(0)")) is True

    assert strike.attempts == [head]


async def test_a_fused_card_the_game_dropped_is_cast_again(move):
    combat, strike, _, (head,) = fight(drops=1)

    assert await combat.try_execute_config(move("strike[sharpen] @ enemy(0)")) is True

    assert strike.attempts == [head, head]
    assert strike not in strike._hand  # it landed the second time


async def test_a_fused_card_that_never_lands_is_given_up_on(move, caplog):
    combat, strike, _, _ = fight(drops=99)

    with caplog.at_level(logging.WARNING):
        assert await combat.try_execute_config(move("strike[sharpen] @ enemy(0)")) is True

    assert len(strike.attempts) == sprinty_combat.CAST_ATTEMPTS
    assert "never left the hand" in caplog.text


async def test_a_cast_that_hides_the_hand_has_landed():
    """The game may hide the hand's window rather than its cards, which keep their own flags."""
    combat, *_ = fight()

    class _Hand:
        visible = True

        async def is_visible(self):
            return self.visible

    hand = _Hand()

    async def get_hand_window():
        return hand

    combat._get_hand_window = get_hand_window
    assert not await combat._cast_landed(len(await combat.get_cards()))
    hand.visible = False
    assert await combat._cast_landed(len(await combat.get_cards()))


async def test_a_card_the_game_dropped_is_found_again_by_its_fuse(move):
    """A dropped cast leaves the hand as it was; the card is still the one carrying the enchant."""
    combat, strike, sharpen, _ = fight(drops=1)
    Card("Strike", _STRIKE, strike._hand, template_id=1)  # a bare copy, not to be cast

    await combat.try_execute_config(move("strike[sharpen] @ enemy(0)"))

    assert len(strike.attempts) == 2 and strike.enchant_id == sharpen.template_id_


# ---------------------------------------------------------------------------
# The target is read again before the cast
# ---------------------------------------------------------------------------


async def test_a_target_rebuilt_during_the_fuse_is_read_again(move):
    old, new = Rebuilt("Head", boss=True), Rebuilt("Head", boss=True)
    combat, strike, sharpen, _ = fight(enemies=[old, new])
    fighting = [m for m in await combat.get_members() if m is not new]

    async def get_members():
        return list(fighting)

    combat.get_members = get_members
    fuse = sharpen.cast

    async def rebuild_then_fuse(target, **kwargs):
        old.gone = True
        fighting[fighting.index(old)] = new
        await fuse(target, **kwargs)

    sharpen.cast = rebuild_then_fuse

    assert await combat.try_execute_config(move("strike[sharpen] @ enemy(0)")) is True

    assert strike.attempts == [new]


async def test_a_target_that_never_reads_whole_is_cast_at_as_it_was(move):
    head = Rebuilt("Head", boss=True)
    combat, strike, sharpen, _ = fight(enemies=[head])
    fuse = sharpen.cast

    async def lose_the_window_then_fuse(target, **kwargs):
        head.gone = True
        await fuse(target, **kwargs)

    sharpen.cast = lose_the_window_then_fuse

    _, elapsed = await timed(combat.try_execute_config(move("strike[sharpen] @ enemy(0)")))

    assert strike.attempts == [head]
    assert elapsed >= sprinty_combat.COMBATANTS_SETTLE_TIMEOUT


# ---------------------------------------------------------------------------
# A miss read while the fight has nobody in it is read again
# ---------------------------------------------------------------------------


async def test_a_fight_read_with_no_enemy_is_read_again(move):
    combat, strike, _, (head,) = fight()
    everyone = await combat.get_members()
    loop = asyncio.get_running_loop()
    rebuilt_at = loop.time() + 0.1

    async def get_members():
        # The enemies' windows are not there yet when the round starts
        return everyone if loop.time() >= rebuilt_at else [m for m in everyone if m is not head]

    combat.get_members = get_members

    assert await combat.try_execute_config(move("strike @ enemy(0)")) is True

    assert strike.attempts == [head]


async def test_a_miss_with_enemies_to_hit_is_not_waited_on(move):
    """A fight with no boss misses `boss` every time; only a fight read as empty is read again."""
    combat, strike, _, _ = fight(enemies=[Member("Minion")])

    result, elapsed = await timed(combat.try_execute_config(move("strike @ boss")))

    assert result is False and strike.attempts == []
    assert elapsed < sprinty_combat.COMBATANTS_SETTLE_INTERVAL


# ---------------------------------------------------------------------------
# The hand is let settle after a fuse
# ---------------------------------------------------------------------------


async def test_the_hand_is_waited_on_until_two_reads_agree(monkeypatch):
    combat, strike, _, _ = fight()
    loop = asyncio.get_running_loop()
    settled_at = loop.time() + 0.1

    async def get_cards():
        if loop.time() < settled_at:
            strike.fuse(strike)  # laid out again: a new window each read
        return [Slot(c) for c in strike._hand]

    combat.get_cards = get_cards

    _, elapsed = await timed(combat._wait_for_hand_to_settle())

    assert 0.1 <= elapsed < sprinty_combat.HAND_SETTLE_TIMEOUT


async def test_a_hand_that_never_settles_is_waited_on_no_longer_than_the_limit(monkeypatch):
    monkeypatch.setattr(sprinty_combat, "HAND_SETTLE_TIMEOUT", 0.2)
    combat, strike, _, _ = fight()

    async def get_cards():
        strike.fuse(strike)
        return [Slot(c) for c in strike._hand]

    combat.get_cards = get_cards

    _, elapsed = await timed(combat._wait_for_hand_to_settle())

    assert 0.2 <= elapsed < 0.4
