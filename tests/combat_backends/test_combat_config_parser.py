import pytest
from lark.exceptions import UnexpectedInput, VisitError

from wizwalker.extensions.wizsprinter.combat_backends.combat_config_parser import (
    AggregationMode,
    AllCondition,
    ClearSpec,
    ComparisonOp,
    Condition,
    DrawSpell,
    ExcludeNameSpec,
    GambitSpec,
    HangingType,
    NamedSpell,
    NotTypeSpec,
    SpellType,
    TargetType,
    TemplateSpell,
    TreeToConfig,
)
from wizwalker.extensions.wizsprinter.combat_backends.config_backend import _parser
from wizwalker.memory.memory_objects.enums import HangingDisposition


def parse(text: str):
    return TreeToConfig().transform(_parser().parse(text))


def only_move(text: str):
    """The one priority of a config with one line."""
    config = parse(text)
    (line,) = config.infinite_rounds
    (priority,) = line.priorities
    return priority


def test_a_bare_pass():
    move = only_move("pass").move
    assert isinstance(move.card, NamedSpell) and move.card.name == "pass"


def test_a_named_spell_at_an_enemy():
    priority = only_move("storm lord @ enemy")
    assert priority.move.card.name == "storm lord" and not priority.move.card.is_literal
    assert priority.target.target_type is TargetType.type_enemy


def test_a_quoted_name_is_matched_exactly():
    card = only_move('"Storm Lord"').move.card
    assert card.name == "Storm Lord" and card.is_literal


def test_a_template_with_an_enchant():
    move = only_move("any<damage & aoe>[sharp]").move
    assert isinstance(move.card, TemplateSpell)
    assert move.card.requirements == [SpellType.type_damage, SpellType.type_aoe]
    # every enchant the parser builds is optional: enchant it if the enchant is in hand
    assert move.enchant.name == "sharp" and move.enchant.optional


def test_two_enchants():
    move = only_move("tempest[potent][sharp]").move
    assert move.enchant.name == "potent" and move.second_enchant.name == "sharp"


def test_alternatives_are_priorities_in_order():
    (line,) = parse("storm lord | tempest | pass").infinite_rounds
    assert [p.move.card.name for p in line.priorities] == ["storm lord", "tempest", "pass"]


def test_numbered_rounds_and_the_rest():
    config = parse("{1} blade @ self\n{2} pass\nany<damage>")
    assert set(config.specific_rounds) == {1, 2}
    assert config.specific_rounds[1].priorities[0].target.target_type is TargetType.type_self
    assert len(config.infinite_rounds) == 1


def test_several_moves_in_one_priority():
    priority = only_move("feint @ boss & tempest")
    assert [m.card.name for m in priority.move] == ["feint", "tempest"]
    assert priority.target[0].target_type is TargetType.type_boss and priority.target[1] is None


@pytest.mark.parametrize("text, index", [("enemy(2)", 2), ("enemy(-1)", -1), ("enemy(last)", -1)])
def test_a_member_by_index(text, index):
    target = only_move(f"storm lord @ {text}").target
    assert target.target_type is TargetType.type_enemy and target.extra_data == index


def test_a_named_target():
    target = only_move('heal @ "Friend One"').target
    assert target.target_type is TargetType.type_named
    assert target.extra_data == "Friend One" and target.is_literal


def test_selected_targets():
    target = only_move("tempest @ select(enemy(1), boss)").target
    assert target.target_type is TargetType.type_select
    assert [t.target_type for t in target.extra_data] == [TargetType.type_enemy, TargetType.type_boss]
    assert target.extra_data[0].extra_data == 1


def test_an_enchant_aimed_at_a_spell():
    target = only_move("sharp @ spell(storm lord)").target
    assert target.target_type is TargetType.type_spell
    assert target.extra_data.name == "storm lord"


def test_draw_takes_a_count():
    assert only_move("draw").move.card.draw_amount == 1
    card = only_move("draw(3)").move.card
    assert isinstance(card, DrawSpell) and card.draw_amount == 3


def test_negations_inside_a_template():
    requirements = only_move("any<trap & !aoe & !feint>").move.card.requirements
    assert requirements[0] is SpellType.type_trap
    assert isinstance(requirements[1], NotTypeSpec) and requirements[1].type is SpellType.type_aoe
    assert isinstance(requirements[2], ExcludeNameSpec) and requirements[2].name == "feint"


def test_hanging_verbs():
    requirements = only_move("any<damage & gambit(harmful_charm, 2) & clear(ward)>").move.card.requirements
    gambit, clear = requirements[1], requirements[2]
    assert isinstance(gambit, GambitSpec) and gambit.hanging_type is HangingType.harmful_charms
    assert gambit.min_count == 2
    assert isinstance(clear, ClearSpec) and clear.hanging_type is HangingType.wards and clear.min_count == 1


def test_a_condition():
    condition = only_move("?(self.health < 50%) heal @ self").condition
    assert isinstance(condition, Condition)
    assert condition.target.target_type is TargetType.type_self
    assert (condition.attribute, condition.op, condition.value, condition.is_percent) == (
        "health", ComparisonOp.lt, 50.0, True
    )


def test_conditions_joined_by_and():
    condition = only_move("?(any(enemies).is_boss == 1 && deck.remaining >= 2) pass").condition
    assert isinstance(condition, AllCondition)
    assert condition.clauses[0].target.aggregation is AggregationMode.agg_any
    assert condition.clauses[1].target.target_type is TargetType.type_deck


def test_a_hanging_count_condition():
    condition = only_move("?(boss.beneficial_charm >= 1) pass").condition
    assert condition.attribute == "beneficial_charm"


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("?(self.helth < 50) pass", "Did you mean 'health'"),
        ("?(self.level < 50%) pass", "takes no %"),
        ("?(deck.health > 1) pass", "deck has one attribute"),
        ("?(self.remaining > 1) pass", "read on deck only"),
        ("any<damage & gambit(blades)>", "Unknown hanging type"),
        ("any<damage & gambit(charm, 0)>", "count must be >= 1"),
        ("any<!req_met>", "Only a spell type can be negated"),
    ],
)
def test_a_condition_or_filter_that_can_never_hold_is_refused(text, fragment):
    with pytest.raises(VisitError) as caught:
        parse(text)
    assert isinstance(caught.value.orig_exc, ValueError)
    assert fragment in str(caught.value.orig_exc)


def test_malformed_text_is_a_parse_error():
    with pytest.raises(UnexpectedInput):
        parse("storm lord @")


def test_hanging_type_names_carry_their_side():
    from wizwalker.extensions.wizsprinter.combat_backends.combat_api import hanging_type_info

    assert hanging_type_info(HangingType.harmful_over_time) == ("over_time", HangingDisposition.harmful)
    assert hanging_type_info(HangingType.auras) == ("auras", None)
