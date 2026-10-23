from functools import lru_cache
from typing import *

from lark import Lark

from .backend_base import BaseCombatBackend
from .combat_config_parser import CombatConfig, PriorityLine, get_sprinty_grammar, TreeToConfig, Move, MoveConfig
from ..sprinty_combat import SprintyCombat


@lru_cache(maxsize=1)
def _parser() -> Lark:
    """The combat config parser, built once.

    Building it compiles the grammar, about 77 ms, and a provider is made for every
    fight. One instance is safe to share: lark's Earley parser fixes its state when it
    is built and keeps each parse's in locals.
    """
    return Lark(get_sprinty_grammar())


@lru_cache(maxsize=64)
def parse_config_text(content: str) -> CombatConfig:
    """`content` parsed, once for each distinct text.

    A long config takes most of a second to parse, all of it holding the event loop, and
    a provider is made for every player in every fight, mostly from the same few texts.
    The config is shared between the providers made from one text, which is safe because
    nothing changes a config once it is parsed: a fight only reads it.
    """
    tree = _parser().parse(content)
    return CombatConfigProvider._expand_config(TreeToConfig().transform(tree))


class CombatConfigProvider(BaseCombatBackend):
    def __init__(self, path: str, cast_time: float = 0.2, *, content: str = None):
        """
        Args:
            path: The config file, or a name for `content` when it is given
            cast_time: Seconds the casts settle for
            content: The config itself, read in place of the file
        """
        super().__init__(cast_time=cast_time)
        self.filename = path
        if content is None:
            # UTF-8, not the locale's code page, which on Windows mangled any
            # name outside ASCII
            with open(path, encoding="utf-8") as file:
                content = file.read()
        self.config: CombatConfig = self.parse_config(content)

    @classmethod
    def from_string(cls, content: str, cast_time: float = 0.2) -> "CombatConfigProvider":
        """A provider for a config held as text rather than in a file."""
        return cls("<inline>", cast_time, content=content)

    def parse_config(self, file_contents) -> CombatConfig:
        return parse_config_text(file_contents)

    async def get_real_round(self, r: int) -> Optional[PriorityLine]:
        if r in self.config.specific_rounds:
            return self.config.specific_rounds[r]
        return None

    async def get_relative_round(self, r: int) -> Optional[PriorityLine]:
        if len(self.config.infinite_rounds) > 0:
            return self.config.infinite_rounds[r % len(self.config.infinite_rounds)]
        return None

    async def handle_no_cards_given(self):
        raise RuntimeError(f"Full config fail! \"{self.filename}\" might be empty or contains only explicit rounds. Consider adding a pass or something else")

    @staticmethod
    def _expand_config(config: CombatConfig) -> CombatConfig:
        old_rounds = [x for x in config.specific_rounds.values()] + config.infinite_rounds
        rounds = []
        for old_round in old_rounds:
            priorities = []
            for old_priority in old_round.priorities:
                #if old_priority.move.enchant is None:
                priorities.append(old_priority)
                #elif old_priority.move.enchant and old_priority.move.second_enchant is None:
                #    priorities.append(old_priority)
                    # enchantless_move = Move(old_priority.move.card, None, None)
                    # enchantless = MoveConfig(enchantless_move, old_priority.target)
                    # priorities.append(enchantless)
                #else:
                #    priorities.append(old_priority)
                #    enchantless_move = Move(
                #        old_priority.move.card, old_priority.move.enchant, None)
                #    enchantless = MoveConfig(
                #        enchantless_move, old_priority.target)
                #    priorities.append(enchantless)
            rounds.append(PriorityLine(priorities, old_round.round))

        return CombatConfig(rounds)
