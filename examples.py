"""
Simple Normal roles, abilities, and alignments.
"""

from collections.abc import Sequence, Callable, Collection
from typing import Any, TypeGuard, TypeVar
from abc import ABC, abstractmethod
from mafia import (
    AbilityModifier,
    AbilityType,
    Alignment,
    Chat,
    Faction,
    Modifier,
    Role,
    Ability,
    Game,
    Player,
    Visit,
    VisitStatus,
    role_name,
)
from nodes import nodes_in_cycles


def roleblock_player(game: Game, player: Player) -> VisitStatus:
    """Roleblocks a player."""
    success = VisitStatus.FAILURE
    for visit in player.get_visits(game):
        if visit.ability_type is not AbilityType.PASSIVE and "unstoppable" not in visit.tags:
            visit.status = VisitStatus.FAILURE
            visit.tags |= {"roleblocked"}
            success = VisitStatus.SUCCESS
    return success


class Resolver:
    """Resolves visits in a game."""
    
    def do_visit(self, game: Game, visit: Visit) -> int:
        status = visit.perform(game)
        visit.status = status
        if visit.ability_type is AbilityType.PASSIVE and status != VisitStatus.PENDING:
            visit.actor.uses.setdefault(visit.ability, 0)
            visit.actor.uses[visit.ability] += status
        return status
        
    
    def resolve_visit(self, game: Game, visit: Visit) -> int:
        """Resolve a visit and return the result. If the visit cannot be resolved, return VisitStatus.PENDING."""
        # Perform if the ability is immediate.
        if visit.ability.immediate:
            return self.do_visit(game, visit)
        # Wait if the target has a pending commute.
        if any(
            "commute" in v.tags
            for t in visit.targets
            for v in t.get_visitors(game)
            if v.status == VisitStatus.PENDING
        ):
            return VisitStatus.PENDING
        # Perform if the visit is unstoppable.
        if "unstoppable" in visit.tags:
            return self.do_visit(game, visit)
        # Wait if the actor has a pending roleblock.
        if visit.ability_type is not AbilityType.PASSIVE and any(
            "roleblock" in v.tags
            for v in visit.actor.get_visitors(game) 
            if v.status == VisitStatus.PENDING
        ):
            return VisitStatus.PENDING
        # Wait if the target has a pending rolestop.
        if visit.ability_type is not AbilityType.PASSIVE and any(
            "rolestop" in v.tags
            for t in visit.targets
            for v in t.get_visitors(game)
            if v.status == VisitStatus.PENDING
        ):
            return VisitStatus.PENDING
        # Wait if the target has a pending juggernaut (and the visit roleblocks).
        if "roleblock" in visit.tags and any(
            "juggernaut" in v.tags
            for t in visit.targets
            for v in t.get_visitors(game)
            if v.status == VisitStatus.PENDING
        ):
            return VisitStatus.PENDING
        # Perform the visit.
        return self.do_visit(game, visit)

    def resolve_game(self, game: Game) -> None:
        """Resolve all visits in the game."""
        for visit in game.visits:
            if (
                visit.ability_type is not AbilityType.PASSIVE
                and visit.status == VisitStatus.PENDING
            ):
                visit.actor.uses.setdefault(visit.ability, 0)
                visit.actor.uses[visit.ability] += 1
            if visit.ability.immediate:
                self.resolve_visit(game, visit)
        failed_to_resolve: bool = True
        while failed_to_resolve:
            failed_to_resolve = False
            successfully_resolved: bool = False
            for visit in sorted(
                game.visits,
                key=lambda v: (
                    "simultaneous" in v.tags,  # Prioritize simultaneous visits.
                    "unstoppable" in v.tags,  # Prioritize unstoppable visits.
                ),
                reverse=True,
            ):
                if visit.status != VisitStatus.PENDING:
                    continue
                result = self.resolve_visit(game, visit)
                if result == VisitStatus.PENDING:
                    failed_to_resolve = True
                else:
                    successfully_resolved = True
            if failed_to_resolve and not successfully_resolved:
                successfully_resolved = self.resolve_cycles(game)
                if not successfully_resolved:
                    raise RuntimeError("Failed to resolve game.")

    def resolve_cycles(self, game: Game) -> bool:
        successfully_resolved: bool = False

        # Check for mutual roleblocks and invoke the Catastrophic Rule.
        roleblocking_visits: list[tuple[Player, Player]] = []
        for visit in game.visits:
            if visit.status == VisitStatus.PENDING and "roleblock" in visit.tags:
                roleblocking_visits.extend((visit.actor, t) for t in visit.targets)
        catastrophic_rule_players = nodes_in_cycles(roleblocking_visits)
        for player in catastrophic_rule_players:
            roleblock_player(game, player)
            successfully_resolved = True

        return successfully_resolved

    def add_passives(self, game: Game) -> None:
        for player in game.players:
            for ability in player.passives:
                if ability.check(game, player):
                    visit = Visit(actor=player, ability=ability, ability_type=AbilityType.PASSIVE)
                    if ability.immediate:
                        self.resolve_visit(game, visit)
                    else:
                        game.visits.append(visit)


class Kill(Ability):
    """Kills a player."""

    def __init__(
        self, id: str | None = None, killer: str | None = None, tags: frozenset[str] | None = None
    ):
        super().__init__(id, tags)
        if killer is not None:
            self.killer = killer

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        if "killer" not in cls.__dict__:
            cls.killer = cls.__name__.replace("_", " ")

    tags = frozenset({"kill"})
    killer: str

    def perform(
        self, game: Game, actor: Player, targets: Sequence[Player] | None = None, *, visit: Visit
    ) -> VisitStatus:
        if targets is None:
            targets = tuple(actor for _ in range(self.target_count))
        target, *_ = targets
        if "unstoppable" not in visit.tags and any(
            "protect" in v.tags
            for v in target.get_visitors(game)
            if v.status == VisitStatus.PENDING
        ):
            return VisitStatus.PENDING
        target.kill(self.killer)
        return VisitStatus.SUCCESS


class InvestigativeAbility(Ability, ABC):
    """Investigates someone and learns the result."""

    tags = frozenset({"investigate"})

    def perform(
        self, game: Game, actor: Player, targets: Sequence[Player] | None = None, *, visit: Visit
    ) -> VisitStatus:
        if targets is None:
            targets = tuple(actor for _ in range(self.target_count))
        target, *_ = targets
        message: str = self.get_message(game, actor, target, visit=visit)
        actor.private_messages.send(self.id, message)
        return VisitStatus.SUCCESS

    @abstractmethod
    def get_message(self, game: Game, actor: Player, target: Player, *, visit: Visit) -> str: ...


class Rolestop(Ability):
    """Prevents abilities from being performed on a player."""

    tags = frozenset({"rolestop"})

    def perform(
        self, game: Game, actor: Player, targets: Sequence[Player] | None = None, *, visit: Visit
    ) -> int:
        if targets is None:
            targets = tuple(actor for _ in range(self.target_count))
        target, *_ = targets
        # Check if a visitor to the target has a pending juggernaut.
        if any(
            "juggernaut" in v.tags
            for t in target.get_visitors(game)
            if t.status == VisitStatus.PENDING
            for v in t.actor.get_visitors(game)
            if v.status == VisitStatus.PENDING
        ):
            return VisitStatus.PENDING
        max_blocks: int | None
        if visit.ability_type is AbilityType.PASSIVE and isinstance(
            visit.ability, XShot.XShotPrototype
        ):
            uses_remaining = visit.ability.max_uses - actor.uses.get(visit.ability, 0)
            max_blocks = (
                min(self.limit, uses_remaining) if self.limit is not None else uses_remaining
            )
        else:
            max_blocks = self.limit
        successes: int = 0
        for v in target.get_visitors(game):
            if (
                v.status == VisitStatus.PENDING
                and "unstoppable" not in v.tags
                and self.block_check(actor, target, v, visit=visit)
            ):
                if self.block_visit(actor, target, v, visit=visit) >= VisitStatus.SUCCESS:
                    successes += 1
                if max_blocks is not None and max_blocks <= successes:
                    return successes
        return successes

    def block_visit(
        self, actor: Player, target: Player, blocked_visit: Visit, *, visit: Visit
    ) -> VisitStatus:
        blocked_visit.status = VisitStatus.FAILURE
        return VisitStatus.SUCCESS

    def block_check(
        self, actor: Player, target: Player, checked_visit: Visit, *, visit: Visit
    ) -> bool:
        return True

    limit: int | None = None


class ProtectiveAbility(Rolestop):
    tags = frozenset({"protect"})

    def perform(
        self, game: Game, actor: Player, targets: Sequence[Player] | None = None, *, visit: Visit
    ) -> int:
        if targets is None:
            targets = tuple(actor for _ in range(self.target_count))
        target, *_ = targets
        if any(
            "macho" in v.tags
            for v in target.get_visitors(game)
            if v.status == VisitStatus.PENDING
        ):
            return VisitStatus.PENDING
        return super().perform(game, actor, targets, visit=visit)

    def block_check(
        self, actor: Player, target: Player, checked_visit: Visit, *, visit: Visit
    ) -> bool:
        return "kill" in checked_visit.tags


# SIMPLE NORMAL ROLES #


class Vanilla(Role):
    """No abilities."""

    is_adjective: bool = True


class Bodyguard(Role):
    """Protects a player from one kill, but dies if successful."""

    class Bodyguard(ProtectiveAbility):
        def block_visit(
            self, actor: Player, target: Player, blocked_visit: Visit, *, visit: Visit
        ) -> VisitStatus:
            actor.kill(self.id)
            return super().block_visit(actor, target, blocked_visit, visit=visit)

        limit = 1

    actions = (Bodyguard(),)


class Bulletproof(Role):
    """Blocks all kills targeting the player."""

    class Bulletproof(ProtectiveAbility):
        limit = None

    passives = (Bulletproof(),)
    is_adjective: bool = True


class Cop(Role):
    """Checks if a player is aligned with the Town."""

    class Cop(InvestigativeAbility):
        tags = frozenset({"investigate", "gun"})

        def get_message(self, game: Game, actor: Player, target: Player, *, visit: Visit) -> str:
            if "town" in target.alignment.tags:
                return f"{target.name} is aligned with the Town."
            else:
                return f"{target.name} is not aligned with the Town!."

    actions = (Cop(),)
    tags = frozenset({"gun"})


class Doctor(Role):
    """Protects a player from one kill."""

    class Doctor(ProtectiveAbility):
        tags = frozenset({"protect", "mafia_no_gun"})
        limit = 1

    actions = (Doctor(),)


class Friendly_Neighbor(Role):
    """Informs a player of the actor's alignment."""

    class Friendly_Neighbor(Ability):
        tags = frozenset({"inform"})

        def perform(
            self,
            game: Game,
            actor: Player,
            targets: Sequence[Player] | None = None,
            *,
            visit: Visit,
        ) -> VisitStatus:
            if targets is None:
                targets = tuple(actor for _ in range(self.target_count))
            target, *_ = targets
            message: str = f"{actor.name} is aligned with the {actor.alignment}!"
            target.private_messages.send(self.id, message)
            return VisitStatus.SUCCESS

    actions = (Friendly_Neighbor(),)


class Gunsmith(Role):
    """Checks if a player has a gun in flavor.

    Mafia (except Traitors, Doctors, and Medical Students), Cops, Vigilantes, Gunsmiths,
    Role Cops, Vanilla Cops, PT Cops, Vengefuls, Modifier Cops, Detectives, Neapolitans,
    Goon Cops, Agents, Auditors, Specialists, Backups and JoATs of the aforementioned roles,
    Inventors that can give out the aforementioned roles, and players with inventions of the
    aforementioned roles have guns."""

    class Gunsmith(InvestigativeAbility):
        tags = frozenset({"investigate", "gun"})

        def get_message(self, game: Game, actor: Player, target: Player, *, visit: Visit) -> str:
            if any(
                "gun" in a.tags
                for a in [*target.actions, *target.passives, *target.shared_actions]
            ) or (
                "mafia" in target.alignment.tags
                and not any(
                    "mafia_no_gun" in a.tags
                    for a in [*target.actions, *target.passives, *target.shared_actions]
                )
            ):
                return f"{target.name} has a gun!"
            else:
                return f"{target.name} does not have a gun."

    actions = (Gunsmith(),)


class Innocent_Child(Role):
    """Informs all players of the actor's alignment."""

    class Innocent_Child(Ability):
        phase = None
        immediate = True
        target_count = 0
        tags = frozenset({"inform"})

        def check(
            self, game: Game, actor: Player, targets: Sequence[Player] | None = None
        ) -> bool:
            # Innocent Child can only be used once.
            return super().check(game, actor, targets) and actor.uses.get(self, 0) == 0

        def perform(
            self,
            game: Game,
            actor: Player,
            targets: Sequence[Player] | None = None,
            *,
            visit: Visit,
        ) -> VisitStatus:
            message: str = f"{actor.name} is aligned with the {actor.alignment.id}!"
            game.chats["global"].send(self.id, message)
            return VisitStatus.SUCCESS

    actions = (Innocent_Child(),)


class Jailkeeper(Role):
    """Protects a player from kills and roleblocks a player simultaneously."""

    class Jailkeeper(ProtectiveAbility):
        tags = frozenset({"protect", "roleblock"})

        def perform(
            self,
            game: Game,
            actor: Player,
            targets: Sequence[Player] | None = None,
            *,
            visit: Visit,
        ) -> VisitStatus:
            if targets is None:
                targets = tuple(actor for _ in range(self.target_count))
            target, *_ = targets
            roleblock_result = roleblock_player(game, target)
            protection_result = super().perform(game, actor, targets, visit=visit)
            return (
                VisitStatus.SUCCESS
                if roleblock_result or protection_result
                else VisitStatus.FAILURE
            )

        limit = None

    actions = (Jailkeeper(),)


class Juggernaut(Role):
    """If the actor performs the factional kill, it cannot be prevented."""

    class Juggernaut(Ability):
        tags = frozenset({"juggernaut", "unstoppable"})

        def perform(
            self,
            game: Game,
            actor: Player,
            targets: Sequence[Player] | None = None,
            *,
            visit: Visit,
        ) -> int:
            if targets is None:
                targets = tuple(actor for _ in range(self.target_count))
            target, *_ = targets
            max_upgrades: int | None = None
            if visit.ability_type is AbilityType.PASSIVE and isinstance(
                visit.ability, XShot.XShotPrototype
            ):
                max_upgrades = visit.ability.max_uses - actor.uses.get(visit.ability, 0)
            successes: int = 0
            for v in target.get_visits(game):
                if "factional_kill" in visit.tags and visit.status == VisitStatus.PENDING:
                    v.tags |= frozenset({"unstoppable"})
                    successes += 1
                    if max_upgrades is not None and max_upgrades <= successes:
                        return successes
            return successes

        def check(
            self, game: Game, actor: Player, targets: Sequence[Player] | None = None
        ) -> bool:
            # Juggernaut can only target self.
            return (
                (self.phase is None or self.phase == game.phase)
                and actor.is_alive
                and (targets is None or actor in targets)
            )

    actions = (Juggernaut(),)


class Macho(Role):
    """Cannot be protected from kills."""

    class Macho(Rolestop):
        tags = frozenset({"macho", "rolestop"})

        def block_check(
            self, actor: Player, target: Player, checked_visit: Visit, *, visit: Visit
        ) -> bool:
            return "protect" in checked_visit.tags

    passives = (Macho(),)
    is_adjective: bool = True


class Mason(Role):
    """Can chat with other Masons."""

    def player_init(self, game: Game, player: Player) -> None:
        if self.id not in game.chats:
            game.chats[self.id] = Chat(participants={player})
        else:
            game.chats[self.id].participants.add(player)
        game.chats[self.id].send(
            self.id, f"{player.name} is a {role_name(player.role, player.alignment)}."
        )

    tags = frozenset({"chat", "informed"})


class Neapolitan(Role):
    """Checks if a player is a Vanilla Townie."""

    class Neapolitan(InvestigativeAbility):
        tags = frozenset({"investigate", "gun"})

        def get_message(self, game: Game, actor: Player, target: Player, *, visit: Visit) -> str:
            if target.role.is_role(Vanilla) and "town" in target.alignment.tags:
                return f"{target.name} is a Vanilla Townie."
            else:
                return f"{target.name} is not a Vanilla Townie."

    actions = (Neapolitan(),)


class Neighborizer(Role):
    """Adds a player into a neighborhood."""

    class Neighborizer(Ability):
        def perform(
            self,
            game: Game,
            actor: Player,
            targets: Sequence[Player] | None = None,
            *,
            visit: Visit,
        ) -> VisitStatus:
            if targets is None:
                targets = tuple(actor for _ in range(self.target_count))
            target, *_ = targets
            chat_id = f"{self.id}:{actor.name}"
            if chat_id not in game.chats:
                game.chats[chat_id] = Chat(participants={actor, target})
            else:
                game.chats[chat_id].participants.add(target)
            game.chats[chat_id].send(
                self.id, f"{target.name} has been added into the neighborhood."
            )
            return VisitStatus.SUCCESS

    def player_init(self, game: Game, player: Player) -> None:
        chat_id = f"{self.id}:{player.name}"
        game.chats[chat_id] = Chat(participants={player})
        game.chats[chat_id].send(self.id, f"{player.name} is a {player.role.id}.")

    tags = frozenset({"chat"})
    actions = (Neighborizer(),)


class Roleblocker(Role):
    """Roleblocks a player."""

    class Roleblocker(Ability):
        tags = frozenset({"roleblock"})

        def perform(
            self,
            game: Game,
            actor: Player,
            targets: Sequence[Player] | None = None,
            *,
            visit: Visit,
        ) -> VisitStatus:
            if targets is None:
                targets = tuple(actor for _ in range(self.target_count))
            target, *_ = targets
            return roleblock_player(game, target)

    actions = (Roleblocker(),)


class Rolecop(Role):
    """Checks a player to learn their role."""

    class Rolecop(InvestigativeAbility):
        tags = frozenset({"investigate", "gun"})

        def get_message(self, game: Game, actor: Player, target: Player, *, visit: Visit) -> str:
            return f"{target.name} is a {target.role.id}."

    actions = (Rolecop(),)


class Tracker(Role):
    """Checks a player to learn who they targeted."""

    class Tracker(InvestigativeAbility):
        tags = frozenset({"investigate", "gun"})

        def get_message(self, game: Game, actor: Player, target: Player, *, visit: Visit) -> str:
            visits: list[Player] = []
            for visit in target.get_visits(game):
                if visit.ability_type is not AbilityType.PASSIVE and all(
                    tag not in visit.tags for tag in {"hidden", "roleblocked"}
                ):
                    visits.extend(visit.targets)
            
            if visits:
                return f"{target.name} targeted {', '.join(p.name for p in visits)}."
            else:
                return f"{target.name} did not target anyone."

    actions = (Tracker(),)


class Vanilla_Cop(Role):
    """Checks if a player is Vanilla."""

    class Vanilla_Cop(InvestigativeAbility):
        tags = frozenset({"investigate", "gun"})

        def get_message(self, game: Game, actor: Player, target: Player, *, visit: Visit) -> str:
            if target.role.is_role(Vanilla):
                return f"{target.name} is Vanilla."
            else:
                return f"{target.name} is not Vanilla."

    actions = (Vanilla_Cop(),)


class Vigilante(Role):
    """Kills a player."""

    class Vigilante(Kill):
        tags = frozenset({"kill", "gun"})

    actions = (Vigilante(),)


class Watcher(Role):
    """Checks a player to learn who targeted them."""

    class Watcher(InvestigativeAbility):
        tags = frozenset({"investigate", "gun"})

        def get_message(self, game: Game, actor: Player, target: Player, *, visit: Visit) -> str:
            visits: list[Player] = []
            for visit in target.get_visitors(game):
                if visit.ability_type is not AbilityType.PASSIVE and all(
                    tag not in visit.tags for tag in {"hidden", "roleblocked"}
                ):
                    visits.append(visit.actor)
            if visits:
                return f"{target.name} was targeted by {', '.join(p.name for p in visits)}."
            else:
                return f"{target.name} was not targeted by anyone."

    actions = (Watcher(),)


# REGULAR NORMAL ROLES #

class Alien(Role):
    """Kidnaps a player at night to make all actions targeting them
    fail, and prevent them from using any abilities.
    """
    
    class Alien(Rolestop):
        tags = frozenset({"rolestop", "roleblock"})

        def perform(self,
                    game: Game,
                    actor: Player,
                    targets: Sequence[Player] | None = None,
                    *,
                    visit: Visit) -> VisitStatus:
            if targets is None:
                targets = tuple(actor for _ in range(self.target_count))
            target, *_ = targets
            roleblock_result = roleblock_player(game, target)
            rolestop_result = super().perform(game, actor, targets, visit=visit)
            return (
                VisitStatus.SUCCESS
                if roleblock_result or rolestop_result
                else VisitStatus.FAILURE
            )
    
    actions = (Alien(),)


class Ascetic(Role):
    """Non-killing actions targeting this player will fail."""

    class Ascetic(Rolestop):
        def block_check(
            self, actor: Player, target: Player, checked_visit: Visit, *, visit: Visit
        ) -> bool:
            return "kill" not in checked_visit.tags

    passives = (Ascetic(),)
    is_adjective: bool = True


class Commuter(Role):
    """Commutes at night to make any actions targeting them fail."""

    class Commuter(Rolestop):
        tags = frozenset({"rolestop", "commute", "unstoppable"})

        def perform(self, game: Game, actor: Player, targets: Sequence[Player] | None = None, *, visit: Visit) -> VisitStatus:
            if targets is None:
                targets = tuple(actor for _ in range(self.target_count))
            target, *_ = targets
            success = VisitStatus.FAILURE
            for v in target.get_visitors(game):
                if v.status == VisitStatus.PENDING:
                    v.status = VisitStatus.FAILURE
                    success = VisitStatus.SUCCESS
            for v in target.get_visits(game):
                if v is not visit and v.status == VisitStatus.PENDING:
                    v.status = VisitStatus.FAILURE
            return success
        
        def check(
            self, game: Game, actor: Player, targets: Sequence[Player] | None = None
        ) -> bool:
            # Commuter can only target self.
            return (
                (self.phase is None or self.phase == game.phase)
                and actor.is_alive
                and (targets is None or actor in targets)
            )

    actions = (Commuter(),)


class Companion(Role):
    """Is informed that another player is Town."""
    
    class Companion(Ability):
        tags = frozenset({"inform"})
        immediate = True
        target_count = 0

        def __init__(self, informed_player: Player | None = None, id: str | None = None, tags: frozenset[str] | None = None):
            self.informed_player = informed_player
            super().__init__(id, tags)

        def perform(self, game: Game, actor: Player, targets: Sequence[Player] | None = None, *, visit: Visit) -> VisitStatus:
            if self.informed_player is None:
                raise TypeError("Companion has no informed player.")
            message: str = f"{self.informed_player.name} is aligned with the Town."
            actor.private_messages.send(self.id, message)
            return VisitStatus.SUCCESS
        
        def check(self, game: Game, actor: Player, targets: Sequence[Player] | None = None) -> bool:
            # Companion can only be used once.
            return super().check(game, actor, targets) and actor.uses.get(self, 0) == 0

    def __init__(self, id: str | None = None, actions: tuple[Ability, ...] | None = None, passives: tuple[Ability, ...] | None = None, shared_actions: tuple[Ability, ...] | None = None, tags: frozenset[str] | None = None, is_adjective: bool | None = None, informed_player: Player | None = None):
        super().__init__(id, actions, passives, shared_actions, tags, is_adjective)
        self.informed_player = informed_player

    def player_init(self, game: Game, player: Player) -> None:
        player.actions.append(Companion.Companion(self.informed_player))


class Detective(Role):
    """Checks if a player attempted to kill someone."""

    class Detective(InvestigativeAbility):
        tags = frozenset({"investigate", "gun"})


        def get_message(self, game: Game, actor: Player, target: Player, *, visit: Visit) -> str:
            if any(
                "kill" in v.tags
                for v in target.get_visits(game)
                if v.ability_type is not AbilityType.PASSIVE
            ):
                return f"{target.name} has tried to kill someone!"
            else:
                return f"{target.name} has not tried to kill anyone."

    actions = (Detective(),)


class Fruit_Vendor(Role):
    """Tells a player that they were given fruit, but not who gave it to them."""

    class Fruit_Vendor(Ability):
        def perform(self, game: Game, actor: Player, targets: Sequence[Player] | None = None, *, visit: Visit) -> VisitStatus:
            if targets is None:
                targets = tuple(actor for _ in range(self.target_count))
            target, *_ = targets
            target.private_messages.send(self.id, "You were given fruit.")
            return VisitStatus.SUCCESS

    actions = (Fruit_Vendor(),)


class Goon_Cop(Role):
    """Checks if a player is a Mafia Goon."""

    class Goon_Cop(InvestigativeAbility):
        tags = frozenset({"investigate", "gun"})

        def get_message(self, game: Game, actor: Player, target: Player, *, visit: Visit) -> str:
            if target.role.is_role(Vanilla) and "mafia" in target.alignment.tags:
                return f"{target.name} is a Mafia Goon!"
            else:
                return f"{target.name} is not a Mafia Goon."

    actions = (Goon_Cop(),)


class Hider(Role):
    """Protects the actor from direct kills, but if the target is killed, the actor is also killed."""

    class Protect_Self(ProtectiveAbility):
        def block_check(
            self, actor: Player, target: Player, checked_visit: Visit, *, visit: Visit
        ):
            return (
                super().block_check(actor, target, checked_visit, visit=visit)
                and checked_visit.ability_type is not AbilityType.PASSIVE
            )
    
    class Lifelink(Ability):
        def perform(self, game: Game, actor: Player, targets: Sequence[Player] | None = None, *, visit: Visit) -> VisitStatus:
            if targets is None:
                targets = tuple(actor for _ in range(self.target_count))
            target, *_ = targets
            if any(
                "kill" in v.tags
                for v in target.get_visitors(game)
                if v.status == VisitStatus.SUCCESS
                and v.ability_type is not AbilityType.PASSIVE
            ):
                actor.kill(self.id)
                return VisitStatus.FAILURE
            if any(
                "kill" in v.tags
                for v in target.get_visitors(game)
                if v.status == VisitStatus.PENDING
                and v.ability_type is not AbilityType.PASSIVE
            ):
                return VisitStatus.PENDING
            return VisitStatus.SUCCESS

    class Hider(Ability):
        tags = frozenset("simultaneous")
        
        def __init__(self, id: str | None = None, tags: frozenset[str] | None = None):
            super().__init__(id, tags)
            self.abilities: list[Ability] = [
                Hider.Protect_Self(self.id, Hider.Protect_Self.tags | {"hidden"}),
                Hider.Lifelink(self.id, Hider.Lifelink.tags | {"hidden"}),
            ]

        def perform(self, game: Game, actor: Player, targets: Sequence[Player] | None = None, *, visit: Visit) -> VisitStatus:
            if targets is None:
                targets = tuple(actor for _ in range(self.target_count))
            visit_targets: list[tuple[Player, ...]] = [(actor,), tuple(targets)]
            visit_types: list[AbilityType] = [AbilityType.PASSIVE, AbilityType.ACTION]
            for ability, a_targets, a_type in zip(self.abilities, visit_targets, visit_types):
                visit = Visit(actor=actor, targets=a_targets, ability=ability, ability_type=a_type)
                game.visits.append(visit)
            return VisitStatus.SUCCESS
    
    actions = (Hider(),)

@lambda x: x()
class Jack_of_All_Trades:
    """Has multiple pre-determined 1-Shot roles."""
    def __call__(self, roles: tuple[type[Role], ...] | None = None, id: str | None = None, tags: frozenset[str] | None = None) -> type[Role]:
        if roles is None:
            roles = (Cop, Vigilante, Doctor, Roleblocker)
        _roles = roles

        if id is None:
            id = self.id
        _id = id

        if tags is None:
            tags = frozenset().union(*(r.tags for r in roles))
        _tags = tags
        
        class Jack_of_All_Trades(Role):
            def __init__(self, id: str | None = None, actions: tuple[Ability, ...] | None = None, passives: tuple[Ability, ...] | None = None, shared_actions: tuple[Ability, ...] | None = None, tags: frozenset[str] | None = None, is_adjective: bool | None = None):
                super().__init__(id, actions, passives, shared_actions, tags)
            
            roles = tuple(XShot(1)(r)() for r in _roles)
            tags = _tags
            actions = tuple(XShot(1)(type(a))(a.id, a.tags) for r in roles for a in r.actions)
            passives = tuple(XShot(1)(type(a))(a.id, a.tags) for r in roles for a in r.passives)
            shared_actions = tuple(XShot(1)(type(a))(a.id, a.tags) for r in roles for a in r.shared_actions)
            
            id = f"{_id} {', '.join(r.id for r in roles)}"
    
            def is_role(self, role: Any) -> TypeGuard[Role | str | type[Role] | Callable[..., type[Role]]]:
                return role is Jack_of_All_Trades or super().is_role(role) or any(r.is_role(role) for r in self.roles)
    
        return Jack_of_All_Trades

    id: str = "Jack of All Trades"


class Medical_Student(Role):
    """Protects a Vanilla player from one kill."""
    class Medical_Student(Doctor.Doctor):
        tags = frozenset({"protect", "mafia_no_gun"})

        def perform(self, game: Game, actor: Player, targets: Sequence[Player] | None = None, *, visit: Visit) -> int:
            if targets is None:
                targets = tuple(actor for _ in range(self.target_count))
            target, *_ = targets
            if target.role.is_role(Vanilla):
                return super().perform(game, actor, targets, visit=visit)
            return VisitStatus.FAILURE

    actions = (Medical_Student(),)


class 

# ROLE MODIFIERS #

T_RoleAlign = TypeVar("T_RoleAlign", Role, Alignment)


class XShot(AbilityModifier):
    """Can only use their abilities X amount of times."""

    class XShotPrototype(Ability):
        max_uses: int

    def __init__(
        self,
        max_uses: int | None = None,
        id: str | None = None,
        tags: frozenset[str] | None = None,
    ):
        if id is None:
            self.id = self._id
        super().__init__(id, tags)
        if max_uses is not None:
            self.max_uses = max_uses

    def modify_ability(self, ability: type[Ability]) -> type[Ability]:
        def check(
            method_self: XShot.XShotPrototype,
            game: Game,
            actor: Player,
            targets: Sequence[Player] | None = None,
        ) -> bool:
            return (
                ability.check(method_self, game, actor, targets)
                and actor.uses.get(method_self, 0) < method_self.max_uses
            )

        return type(
            f"{self!r}({ability.__name__})",
            (XShot.XShotPrototype, ability),
            dict(
                id=ability.id,
                max_uses=self.max_uses,
                tags=ability.tags | self.tags,
                check=check,
            ),
        )

    id = "X-Shot"
    @property
    def _id(self) -> str:
        return f"{self.max_uses}-Shot"

    max_uses: int = 1


class Night_Specific(AbilityModifier):
    """Can only use their abilities on specific nights."""
    
    def __init__(
        self,
        id: str | None = None,
        night_check: Callable[[int], bool] | None = None,
        tags: frozenset[str] | None = None,
    ):
        super().__init__(id, tags)
        if night_check is not None:
            self.night_check = night_check  # type: ignore[method-assign]

    def modify_ability(self, ability: type[Ability]) -> type[Ability]:
        def check(
            method_self: Ability,
            game: Game,
            actor: Player,
            targets: Sequence[Player] | None = None,
        ) -> bool:
            return ability.check(method_self, game, actor, targets) and self.night_check(
                game.day_no
            )

        return type(
            f"{self!r}({ability.__name__})",
            (ability,),
            dict(
                tags=ability.tags | self.tags,
                check=check,
            ),
        )

    def night_check(self, day_no: int, /) -> bool:
        raise NotImplementedError


class Night_X(Night_Specific):
    """Can only use their abilities on nights listed."""
    def __init__(
        self,
        nights: Collection[int] | None = None,
        id: str | None = None,
        tags: frozenset[str] | None = None,
    ):
        if nights is not None:
            self.nights = frozenset(nights)
        super().__init__(id, tags=tags)
        if id is None:
            self.id = self._id

    nights: frozenset[int] = frozenset()

    def night_check(self, day_no: int, /) -> bool:
        return day_no in self.nights

    id = "Night X"
    @property
    def _id(self) -> str:
        return f"Night {','.join(str(n) for n in sorted(self.nights))}"

class Novice(Night_Specific):
    """Cannot use their abilities on the first night."""
    def night_check(self, day_no: int, /) -> bool:
        return day_no > 1


class Odd_Night(Night_Specific):
    """Can only use their abilities on odd nights."""
    def night_check(self, day_no: int, /) -> bool:
        return bool(day_no % 2)


class Even_Night(Night_Specific):
    """Can only use their abilities on even nights."""
    def night_check(self, day_no: int) -> bool:
        return not (day_no % 2)


# ALIGNMENTS #


class Town(Faction):
    """The uninformed majority."""

    tags = frozenset({"town"})
    demonym = "{alignment}ie"


class Mafia(Faction):
    """The informed minority."""

    class Mafia_Factional_Kill(Kill):
        tags = frozenset({"kill", "factional_kill"})

    def player_init(self, game: Game, player: Player) -> None:
        if self.id not in game.chats:
            game.chats[self.id] = Chat(participants={player})
        else:
            game.chats[self.id].participants.add(player)
        game.chats[self.id].send(
            self.id, f"{player.name} is a {role_name(player.role, player.alignment)}."
        )

    shared_actions = (Mafia_Factional_Kill(),)
    tags = frozenset({"mafia", "chat", "informed"})
    demonym = "{alignment._demonym}"
    role_names: dict[str, str] = {
        "Vanilla": "{alignment} Goon",
    }
    
    @property
    def _demonym(self) -> str:
        if self.id.endswith("fia"):
            return f"{self.id[:1]}oso"
        else:
            return f"{self} Goon"


class Serial_Killer(Faction):
    """Self-aligned third party."""

    class Serial_Killer_Factional_Kill(Kill):
        tags = frozenset({"kill", "factional_kill"})

    actions = (Serial_Killer_Factional_Kill(),)
    tags = frozenset({"third_party"})
    role_names: dict[str, str] = {
        "Vanilla": "{alignment}",
    }