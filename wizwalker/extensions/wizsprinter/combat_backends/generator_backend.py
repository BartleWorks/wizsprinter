from typing import *

from wizwalker.combat.member import CombatMember

from .backend_base import BaseCombatBackend
from .combat_api import *
from ..sprinty_combat import SprintyCombat

class CombatConfigGenerator(BaseCombatBackend):
    def __init__(self, cast_time: float = 0.2):
        super().__init__(cast_time=cast_time)
        self.combat: SprintyCombat # restore autocomplete

    async def get_heal_priorities(self) -> list[MoveConfig]:
        me = await self.combat.get_client_member()
        client_health = await me.health()
        client_max_health = await me.max_health()
        # It can be zero, read mid-change, and dividing by it raised
        if client_max_health <= 0 or client_health / client_max_health > 0.4:
            return []

        return [
            MoveConfig(
                move=Move(
                    card=TemplateSpell(requirements=[SpellType.type_heal_self]),
                )
            ),
            MoveConfig(
                move=Move(
                    card=TemplateSpell(requirements=[SpellType.type_heal, SpellType.type_aoe]),
                )
            ),
        ]

    async def get_real_round(self, r: int) -> Optional[PriorityLine]:
        priorities = []

        # heal
        priorities.extend(await self.get_heal_priorities())
        
        # attack, aoe
        priorities.append(
            MoveConfig(
                move=Move(
                    card=TemplateSpell(requirements=[SpellType.type_damage, SpellType.type_aoe]),
                    enchant=TemplateSpell(requirements=[SpellType.type_enchant], optional=True)
                )
            )
        )

        # attack
        priorities.append(
            MoveConfig(
                move=Move(
                    card=TemplateSpell(requirements=[SpellType.type_damage]),
                    enchant=TemplateSpell(requirements=[SpellType.type_enchant], optional=True)
                ),
                target=TargetData(TargetType.type_enemy)
            )
        )

        # pass
        priorities.append(            
            MoveConfig(move=Move(
                card=NamedSpell("pass")
            ))
        )

        # TODO: Maybe dedupe?
        return PriorityLine(priorities=priorities)

    async def get_relative_round(self, r: int) -> Optional[PriorityLine]:
        # it's all automatic, so they mean the same thing. Awaited: the caller got
        # the coroutine itself where a PriorityLine belonged.
        return await self.get_real_round(r)