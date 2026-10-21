"""How long an enchant's fuse is waited for, and when the click is repeated."""

import asyncio
from types import SimpleNamespace

from wizwalker.extensions.wizsprinter import sprinty_combat
from wizwalker.memory import EffectTarget, SpellEffects

from .fakes import Card, Effect, fake_combat

CAST_TIME = 0.3  # so a click has 0.6 s to show before it is repeated


def sharpen():
    return [Effect(SpellEffects.modify_card_damage, EffectTarget.spell, 100)]


def strike():
    return [Effect(SpellEffects.damage, EffectTarget.enemy_single, 500)]


class LateCard(Card):
    """An enchant whose fuse shows in the hand a while after its click."""

    delay = 0.15

    async def cast(self, target, *, sleep_time=None, debug_paint=False):
        self.casts.append(target)
        hand = self._hand

        def land():
            if self in hand:
                hand.remove(self)
                target.fuse(self)

        asyncio.get_running_loop().call_later(self.delay, land)


def setup(enchant_type=Card, *, fuses=True):
    hand = []
    enchant = enchant_type("Sharpen", sharpen(), hand, template_id=2)
    target = Card("Strike", strike(), hand, template_id=1, fuses=fuses)
    combat = fake_combat(hand, provider=SimpleNamespace(cast_time=CAST_TIME))
    return combat, enchant, target


async def timed(coro):
    loop = asyncio.get_running_loop()
    started = loop.time()
    result = await coro
    return result, loop.time() - started


async def test_a_fuse_already_in_ends_the_wait_at_once():
    # A fixed sleep of the whole click window came first, fuse or no fuse
    combat, enchant, target = setup()
    fused, elapsed = await timed(combat._fuse_enchant(enchant, target, recast=True))
    assert fused and elapsed < CAST_TIME
    assert len(enchant.casts) == 1


async def test_a_late_fuse_is_seen_when_it_lands():
    combat, enchant, target = setup(LateCard)
    fused, elapsed = await timed(combat._fuse_enchant(enchant, target, recast=True))
    assert fused
    assert LateCard.delay <= elapsed < 2 * CAST_TIME
    assert len(enchant.casts) == 1


async def test_a_refused_enchant_is_clicked_again_until_it_gives_up(monkeypatch):
    monkeypatch.setattr(sprinty_combat, "ENCHANT_TIMEOUT", 1.0)
    combat, enchant, target = setup(fuses=False)
    fused, elapsed = await timed(combat._fuse_enchant(enchant, target, recast=True))
    assert not fused
    assert 1.0 <= elapsed < 2.0
    # one click, then one more each 0.6 s window until the second runs out
    assert len(enchant.casts) == 2


async def test_without_recasting_the_click_is_made_once(monkeypatch):
    monkeypatch.setattr(sprinty_combat, "ENCHANT_TIMEOUT", 0.3)
    combat, enchant, target = setup(fuses=False)
    assert not await combat._fuse_enchant(enchant, target, recast=False)
    assert len(enchant.casts) == 1
