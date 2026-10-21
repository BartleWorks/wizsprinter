import pytest

from wizwalker.extensions.wizsprinter.combat_backends.combat_config_parser import (
    GambitSpec,
    HangingType,
    SpellType,
    TemplateSpell,
)
from wizwalker.extensions.wizsprinter.combat_backends.spell_ranking import (
    AllOf,
    Amount,
    BestOf,
    CardFacts,
    CardSource,
    OneOf,
    expected_value,
    rank_facts,
    ranker_for,
)


def ranked(template_types, facts):
    ranker = ranker_for(TemplateSpell(list(template_types)))
    return rank_facts(facts, ranker)


def test_all_of_adds_up():
    assert expected_value(AllOf((Amount(300), Amount(150)))) == 450


def test_one_of_is_the_mean_of_its_branches():
    # Humongofrog's five rolls are one hit, not five
    rolls = OneOf(tuple(Amount(v) for v in (575, 585, 595, 605, 615)))
    assert expected_value(rolls) == 595


def test_best_of_keeps_the_largest_magnitude_with_its_sign():
    assert expected_value(BestOf((Amount(-50), Amount(-70)))) == -70
    assert expected_value(BestOf((Amount(45), Amount(30)))) == 45


def test_empty_nodes_score_zero():
    assert expected_value(AllOf()) == expected_value(BestOf()) == expected_value(OneOf()) == 0


def test_a_score_node_is_required():
    with pytest.raises(TypeError):
        expected_value(42)


def test_damage_ranks_the_biggest_hit_first():
    facts = [CardFacts(score=Amount(305)), CardFacts(score=Amount(755)), CardFacts(score=Amount(500))]
    assert ranked([SpellType.type_aoe], facts) == [1, 2, 0]


def test_per_pip_damage_ranks_after_fixed_damage():
    facts = [CardFacts(score=Amount(800), is_per_pip=True), CardFacts(score=Amount(300))]
    assert ranked([SpellType.type_damage], facts) == [1, 0]


def test_a_pending_enchant_counts_toward_damage():
    facts = [CardFacts(score=Amount(400)), CardFacts(score=Amount(350), enchant_bonus=100)]
    assert ranked([SpellType.type_damage], facts) == [1, 0]


@pytest.mark.parametrize(
    "first, second",
    [
        (CardFacts(score=Amount(500), pip_cost=4), CardFacts(score=Amount(500), pip_cost=5)),
        (CardFacts(score=Amount(500), source=CardSource.item), CardFacts(score=Amount(500), source=CardSource.deck)),
        (CardFacts(score=Amount(500), source=CardSource.deck), CardFacts(score=Amount(500), source=CardSource.treasure)),
        (CardFacts(score=Amount(500), is_enchanted=True), CardFacts(score=Amount(500))),
    ],
    ids=["fewer pips", "item before deck", "deck before treasure", "enchanted first"],
)
def test_ties_break_on_cost_then_source_then_enchantment(first, second):
    assert ranked([SpellType.type_damage], [second, first]) == [1, 0]


def test_blades_rank_by_size():
    facts = [CardFacts(score=Amount(25)), CardFacts(score=Amount(45))]
    assert ranked([SpellType.type_blade], facts) == [1, 0]


def test_a_shield_ranks_by_magnitude():
    # A -70 Tower Shield is the stronger of two shields
    facts = [CardFacts(score=Amount(-30)), CardFacts(score=Amount(-70))]
    assert ranked([SpellType.type_ward], facts) == [1, 0]


def test_incoming_damage_puts_my_shield_before_their_trap():
    facts = [CardFacts(score=Amount(70)), CardFacts(score=Amount(-70))]
    assert ranked([SpellType.type_inc_damage], facts) == [1, 0]


def test_flat_buffs_rank_after_percentages():
    facts = [CardFacts(score=Amount(225), is_flat=True), CardFacts(score=Amount(35))]
    assert ranked([SpellType.type_blade], facts) == [1, 0]


def test_the_narrower_category_decides_the_ranker():
    aoe = ranker_for(TemplateSpell([SpellType.type_damage, SpellType.type_aoe]))
    assert aoe.aoe_only and aoe.score_type is SpellType.type_damage


def test_an_unranked_category_keeps_the_callers_order():
    assert ranker_for(TemplateSpell([SpellType.type_dispel])) is None
    assert ranker_for(TemplateSpell([GambitSpec(HangingType.charms)])) is None
    assert ranker_for("not a template") is None


def test_ties_hold_their_order():
    facts = [CardFacts(score=Amount(100)) for _ in range(4)]
    assert ranked([SpellType.type_damage], facts) == [0, 1, 2, 3]
