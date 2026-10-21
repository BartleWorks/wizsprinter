"""Each effect is read from memory once however many requirements ask about it.

A read here is a ReadProcessMemory call per field in game, and matching a hand
against a strategy's templates asks the same few fields over and over.
"""

from collections import Counter

import pytest

from wizwalker.extensions.wizsprinter import sprinty_combat
from wizwalker.extensions.wizsprinter.combat_backends.combat_config_parser import SpellType, TemplateSpell
from wizwalker.extensions.wizsprinter.sprinty_combat import (
    EffectFacts,
    EffectReads,
    ReqSatisfaction,
    does_card_contain_reqs,
    facts_satisfy,
)
from wizwalker.memory import EffectTarget, SpellEffects

from .fakes import Card, Effect, Hanging, Member, fake_combat


class CountedEffect(Effect):
    """An Effect that counts each field read."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reads = Counter()

    async def effect_type(self):
        self.reads["type"] += 1
        return await super().effect_type()

    async def effect_target(self):
        self.reads["target"] += 1
        return await super().effect_target()

    async def effect_param(self):
        self.reads["param"] += 1
        return await super().effect_param()

    async def num_rounds(self):
        self.reads["rounds"] += 1
        return await super().num_rounds()


class CountedCard(Card):
    names_read = 0

    async def name(self):
        CountedCard.names_read += 1
        return await super().name()


def damage(param=300):
    return CountedEffect(SpellEffects.damage, EffectTarget.enemy_team, param)


def blade(param=35):
    return CountedEffect(SpellEffects.modify_outgoing_damage, EffectTarget.friendly_team, param)


def read_at_most_once(*effects):
    return all(count <= 1 for effect in effects for count in effect.reads.values())


async def test_matching_several_requirements_reads_each_effect_once():
    effects = [damage(), blade()]
    card = Card("Mass Storm", effects)
    template = TemplateSpell([SpellType.type_damage, SpellType.type_aoe, SpellType.type_blade])
    assert await does_card_contain_reqs(card, template)
    assert read_at_most_once(*effects)


async def test_a_negation_reads_nothing_twice():
    effects = [damage(), blade()]
    card = Card("Mass Storm", effects)
    template = TemplateSpell([SpellType.type_damage, sprinty_combat.NotTypeSpec(SpellType.type_trap)])
    await does_card_contain_reqs(card, template)
    assert read_at_most_once(*effects)


async def test_matching_reads_no_further_than_the_first_match():
    first, second = damage(), blade()
    assert await does_card_contain_reqs(Card("Hit", [first, second]), TemplateSpell([SpellType.type_damage]))
    assert second.reads == Counter()


async def test_the_card_name_is_read_only_when_tracing(monkeypatch):
    # The trace read every damage card's name, tracing or not
    monkeypatch.setattr(sprinty_combat, "_DEBUG", False)
    CountedCard.names_read = 0
    await does_card_contain_reqs(CountedCard("Hit", [damage()]), TemplateSpell([SpellType.type_damage]))
    assert CountedCard.names_read == 0


async def test_stacking_reads_each_effect_once():
    effects = [blade(), CountedEffect(SpellEffects.modify_incoming_damage, EffectTarget.enemy_team, 30)]
    hand = []
    card = Card("Blade and Trap", effects, hand, template_id=7)
    combat = fake_combat(hand, team=[Member("P1", Hanging(7))], enemies=[Member("E1")])
    assert await combat.would_stack(card, None)
    assert read_at_most_once(*effects)


async def test_effect_reads_answer_by_index_and_in_order():
    effects = [damage(100), blade(20)]
    reads = EffectReads(effects)
    assert (await reads.at(1)).param == 20
    assert [f.param async for f in reads] == [100, 20]
    assert read_at_most_once(*effects)
    assert len(reads) == 2


# --- the classifier, on facts alone ----------------------------------------------


def facts(effect_type, target, param=0, rounds=0):
    return EffectFacts(effect_type, target, param, rounds)


@pytest.mark.parametrize(
    "effect, kind",
    [
        (facts(SpellEffects.modify_outgoing_damage, EffectTarget.friendly_single, 35), SpellType.type_blade),
        (facts(SpellEffects.modify_outgoing_damage, EffectTarget.enemy_single, -25), SpellType.type_charm),
        (facts(SpellEffects.modify_incoming_damage, EffectTarget.friendly_team, -50), SpellType.type_ward),
        (facts(SpellEffects.modify_incoming_damage, EffectTarget.enemy_team, 30), SpellType.type_trap),
        (facts(SpellEffects.modify_outgoing_damage, EffectTarget.self, 20, rounds=4), SpellType.type_aura),
        (facts(SpellEffects.modify_incoming_damage, EffectTarget.enemy_single, 20, rounds=4), SpellType.type_harmful_aura),
        (facts(SpellEffects.damage, EffectTarget.enemy_single, 500), SpellType.type_damage),
        (facts(SpellEffects.heal, EffectTarget.self, 400), SpellType.type_heal_self),
        (facts(SpellEffects.modify_card_damage, EffectTarget.spell, 100), SpellType.type_mod_damage),
        (facts(SpellEffects.damage, EffectTarget.enemy_team, 300), SpellType.type_aoe),
    ],
)
def test_classifies_an_effect(effect, kind):
    assert facts_satisfy(effect, kind) is ReqSatisfaction.true


@pytest.mark.parametrize(
    "effect, kind",
    [
        # a charm on the enemy is no blade, and a blade with rounds is an aura
        (facts(SpellEffects.modify_outgoing_damage, EffectTarget.enemy_single, -25), SpellType.type_blade),
        (facts(SpellEffects.modify_outgoing_damage, EffectTarget.self, 20, rounds=4), SpellType.type_blade),
        (facts(SpellEffects.heal, EffectTarget.enemy_single, 400), SpellType.type_heal),
        (facts(SpellEffects.damage, EffectTarget.enemy_single, 500), SpellType.type_aoe),
    ],
)
def test_does_not_misclassify_an_effect(effect, kind):
    assert facts_satisfy(effect, kind) is ReqSatisfaction.false
