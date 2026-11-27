"""`[sharp | "Aegis"]`: backups for one enchant, the first the hand holds.

A card takes one enchant, so the options in a bracket are alternatives, never steps: at
most one is fused. A second bracket is a second step (a fusion) and takes backups the same
way. Before this, `[sharp]` cast the card bare without a Sharpened Blade, and a line
below it could not help, since the first line had already cast.
"""

from __future__ import annotations

import pytest
from lark import Lark
from lark.exceptions import UnexpectedInput
from wizwalker.extensions.wizsprinter.combat_backends.combat_api import (
    EnchantChoice,
    NamedSpell,
    SpellType,
    TemplateSpell,
)
from wizwalker.extensions.wizsprinter.combat_backends.combat_config_parser import (
    TreeToConfig,
    get_sprinty_grammar,
)
from wizwalker.extensions.wizsprinter.sprinty_combat import enchant_is_optional
from wizwalker.memory import EffectTarget, SpellEffects

from .fakes import Card, Effect, Member, fake_combat

STORMBLADE = 1001
SHARPENED_BLADE = 2001
AEGIS = 2101

_BLADE = [Effect(SpellEffects.modify_outgoing_damage, EffectTarget.friendly_single, 35)]
_SHARPEN = [Effect(SpellEffects.modify_card_damage, EffectTarget.spell, 10)]
_AEGIS = [Effect(SpellEffects.protect_card_beneficial, EffectTarget.spell, 0)]

_LINE = 'any<blade>[sharp | "Aegis"] @ self'


@pytest.fixture(scope="module")
def parse():
    """One grammar per module: Lark costs ~77 ms to build."""
    parser = Lark(get_sprinty_grammar())

    def _parse(dsl: str):
        return TreeToConfig().transform(parser.parse(dsl)).infinite_rounds[0].priorities

    return _parse


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_backups_parse_as_one_optional_choice_in_order(parse):
    enchant = parse(_LINE)[0].move.enchant

    assert isinstance(enchant, EnchantChoice)
    assert enchant_is_optional(enchant) is True
    sharp, aegis = enchant.options
    assert (sharp.name, sharp.is_literal) == ("sharp", False)
    assert (aegis.name, aegis.is_literal) == ("Aegis", True)
    assert all(enchant_is_optional(option) for option in enchant.options)


def test_one_enchant_is_still_a_plain_spell(parse):
    assert isinstance(parse("any<blade>[sharp] @ self")[0].move.enchant, NamedSpell)


def test_a_template_can_be_an_option(parse):
    first, second = parse("any<damage>[any<mod_damage> | epic] @ enemy")[0].move.enchant.options

    assert isinstance(first, TemplateSpell) and SpellType.type_mod_damage in first.requirements
    assert first.optional is True
    assert second.name == "epic"


def test_the_pipe_inside_a_bracket_does_not_split_the_priorities(parse):
    priorities = parse(f"{_LINE} | any<trap>[potent | \"Indemnity\"] @ boss | pass")

    assert len(priorities) == 3
    assert isinstance(priorities[1].move.enchant, EnchantChoice)


def test_a_second_bracket_is_a_second_step_with_its_own_backups(parse):
    move = parse("any<damage>[potent | sharp][epic] @ enemy")[0].move

    assert isinstance(move.enchant, EnchantChoice)
    assert isinstance(move.second_enchant, NamedSpell) and move.second_enchant.name == "epic"


def test_an_unclosed_choice_is_an_error():
    with pytest.raises(UnexpectedInput):
        Lark(get_sprinty_grammar()).parse("any<blade>[sharp | aegis @ self")


# ---------------------------------------------------------------------------
# Which enchant a cast fuses
# ---------------------------------------------------------------------------


def _hand(*, sharp: bool = False, aegis: bool = False, sharp_castable: bool = True):
    hand = []
    blade = Card("Stormblade", _BLADE, hand, template_id=STORMBLADE)
    sharpened = (
        Card("Sharpened Blade", _SHARPEN, hand, template_id=SHARPENED_BLADE, castable=sharp_castable) if sharp else None
    )
    protect = Card("Aegis", _AEGIS, hand, template_id=AEGIS) if aegis else None
    return hand, blade, sharpened, protect


async def test_the_first_option_in_hand_is_fused_and_only_it(parse):
    hand, blade, sharpened, protect = _hand(sharp=True, aegis=True)
    me = Member("P1")
    combat = fake_combat(hand, team=[me])

    assert await combat.try_execute_config(parse(_LINE)[0]) is True

    assert sharpened.casts == [blade]
    assert protect.casts == []
    assert blade.enchant_id == SHARPENED_BLADE
    assert blade.casts == [me]


async def test_a_backup_is_fused_when_the_first_choice_is_not_in_hand(parse):
    hand, blade, _, protect = _hand(aegis=True)
    me = Member("P1")
    combat = fake_combat(hand, team=[me])

    assert await combat.try_execute_config(parse(_LINE)[0]) is True

    assert protect.casts == [blade]
    assert blade.enchant_id == AEGIS
    assert blade.casts == [me]


async def test_a_backup_is_fused_when_the_first_choice_cannot_be_cast(parse):
    hand, blade, sharpened, protect = _hand(sharp=True, aegis=True, sharp_castable=False)
    combat = fake_combat(hand, team=[Member("P1")])

    assert await combat.try_execute_config(parse(_LINE)[0]) is True

    assert sharpened.casts == []
    assert blade.enchant_id == AEGIS


async def test_with_no_option_in_hand_the_card_is_cast_bare(parse):
    hand, blade, _, _ = _hand()
    me = Member("P1")
    combat = fake_combat(hand, team=[me])

    assert await combat.try_execute_config(parse(_LINE)[0]) is True

    assert blade.enchant_id == 0
    assert blade.casts == [me]
