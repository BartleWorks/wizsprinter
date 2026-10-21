"""The small pure decisions SprintyCombat makes along the way."""

from types import SimpleNamespace

import pytest

from wizwalker.extensions.wizsprinter.combat_backends.combat_config_parser import (
    ClearSpec,
    ComparisonOp,
    DrawSpell,
    EchoSpec,
    GambitSpec,
    HangingType,
    Move,
    MoveConfig,
    NamedSpell,
    TargetData,
    TargetType,
    TemplateSpell,
)
from wizwalker.extensions.wizsprinter.sprinty_combat import (
    SprintyCombat,
    enchant_is_optional,
    is_enchant_only,
    name_matches,
    parse_card_count,
)
from wizwalker.memory.memory_objects.enums import HangingDisposition


@pytest.mark.parametrize(
    "text, counts",
    [
        ("<center>Cards</center>\n<center>13 of 20</center>", (13, 20)),
        ("<center>Cartes</center>\n<center>13 sur 20</center>", (13, 20)),
        ("<center>Cards</center>\n<center>0 of 7</center>\n", (0, 7)),
    ],
)
def test_reads_the_card_count_in_any_language(text, counts):
    assert parse_card_count(text) == counts


@pytest.mark.parametrize("text", ["", "\n\n", "<center>Cards</center>"])
def test_an_unreadable_card_count(text):
    assert parse_card_count(text) is None


def spell_target(name):
    return TargetData(TargetType.type_spell, NamedSpell(name))


def test_an_enchant_aimed_at_a_spell_is_enchant_only():
    assert is_enchant_only(MoveConfig(Move(NamedSpell("sharp")), spell_target("tempest")))


@pytest.mark.parametrize(
    "config",
    [
        MoveConfig(Move(NamedSpell("tempest")), TargetData(TargetType.type_enemy)),
        MoveConfig(Move(NamedSpell("tempest")), None),
        MoveConfig(Move(NamedSpell("discard")), spell_target("tempest")),
        MoveConfig(Move(DrawSpell()), spell_target("tempest")),
        MoveConfig([Move(NamedSpell("sharp")), Move(NamedSpell("tempest"))],
                   [spell_target("tempest"), TargetData(TargetType.type_enemy)]),
    ],
    ids=["a cast", "no target", "a discard", "a draw", "an enchant then a cast"],
)
def test_anything_that_ends_the_turn_is_not_enchant_only(config):
    assert not is_enchant_only(config)


def test_names_match_loosely_unless_quoted():
    assert name_matches("storm", "Storm Lord", is_literal=False)
    assert not name_matches("storm", "Storm Lord", is_literal=True)
    assert name_matches("Storm Lord", "Storm Lord", is_literal=True)


def test_an_enchant_built_in_code_is_mandatory_unless_it_says_otherwise():
    assert not enchant_is_optional(SimpleNamespace())
    assert enchant_is_optional(NamedSpell("sharp", optional=True))
    assert enchant_is_optional(TemplateSpell([], optional=True))


@pytest.mark.parametrize(
    "members, n, expected",
    [([1, 2, 3], 0, 1), ([1, 2, 3], 2, 3), ([1, 2, 3], 3, None), ([1, 2, 3], -1, 3), ([1, 2, 3], -4, None), ([], 0, None)],
)
def test_a_member_by_index(members, n, expected):
    assert SprintyCombat._at_index(members, n) == expected


@pytest.mark.parametrize(
    "spec, sides",
    [
        (GambitSpec(HangingType.charms), [("caster", HangingDisposition.beneficial), ("target", HangingDisposition.harmful)]),
        (GambitSpec(HangingType.harmful_charms), [("target", HangingDisposition.harmful)]),
        (ClearSpec(HangingType.wards), [("caster", HangingDisposition.harmful), ("target", HangingDisposition.beneficial)]),
        (ClearSpec(HangingType.beneficial_wards), [("target", HangingDisposition.beneficial)]),
        (EchoSpec(HangingType.over_time), [("target", HangingDisposition.beneficial), ("target", HangingDisposition.harmful)]),
    ],
)
def test_which_side_a_hanging_verb_reads(spec, sides):
    assert SprintyCombat._resolve_verb_sides(spec) == sides


@pytest.mark.parametrize(
    "actual, op, value, expected",
    [(1, ComparisonOp.lt, 2, True), (2, ComparisonOp.le, 2, True), (3, ComparisonOp.gt, 2, True),
     (2, ComparisonOp.ge, 3, False), (2, ComparisonOp.eq, 2, True), (2, ComparisonOp.ne, 2, False)],
)
def test_comparisons(actual, op, value, expected):
    assert SprintyCombat._compare(None, actual, op, value) is expected
