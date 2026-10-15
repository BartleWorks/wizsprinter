import difflib
from enum import Enum, auto
from typing import *

from wizwalker.memory.memory_objects.conditionals import (
    charm_effect_types, ward_effect_types, over_time_effect_types, aura_effect_types,
    ReqHangingCharm, ReqHangingWard, ReqHangingOverTime, ReqHangingAura,
)
from wizwalker.memory.memory_objects.enums import HangingDisposition, HangingEffectType, SpellEffects

class TargetType(Enum):
    type_self = auto()
    type_boss = auto()
    type_enemy = auto()
    type_ally = auto()
    type_aoe = auto()
    type_named = auto()
    type_spell = auto()
    type_select = auto()
    type_enemies = auto()
    type_allies = auto()
    # Condition-only: the wizard's own deck, read through `deck.<attr>`.
    type_deck = auto()


class SpellType(Enum):
    type_damage = auto()
    type_inc_damage = auto()
    type_out_damage = auto()
    type_aoe = auto()
    type_heal = auto()
    type_inc_heal = auto()
    type_out_heal = auto()
    type_heal_self = auto()
    type_heal_other = auto()
    type_blade = auto()
    type_charm = auto()
    type_ward = auto()
    type_trap = auto()
    type_enchant = auto()
    #Slack added types
    type_aura = auto()
    type_global = auto()
    type_polymorph = auto()
    type_shadow = auto()
    type_shadow_creature = auto()
    type_pierce = auto()
    type_prism = auto()
    type_dispel = auto()
    #Fix for enchants
    type_mod_damage = auto()
    type_mod_heal = auto()
    type_mod_pierce = auto()
    #Card requirement filtering
    type_req_met = auto()
    # Whether the effect the card leaves would add to its target's, rather than
    # duplicate one already hanging there. Checked after selection, like req_met.
    type_stacks = auto()
    # An aura cast at an enemy: an effect lasting rounds whose target is an enemy.
    # `aura` stays an aura on the caster.
    type_harmful_aura = auto()
    # Whether the aura the card leaves is better for the caster's side than the
    # aura its landing participant already holds. Checked after selection.
    type_stronger = auto()


#: Requirements checked after a card is selected rather than against each of its
#: effects, so a negation of one has nothing to test and a card's effects never
#: count toward them.
POST_FILTER_TYPES = (SpellType.type_req_met, SpellType.type_stacks, SpellType.type_stronger)


class ComparisonOp(Enum):
    lt = "<"
    le = "<="
    gt = ">"
    ge = ">="
    eq = "=="
    ne = "!="


class AggregationMode(Enum):
    agg_any = "any"
    agg_all = "all"
    agg_avg = "avg"


class ConditionTarget:
    def __init__(self, target_type: TargetType, index: int = None, aggregation: AggregationMode = None):
        self.target_type = target_type
        self.index = index
        self.aggregation = aggregation

    def __repr__(self) -> str:
        agg = f", aggregation={self.aggregation}" if self.aggregation else ""
        return f"ConditionTarget(target_type={self.target_type}, index={self.index}{agg})"


class Condition:
    def __init__(self, target: ConditionTarget, attribute: str, op: ComparisonOp, value: float, is_percent: bool = False):
        self.target = target
        self.attribute = attribute
        self.op = op
        self.value = value
        self.is_percent = is_percent

    def __repr__(self) -> str:
        pct = "%" if self.is_percent else ""
        return f"Condition({self.target}.{self.attribute} {self.op.value} {self.value}{pct})"


class AllCondition:
    """Composite predicate that holds iff every clause holds (logical AND).
    Produced by the parser when a `?(...)` block contains two or more clauses
    joined by `&&`. A single-clause `?(...)` still returns a plain Condition,
    so existing strategies are unaffected."""
    def __init__(self, clauses: List[Condition]):
        self.clauses = clauses

    def __repr__(self) -> str:
        return f"AllCondition([{', '.join(repr(c) for c in self.clauses)}])"


class Spell:
    pass


class DrawSpell(Spell):
    def __init__(self, draw_amount: int = 1):
        self.draw_amount = draw_amount

    def __repr__(self) -> str:
        return f"DrawSpell(draw_amount={self.draw_amount})"

class NamedSpell(Spell):
    def __init__(self, name: str, is_literal: bool = False, optional: bool = False) -> None:
        self.name = name
        self.is_literal = is_literal
        # Only meaningful in enchant position, where it means the same thing it
        # does on TemplateSpell: enchant the card if the enchant is in hand,
        # cast it bare if it is not. See `TreeToConfig.spell`.
        self.optional = optional

    def __repr__(self) -> str:
        return f"NamedSpell(name=\"{self.name}\", is_literal={self.is_literal}, optional={self.optional})"


# --- Hanging-effect category registry -------------------------------------
# Single source of truth for which SpellEffects belong to which broad category,
# which ConditionalSpellEffect requirement class checks for that category, and
# which HangingEffectType the game uses on HangingConversionSpellEffect.
#
# To add a new category (e.g. "auras"):
#   1. Define / import the SpellEffects list (e.g. aura_effect_types).
#   2. Add one row here with whatever pieces wizwalker exposes. Pieces that
#      don't exist yet (no req_class, no HET value) get None — the matcher
#      degrades to whatever paths still work for that category.
# Tuple = (effect_types_list, req_class_or_None, hanging_effect_type_or_None,
#          [parser_aliases], swap_effect_type_or_None)
HANGING_CATEGORIES = {
    "charms":    (charm_effect_types,     ReqHangingCharm,     HangingEffectType.charm,     ["charm"], SpellEffects.swap_charm),
    "wards":     (ward_effect_types,      ReqHangingWard,      HangingEffectType.ward,      ["ward"], SpellEffects.swap_ward),
    "over_time": (over_time_effect_types, ReqHangingOverTime, HangingEffectType.over_time, ["ot"],   SpellEffects.swap_over_time),
    "auras":     (aura_effect_types,      ReqHangingAura,      None,                        ["aura"], None),
}


def _build_hanging_type():
    members = {}
    for canonical in HANGING_CATEGORIES:
        members[canonical] = canonical
        members[f"beneficial_{canonical}"] = f"beneficial_{canonical}"
        members[f"harmful_{canonical}"] = f"harmful_{canonical}"
    return Enum("HangingType", members)


# Dynamically constructed so adding a category to HANGING_CATEGORIES auto-grows
# the enum (and everything downstream that reads from the registry).
# Members for the 3 stock categories: charms, beneficial_charms, harmful_charms,
# wards, beneficial_wards, harmful_wards, over_time, beneficial_over_time,
# harmful_over_time. Use disposition-prefixed names to combine with the verb
# (gambit/clear) and pin down a single side.
HangingType = _build_hanging_type()


def hanging_type_info(ht: "HangingType") -> Tuple[str, Optional[HangingDisposition]]:
    """Decompose a HangingType into (canonical_category, disposition_or_None)."""
    name = ht.value
    if name.startswith("beneficial_"):
        return name[len("beneficial_"):], HangingDisposition.beneficial
    if name.startswith("harmful_"):
        return name[len("harmful_"):], HangingDisposition.harmful
    return name, None


def hanging_type_aliases() -> Dict[str, "HangingType"]:
    """Return {parser_keyword: HangingType_member} including all category aliases
    (charm/ward/ot) and disposition prefixes (beneficial_/harmful_)."""
    out: Dict[str, HangingType] = {}
    for canonical, (_, _, _, aliases, _) in HANGING_CATEGORIES.items():
        names = [canonical] + list(aliases)
        for n in names:
            out[n] = HangingType[canonical]
            out[f"beneficial_{n}"] = HangingType[f"beneficial_{canonical}"]
            out[f"harmful_{n}"] = HangingType[f"harmful_{canonical}"]
    return out


# What `?(member.<attr> ...)` reads by calling the CombatMember method of that name,
# mapped to the method a `%` divides by, or None for one that takes no `%`.
# CONDITIONS.md documents exactly these; the parser refuses any other name.
MEMBER_ATTRIBUTES: Dict[str, Optional[str]] = {
    "health": "max_health",
    "max_health": None,
    "mana": "max_mana",
    "max_mana": None,
    "normal_pips": None,
    "power_pips": None,
    "shadow_pips": None,
    "level": None,
    "is_boss": None,
    "is_dead": None,
    "is_stunned": None,
    "is_player": None,
    "is_monster": None,
    "is_minion": None,
}

# What `?(deck.<attr> ...)` reads. None takes a `%`.
DECK_ATTRIBUTES = ("remaining",)


def hanging_attributes() -> Dict[str, Tuple[str, Optional[HangingDisposition]]]:
    """Return {condition attribute: (category, disposition or None)} for the hanging
    effect counts: each category and alias, bare and with a disposition prefix
    (`charms`, `beneficial_charm`, `harmful_ot`, ...). None of them takes a `%`."""
    out: Dict[str, Tuple[str, Optional[HangingDisposition]]] = {}
    for canonical, (_, _, _, aliases, _) in HANGING_CATEGORIES.items():
        for name in [canonical] + list(aliases):
            out[name] = (canonical, None)
            out[f"beneficial_{name}"] = (canonical, HangingDisposition.beneficial)
            out[f"harmful_{name}"] = (canonical, HangingDisposition.harmful)
    return out


def _member_attribute_names() -> List[str]:
    # The documented names, without the hanging aliases, so an error message stays readable.
    hanging = [f"{side}{canonical}" for canonical in HANGING_CATEGORIES for side in ("", "beneficial_", "harmful_")]
    return list(MEMBER_ATTRIBUTES) + hanging


def condition_attribute_error(attribute: str) -> Optional[str]:
    """Why `attribute` names nothing a condition can read on any subject, or None.

    A misspelled attribute used to parse and read false on every turn, which looks
    exactly like a condition that doesn't hold.
    """
    if attribute in MEMBER_ATTRIBUTES or attribute in hanging_attributes() or attribute in DECK_ATTRIBUTES:
        return None
    valid = _member_attribute_names()
    close = difflib.get_close_matches(attribute, valid + list(DECK_ATTRIBUTES), n=1)
    if close:
        return f"Unknown condition attribute '{attribute}'. Did you mean '{close[0]}'?"
    return f"Unknown condition attribute '{attribute}'. Valid: {', '.join(valid)}; and deck.remaining."


def condition_clause_error(target_type: TargetType, attribute: str, is_percent: bool) -> Optional[str]:
    """Why `<target>.<attribute>` with or without `%` always reads false, or None.

    `attribute` is one condition_attribute_error accepts; this checks it against its
    subject, and a `%` against the attribute.
    """
    if target_type is TargetType.type_deck:
        if attribute not in DECK_ATTRIBUTES:
            return f"deck has one attribute, remaining, so deck.{attribute} reads nothing."
        if is_percent:
            return "deck.remaining takes no %: a count of cards has no maximum."
        return None
    if attribute not in MEMBER_ATTRIBUTES and attribute not in hanging_attributes():
        return f"'{attribute}' is read on deck only, not on a combatant."
    if is_percent and MEMBER_ATTRIBUTES.get(attribute) is None:
        takes = [name for name, max_name in MEMBER_ATTRIBUTES.items() if max_name]
        return f"'{attribute}' takes no %: it has no maximum. Only {' and '.join(takes)} do."
    return None


class GambitSpec:
    """Filter for spells that 'Gambit' a hanging effect (consume your own
    beneficial-X or the enemy's harmful-X for a bonus)."""
    def __init__(self, hanging_type: HangingType, min_count: int = 1):
        self.hanging_type = hanging_type
        self.min_count = min_count

    def __repr__(self) -> str:
        return f"GambitSpec(hanging_type={self.hanging_type}, min_count={self.min_count})"


class ClearSpec:
    """Filter for spells that 'Clear' a hanging effect (consume your own
    harmful-X or the enemy's beneficial-X for a bonus)."""
    def __init__(self, hanging_type: HangingType, min_count: int = 1):
        self.hanging_type = hanging_type
        self.min_count = min_count

    def __repr__(self) -> str:
        return f"ClearSpec(hanging_type={self.hanging_type}, min_count={self.min_count})"


class EchoSpec:
    """Filter for spells that 'Echo' a hanging effect — read an effect on the
    enemy and apply the same effect type to the caster (value not copied,
    only the type/disposition). Source side is the target, so verb resolution
    is `target+disposition`. With unspecified disposition both halves match."""
    def __init__(self, hanging_type: HangingType, min_count: int = 1):
        self.hanging_type = hanging_type
        self.min_count = min_count

    def __repr__(self) -> str:
        return f"EchoSpec(hanging_type={self.hanging_type}, min_count={self.min_count})"


class SwapSpec:
    """Filter for spells that 'Swap' a hanging effect — exchange N hangings of
    a specific category+disposition between caster and target. Modeled as a
    top-level SpellEffect whose effect_type is swap_charm/swap_ward/
    swap_over_time and whose disposition pins the side."""
    def __init__(self, hanging_type: HangingType, min_count: int = 1):
        self.hanging_type = hanging_type
        self.min_count = min_count

    def __repr__(self) -> str:
        return f"SwapSpec(hanging_type={self.hanging_type}, min_count={self.min_count})"


class NotTypeSpec:
    """`!aoe` inside any<...>: reject a card any of whose effects is this type.

    No __eq__ on purpose -- `SpellType.type_aoe in requirements` must not match a
    negated aoe."""
    def __init__(self, type: SpellType):
        self.type = type

    def __repr__(self) -> str:
        return f"NotTypeSpec(type={self.type})"


class ExcludeNameSpec:
    """`!feint` inside any<...>: reject a card by name. Unquoted is the loose,
    case-insensitive substring match a bare spell move uses; quoted is exact."""
    def __init__(self, name: str, is_literal: bool = False):
        self.name = name
        self.is_literal = is_literal

    def __repr__(self) -> str:
        return f"ExcludeNameSpec(name=\"{self.name}\", is_literal={self.is_literal})"


class TemplateSpell(Spell):
    def __init__(self, requirements: List, optional=False) -> None:
        # `requirements` is a heterogeneous list of SpellType values plus optional
        # post-selection filter specs (GambitSpec / ClearSpec) and the negations
        # (NotTypeSpec / ExcludeNameSpec). req_met and stacks stay SpellType
        # sentinels so existing parsing keeps working.
        self.requirements = requirements
        self.optional = optional

    def __repr__(self) -> str:
        return f"TemplateSpell(requirements={self.requirements}, optional={self.optional})"


class Move:
    def __init__(self, card: Spell, enchant: Spell = None, second_enchant: Spell = None):
        self.card = card
        self.enchant = enchant
        self.second_enchant = second_enchant

    def __repr__(self) -> str:
        return f"Move(card={self.card}, enchant={self.enchant}, second_enchant={self.second_enchant})"


class TargetData:
    def __init__(self, target_type: TargetType, extra_data: Any = None, is_literal: bool = False):
        self.target_type = target_type
        self.extra_data = extra_data
        self.is_literal = is_literal

    def __repr__(self) -> str:
        return f"TargetData(target_type={self.target_type}, extra_data={self.extra_data}, is_literal={self.is_literal})"


class MoveConfig:
    def __init__(self, move: Union[Move, List], target: Union[TargetData, List] = None, condition: Condition = None):
        self.move = move
        self.target = target
        self.condition = condition

    def __repr__(self) -> str:
        cond = f", condition={self.condition}" if self.condition else ""
        return f"MoveConfig(move={self.move}, target={self.target}{cond})"


class PriorityLine:
    def __init__(self, priorities: List[MoveConfig], _round: int = None):
        self.priorities = priorities
        self.round = _round

    def __repr__(self) -> str:
        return f"PriorityLine(priorities={self.priorities}, round={self.round})"


class CombatConfig:
    def __init__(self, rounds: List[PriorityLine]):
        self.specific_rounds: dict[int, PriorityLine] = {}
        self.infinite_rounds: list[PriorityLine] = []
        for _round in rounds:
            if _round.round is None:
                self.infinite_rounds.append(_round)
            else:
                self.specific_rounds[_round.round] = _round

    def __repr__(self) -> str:
        return f"CombatConfig(specific_rounds={self.specific_rounds}, infinite_rounds={self.infinite_rounds})"
