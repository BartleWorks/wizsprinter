# Combat Config DSL

A combat config says what one wizard casts, round by round. It is parsed by the Lark
grammar in `combat_config_parser.py`; conditions (`?(…)`) have a page of their own,
`CONDITIONS.md`.

## Lines and rounds

```
# Round-specific lines (optional round number)
{1} move_expr @ target | move_expr @ target | pass
{2} move_expr @ target
# Infinite repeating lines (no round number)
move_expr @ target | move_expr @ target
```

`|` separates priorities in order: the first one that can be cast is cast. `pass`
gives the round up.

`&` chains moves inside one priority, each with its own target, run in order:
`willcast & any<damage> @ enemy`.

## Moves

```
# Named spell (substring match by default)
"Tempest" @ aoe

# Template spell (matches by effect types)
any<damage> @ enemy
any<heal> @ self
any<trap & inc_damage> @ enemy        # AND of types
any<blade & out_damage>[sharp] @ self  # with enchant

# Negation with ! (combined with &)
any<trap & !aoe> @ enemy              # a trap, but not an AoE one
any<trap & !feint> @ boss             # a trap, but no card whose name contains "feint"
any<trap & !"Feint"> @ boss           # a trap, but not the card named exactly Feint

# Enchantment variants
any<damage>[epic] @ enemy             # enchant with any<enchant> named "epic"
any<heal>[potent] @ self
```

A move takes up to two enchants in brackets, applied in order.

`!word` negates a spell type when `word` is one, and excludes a card by name otherwise.
An unquoted name is the same loose, case-insensitive substring match a bare spell move
uses, so `!feint` also rules out Mass Feint (`Feint Mass - Amulet`); a quoted name is
exact. A negated type rules out every card with that effect, AoE or not.

`&` is an AND over the card's effects, not within one effect: each type needs *some*
effect that satisfies it. `aoe` is about whom an effect targets, not what it does — it
matches any effect aimed at a whole team, either side: AoE damage, a mass trap or charm,
a team blade, ward or heal (not an aura, which targets self, or a global). So
`any<trap & aoe>` is a mass trap, `any<blade & aoe>` a team blade, and `any<damage & aoe>`
an AoE hit. Blade, charm, ward and trap match single-target and team effects alike, so
bare `any<trap>` includes mass traps; write `any<trap & !aoe>` for single-target only.
With `aoe` in the template, a card with a single-target damage effect on an enemy is
rejected (Storm Beetle), and the matches are ranked by AoE damage, which leaves a
non-damage clause in hand order.

`stacks` keeps a buff only when it would add to what already hangs where it lands:
`any<blade & stacks>[sharp] @ ally(last)`. Two effects with the same spell template id and
the same enchant template id don't stack, whoever cast them, and the move's own `[...]`
enchant counts. A mass card stacks while one living member of its side lacks it.
`CONDITIONS.md` has the rules.

`aura` is an aura on the caster (Amplify, Stabilize, Mend); `harmful_aura` is one cast at
an enemy (Attenuate: +20% incoming damage for four rounds). A trap has no rounds, so
neither matches one. `stronger` keeps an aura card only when it beats, for the caster's
side, the aura its target already holds: a participant holds one aura and a new one
replaces it, so `any<harmful_aura & inc_damage & stronger> @ boss` replaces the boss's own
Frenzy or a weaker Attenuate, and never a stronger one.

`req_met`, `stacks`, `stronger` and the hanging verbs (`gambit(…)` and its siblings) cannot be
negated — they are checked after a card is picked, so there is nothing for the negation
to test.

The grammar's `spell_type` rule lists every type keyword.

### Special moves

| move | does |
|---|---|
| `pass` | gives the round up; held enchants run first |
| `willcast` | casts the pet's Willcast card, if it is castable |
| `draw`, `draw(N)` | draws one card, or N, while the hand has room |
| `discard @ spell(…)` | discards the named cards from hand |

A priority whose every move is aimed at a card in hand (`[sharp] @ spell(any<damage>)`)
only enchants: it never ends the turn, so it is held and run just before the round's card
is cast, and only when that card is not an attack.

## Targets

| token | means |
|---|---|
| `self` | the caster |
| `boss` | the boss, if it is alive and targetable |
| `enemy`, `enemy(N)` | the first, or Nth (0-indexed), enemy a spell can be cast at; `enemy(-N)` counts from the end |
| `ally`, `ally(N)` | the first, or Nth, ally; `ally(last)` is the same as `ally(-1)` |
| `enemies`, `allies` | every targetable enemy; the caster and every ally |
| `aoe` | no single target: the card's own area |
| `Nightshade`, `"Lord Nightshade"` | the combatant whose name contains it, or is exactly it when quoted (there is no `named:` prefix) |
| `spell(…)` | a card in hand, by name or template: what an enchant or `discard` is aimed at |
| `select(a, b, …)` | several targets, each resolved as above |

`enemy` skips an enemy that is dead or untargetable; `CONDITIONS.md`, *Which enemies
count*, has the detail.
