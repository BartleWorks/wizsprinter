import pytest

from wizwalker.extensions.wizsprinter.combat_backends.combat_config_parser import SpellType, TemplateSpell
from wizwalker.extensions.wizsprinter.combat_backends.config_backend import CombatConfigProvider
from wizwalker.extensions.wizsprinter.combat_backends.generator_backend import CombatConfigGenerator


def test_reads_a_config_file_as_utf8(tmp_path):
    # The locale's code page read these bytes as other characters
    path = tmp_path / "strategy.txt"
    path.write_text('"Rêve Éternel" @ boss\npass', encoding="utf-8")
    provider = CombatConfigProvider(str(path))
    assert provider.filename == str(path)
    assert provider.config.infinite_rounds[0].priorities[0].move.card.name == "Rêve Éternel"


def test_a_config_from_a_string():
    provider = CombatConfigProvider.from_string("{1} blade @ self\npass", cast_time=0.5)
    assert provider.cast_time == 0.5 and provider.filename == "<inline>"
    assert set(provider.config.specific_rounds) == {1}


async def test_rounds_by_number_and_the_rest_in_turn():
    provider = CombatConfigProvider.from_string("{2} blade @ self\nfeint @ boss\ntempest")
    assert (await provider.get_real_round(2)).priorities[0].move.card.name == "blade"
    assert await provider.get_real_round(1) is None
    names = [(await provider.get_relative_round(r)).priorities[0].move.card.name for r in range(4)]
    assert names == ["feint", "tempest", "feint", "tempest"]


async def test_a_config_of_numbered_rounds_alone_has_nothing_else():
    provider = CombatConfigProvider.from_string("{1} pass")
    assert await provider.get_relative_round(5) is None
    with pytest.raises(RuntimeError):
        await provider.handle_no_cards_given()


class Member:
    def __init__(self, health, max_health):
        self._health, self._max = health, max_health

    async def health(self):
        return self._health

    async def max_health(self):
        return self._max


class Combat:
    def __init__(self, member):
        self.member = member

    async def get_client_member(self):
        return self.member


def generator(health, max_health) -> CombatConfigGenerator:
    backend = CombatConfigGenerator()
    backend.attach_combat(Combat(Member(health, max_health)))
    return backend


async def test_the_generator_relative_round_is_a_priority_line():
    # It returned the coroutine get_real_round made, unawaited
    line = await generator(100, 100).get_relative_round(3)
    assert line.priorities[-1].move.card.name == "pass"


async def test_the_generator_heals_when_low():
    line = await generator(30, 100).get_real_round(1)
    first = line.priorities[0].move.card
    assert isinstance(first, TemplateSpell) and first.requirements == [SpellType.type_heal_self]


async def test_the_generator_attacks_when_healthy():
    line = await generator(90, 100).get_real_round(1)
    assert SpellType.type_heal_self not in line.priorities[0].move.card.requirements


async def test_the_generator_survives_a_max_health_of_zero():
    line = await generator(0, 0).get_real_round(1)
    assert line.priorities
