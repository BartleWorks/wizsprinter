"""Counting the team from the end in the host's order (`SprintyCombat.team_order`).

A team that isn't an Adventure Party group sits in the order it walked in, so a host that
knows who its hitter is hands the order over, and `ally(last)` names that player whatever
the seats. `fake_combat()` gives each team member the owner id of its seat, 1 up.
"""

import pytest

from .fakes import Member, fake_combat


def _team(n: int = 4) -> list[Member]:
    return [Member(f"seat {i}") for i in range(1, n + 1)]


@pytest.mark.parametrize("me", range(4))
async def test_with_a_team_order_every_client_counts_the_orders_last_as_last(me):
    team = _team()
    combat = fake_combat([], team=team, me=me)
    # Seat 1 walked in first, but the host's order puts it last: it is the hitter.
    combat.team_order = [4, 3, 2, 1]

    assert await combat.get_nth_ally_or_none(-1) is team[0]
    assert await combat.get_nth_ally_or_none(-2) is team[1]
    assert await combat.get_nth_ally_or_none(-4) is team[3]


@pytest.mark.parametrize("me", range(4))
async def test_without_one_the_seats_decide(me):
    team = _team()
    combat = fake_combat([], team=team, me=me)

    assert await combat.get_nth_ally_or_none(-1) is team[3]


async def test_the_order_is_taken_at_construction_too():
    team = _team(2)
    combat = fake_combat([], team=team)
    plain = type(combat)(combat.client, combat.config, team_order=(1, 2))

    assert plain.team_order == [1, 2]
    assert type(combat)(combat.client, combat.config).team_order is None


async def test_a_player_the_order_names_but_who_is_not_in_the_fight_is_skipped():
    team = _team(3)
    combat = fake_combat([], team=team)
    combat.team_order = [4, 3, 2, 1]  # seat 4's owner is not in this fight

    assert await combat.get_nth_ally_or_none(-1) is team[0]
    assert await combat.get_nth_ally_or_none(-3) is team[2]
    assert await combat.get_nth_ally_or_none(-4) is None


async def test_a_player_the_order_does_not_name_counts_first_in_seat_order():
    team = _team()
    combat = fake_combat([], team=team)
    # Only seats 2 and 4 are ours; seats 1 and 3 are someone else's wizards.
    combat.team_order = [2, 4]

    assert [m.name_ for m in await combat.get_team_in_order()] == ["seat 1", "seat 3", "seat 2", "seat 4"]
    assert await combat.get_nth_ally_or_none(-1) is team[3]


async def test_a_forward_index_still_counts_the_others_in_seat_order():
    team = _team()
    combat = fake_combat([], team=team, me=0)
    combat.team_order = [4, 3, 2, 1]

    assert await combat.get_nth_ally_or_none(0) is team[1]
    assert await combat.get_nth_ally_or_none(2) is team[3]


async def test_a_combat_made_without_init_has_no_order():
    combat = fake_combat([], team=_team(2))
    bare = object.__new__(type(combat))

    assert bare.team_order is None
