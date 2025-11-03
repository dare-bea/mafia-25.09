"""
Simple Normal roles, abilities, and alignments.
"""

from collections.abc import Sequence, Callable, Collection
from dataclasses import replace
from itertools import product
from typing import Any, Generator, TypeVar
from abc import ABC, abstractmethod
from mafia import (
    AbilityModifier,
    AbilityType,
    Alignment,
    Chat,
    PrivateChat,
    Faction,
    Modifier,
    Role,
    Ability,
    Game,
    Player,
    Visit,
    VisitStatus,
)
from nodes import nodes_in_cycles


def roleblock_player(game: Game, player: Player, visit: Visit | None = None) -> VisitStatus:
    """Roleblocks a player."""
    success = VisitStatus.FAILURE
    for v in player.get_visits(game):
        if visit is not None and not Personal.can_interact(visit, v):
            continue
        if v.ability_type is not AbilityType.PASSIVE and "unstoppable" not in v.tags:
            v.status = VisitStatus.FAILURE
            v.tags |= {"roleblocked"}
            success = VisitStatus.SUCCESS
    return success


def visit_is_visible(visit: Visit, game: Game) -> bool:
    return (
        visit.ability_type is not AbilityType.PASSIVE
        and "hidden" not in visit.tags
        and "roleblocked" not in visit.tags
        and not visit.is_self_target()
        and visit.is_active_time(game)
    )


def has_valid_targets(
    ability: Ability, game: Game, actor: Player, is_passive: bool = False
) -> bool:
    """Check if an ability has any valid targets."""
    if is_passive:
        return ability.check(game, actor)
    if ability.target_count == 0:
        return ability.check(game, actor, ())
    for targets in product(game.players, repeat=ability.target_count):
        if ability.check(game, actor, targets):
            return True
    return False

def get_valid_targets(
    ability: Ability, game: Game, actor: Player, is_passive: bool = False
) -> Generator[tuple[Player, ...], None, None]:
    """Get all valid targets for an ability."""
    if is_passive and ability.check(game, actor):
        yield tuple(actor for _ in range(ability.target_count))
        return
    for targets in product(game.players, repeat=ability.target_count):
        if ability.check(game, actor, targets):
            yield targets

class Resolver:
    """Resolves visits in a game."""

    lazy_allowed: bool = True

    def do_visit(self, game: Game, visit: Visit) -> int:
        status = visit.perform(game)
        visit.status = status
        if visit.ability_type is AbilityType.PASSIVE and status != VisitStatus.PENDING:
            visit.actor.uses.setdefault(visit.ability, 0)
            visit.actor.uses[visit.ability] += status
        return status

    def resolve_visit(self, game: Game, visit: Visit) -> int:
        """Resolve a visit and return the result. If the visit cannot be resolved, return VisitStatus.PENDING."""
        # Prevent if the visit is lazy and lazy is not allowed.
        if "lazy" in visit.tags and not self.lazy_allowed:
            visit.status = VisitStatus.FAILURE
            return VisitStatus.FAILURE
        # Perform if the ability is immediate.
        if visit.ability.immediate:
            return self.do_visit(game, visit)
        # Wait if the target has a pending commute.
        if any(
            "commute" in v.tags
            for t in visit.targets
            for v in t.get_visitors(game)
            if v.is_active(game)
        ):
            return VisitStatus.PENDING
        # Perform if the visit is unstoppable.
        if "unstoppable" in visit.tags:
            return self.do_visit(game, visit)
        # Wait if the actor has a pending roleblock.
        if visit.ability_type is not AbilityType.PASSIVE and any(
            "roleblock" in v.tags for v in visit.actor.get_visitors(game) if v.is_active(game)
        ):
            return VisitStatus.PENDING
        # Wait if the target has a pending rolestop.
        if visit.ability_type is not AbilityType.PASSIVE and any(
            "rolestop" in v.tags
            for t in visit.targets
            for v in t.get_visitors(game)
            if v.is_active(game)
        ):
            return VisitStatus.PENDING
        # Wait if the target has a pending juggernaut (and the visit roleblocks).
        if "roleblock" in visit.tags and any(
            "juggernaut" in v.tags
            for t in visit.targets
            for v in t.get_visitors(game)
            if v.is_active(game)
        ):
            return VisitStatus.PENDING
        # Perform the visit.
        return self.do_visit(game, visit)

    def resolve_game(self, game: Game) -> None:
        """Resolve all visits in the game."""
        for visit in game.visits:
            if visit.ability_type is not AbilityType.PASSIVE and visit.is_active(game):
                visit.actor.uses.setdefault(visit.ability, 0)
                visit.actor.uses[visit.ability] += 1
                visit.actor.action_history.append(replace(visit))
        for visit in game.visits:
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
                if not visit.is_active(game):
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
        for visit in game.visits:
            if (
                "investigate" in visit.tags
                and visit.is_active_time(game)
                and visit.status == VisitStatus.FAILURE
            ):
                visit.actor.private_messages.send(
                    visit.ability.id, "Your ability failed, and you did not recieve a result."
                )

    def resolve_cycles(self, game: Game) -> bool:
        successfully_resolved: bool = False

        # Check for mutual roleblocks and invoke the Catastrophic Rule.
        roleblocking_visits: list[tuple[Player, Player]] = []
        for visit in game.visits:
            if visit.is_active(game) and "roleblock" in visit.tags:
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
                    visit = Visit(
                        actor=player, ability=ability, ability_type=AbilityType.PASSIVE, game=game
                    )
                    if ability.immediate:
                        self.resolve_visit(game, visit)
                    else:
                        game.visits.append(visit)

    def make_visit(
        self,
        game: Game,
        actor: Player,
        targets: tuple[Player, ...] | None,
        ability_type: AbilityType,
        ability_idx: int,
        tags: frozenset[str] | Collection[str] = frozenset(),
        *,
        player_inputs: tuple[object, ...] = (),
    ) -> Visit:
        ability = (
            actor.actions[ability_idx]
            if ability_type is AbilityType.ACTION
            else actor.passives[ability_idx]
            if ability_type is AbilityType.PASSIVE
            else actor.shared_actions[ability_idx]
            if ability_type is AbilityType.SHARED_ACTION
            else None
        )
        if ability is None:
            if not isinstance(ability_type, AbilityType):
                raise TypeError(f"Expected AbilityType, got {type(ability_type)}.")
            else:
                raise ValueError(f"Unsupported value {ability_type}.")
        return Visit(
            actor,
            targets,  # type: ignore[arg-type]
            ability_type=ability_type,
            ability=ability,
            game=game,
            tags=frozenset(tags),
            player_inputs=tuple(player_inputs),
        )

    def check_lazy_allowed(self, game: Game) -> bool:
        self.lazy_allowed = sum(bool("town" not in p.alignment.tags) for p in game.players) > 1
        return self.lazy_allowed


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

    def check(self, game: Game, actor: Player, targets: Sequence[Player] | None = None) -> bool:
        return (
            super().check(game, actor, targets)
            and (
                targets is None
                or all(t not in actor.known_players
                       or t.alignment.id != actor.alignment.id
                       for t in targets)
            )
        )

    def perform(
        self, game: Game, actor: Player, targets: Sequence[Player] | None = None, *, visit: Visit
    ) -> VisitStatus:
        if targets is None:
            targets = tuple(actor for _ in range(self.target_count))
        target, *_ = targets
        if "unstoppable" not in visit.tags and any(
            "protect" in v.tags for v in target.get_visitors(game) if v.is_active(game)
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
            if t.is_active(game)
            for v in t.actor.get_visitors(game)
            if v.is_active(game)
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
                v.is_active(game)
                and "unstoppable" not in v.tags
                and self.block_check(actor, target, v, visit=visit)
                and Personal.can_interact(visit, v)
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
        if any("macho" in v.tags for v in target.get_visitors(game) if v.is_active(game)):
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
        """You may target another player to protect them from a single nightkill on that night. If you successfully protect another player, you will die in their place."""
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
        """Any killing actions that target you will fail."""
        limit = None

    passives = (Bulletproof(),)
    is_adjective: bool = True


class Cop(Role):
    """Checks if a player is aligned with the Town."""

    class Cop(InvestigativeAbility):
        """You may investigate another player to learn if they are Town or Not Town. If your action fails, you will receive 'No Result.'"""
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
        """You may target another player to protect them from a single nightkill on that night."""
        tags = frozenset({"protect", "mafia_no_gun"})
        limit = 1

    actions = (Doctor(),)


class Friendly_Neighbor(Role):
    """Informs a player of the actor's alignment."""

    class Friendly_Neighbor(Ability):
        """You may target another player to inform them that you are aligned with the Town."""
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
        """You may investigate another player to learn whether or not they have a gun. If your action fails, you will receive 'No Result.'. You can find an overview of which roles do and do not have guns [here](https://wiki.mafiascum.net/index.php?title=Gunsmith#Normal_version)."""
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
            roleblock_result = roleblock_player(game, target, visit=visit)
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
                if (
                    "factional_kill" in v.tags
                    and v.is_active(game)
                    and Personal.can_interact(
                        visit, v
                    )  # Personal makes Juggernaut useless but just in case it's used for some reason.
                ):
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
                and (targets is None or (all(t.is_alive for t in targets) and actor in targets))
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
        chat: Chat
        if self.id not in game.chats:
            chat = PrivateChat(participants={player})
            game.chats[self.id] = chat
        elif isinstance(chat := game.chats[self.id], PrivateChat):
            chat.participants.add(player)
        else:
            raise TypeError(f"Expected PrivateChat, got {type(chat)}.")
        chat.send(
            self.id, f"{player.name} is a {player.role_name}."
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
            chat: Chat
            if chat_id not in game.chats:
                chat = PrivateChat(participants={actor, target})
                game.chats[chat_id] = chat
            elif isinstance(chat := game.chats[chat_id], PrivateChat):
                chat.participants.add(target)
            else:
                raise TypeError(f"Expected PrivateChat, got {type(chat)}.")
            chat.send(
                self.id, f"{target.name} has been added into the neighborhood."
            )
            return VisitStatus.SUCCESS

    def player_init(self, game: Game, player: Player) -> None:
        chat_id = f"{self.id}:{player.name}"
        game.chats[chat_id] = PrivateChat(participants={player})
        game.chats[chat_id].send(self.id, f"{player.name} is a {self.id}.")
        # Hide full identity of Neighborizer.

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
            return roleblock_player(game, target, visit=visit)

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
            # Wait if target has a pending roleblock.
            if any("roleblock" in v.tags for v in target.get_visitors(game) if v.is_active(game)):
                return VisitStatus.PENDING
            return super().perform(game, actor, targets, visit=visit)

        def get_message(self, game: Game, actor: Player, target: Player, *, visit: Visit) -> str:
            visits: list[Player] = []
            for v in target.get_visits(game):
                if (
                    visit_is_visible(v, game)
                    and v is not visit
                    and Personal.can_interact(visit, v)
                ):
                    visits.extend(v.targets)

            if visits:
                return f"{target.name} targeted {', '.join(p.name for p in visits)}!"
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
            # Check if target's visitors have a pending roleblock.
            if any(
                "roleblock" in vv.tags
                for v in target.get_visitors(game)
                if v.is_active(game)
                for vv in v.actor.get_visitors(game)
                if vv.is_active(game)
            ):
                return VisitStatus.PENDING
            return super().perform(game, actor, targets, visit=visit)

        def get_message(self, game: Game, actor: Player, target: Player, *, visit: Visit) -> str:
            visits: list[Player] = []
            for v in target.get_visitors(game):
                if (
                    visit_is_visible(v, game)
                    and v is not visit
                    and Personal.can_interact(visit, v)
                ):
                    visits.append(v.actor)
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
            roleblock_result = roleblock_player(game, target, visit=visit)
            rolestop_result = super().perform(game, actor, targets, visit=visit)
            return (
                VisitStatus.SUCCESS if roleblock_result or rolestop_result else VisitStatus.FAILURE
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
            success = VisitStatus.FAILURE
            for v in target.get_visitors(game):
                if v.is_active(game):
                    v.status = VisitStatus.FAILURE
                    success = VisitStatus.SUCCESS
            for v in target.get_visits(game):
                if v is not visit and v.is_active(game):
                    v.status = VisitStatus.FAILURE
            return success

        def check(
            self, game: Game, actor: Player, targets: Sequence[Player] | None = None
        ) -> bool:
            # Commuter can only target self.
            return (
                (self.phase is None or self.phase == game.phase)
                and actor.is_alive
                and (targets is None or (all(t.is_alive for t in targets) and actor in targets))
            )

    actions = (Commuter(),)


class Companion(Role):
    """Is informed that another player is Town."""

    class Companion(Ability):
        tags = frozenset({"inform"})
        immediate = True
        target_count = 0

        def __init__(
            self,
            informed_player: Player | None = None,
            id: str | None = None,
            tags: frozenset[str] | None = None,
        ):
            self.informed_player = informed_player
            super().__init__(id, tags)

        def perform(
            self,
            game: Game,
            actor: Player,
            targets: Sequence[Player] | None = None,
            *,
            visit: Visit,
        ) -> VisitStatus:
            if self.informed_player is None:
                raise TypeError("Companion has no informed player.")
            message: str = f"{self.informed_player.name} is aligned with the Town."
            actor.private_messages.send(self.id, message)
            return VisitStatus.SUCCESS

        def check(
            self, game: Game, actor: Player, targets: Sequence[Player] | None = None
        ) -> bool:
            # Companion can only be used once.
            return super().check(game, actor, targets) and actor.uses.get(self, 0) == 0

    @property
    def informed_player(self) -> Player | None:
        for action in self.actions:
            if isinstance(action, Companion.Companion):
                return action.informed_player
        return None

    @informed_player.setter
    def informed_player(self, value: Player | None) -> None:
        for action in self.actions:
            if isinstance(action, Companion.Companion):
                action.informed_player = value
    
    @informed_player.deleter
    def informed_player(self) -> None:
        for action in self.actions:
            if isinstance(action, Companion.Companion):
                action.informed_player = None

    def __init__(
        self,
        id: str | None = None,
        actions: tuple[Ability, ...] | None = None,
        passives: tuple[Ability, ...] | None = None,
        shared_actions: tuple[Ability, ...] | None = None,
        tags: frozenset[str] | None = None,
        is_adjective: bool | None = None,
        informed_player: Player | None = None,
    ):
        super().__init__(id, actions, passives, shared_actions, tags, is_adjective)
        self.actions = (Companion.Companion(informed_player),)


class Detective(Role):
    """Checks if a player attempted to kill someone."""

    class Detective(InvestigativeAbility):
        tags = frozenset({"investigate", "gun"})

        def get_message(self, game: Game, actor: Player, target: Player, *, visit: Visit) -> str:
            if any(
                "kill" in v.tags
                for v in target.get_visits(game)
                if v.ability_type is not AbilityType.PASSIVE and Personal.can_interact(visit, v)
            ):
                return f"{target.name} has tried to kill someone!"
            else:
                return f"{target.name} has not tried to kill anyone."

    actions = (Detective(),)


class Fruit_Vendor(Role):
    """Tells a player that they were given fruit, but not who gave it to them."""

    class Fruit_Vendor(Ability):
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

    class Hider(Ability):
        class Protect_Self(ProtectiveAbility):
            id = "Hider"

            def block_check(
                self, actor: Player, target: Player, checked_visit: Visit, *, visit: Visit
            ) -> bool:
                return (
                    super().block_check(actor, target, checked_visit, visit=visit)
                    and checked_visit.ability_type is not AbilityType.PASSIVE
                )

        class Lifelink(Ability):
            id = "Hider"

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
                    if v.is_active(game) and v.ability_type is not AbilityType.PASSIVE
                ):
                    return VisitStatus.PENDING
                return VisitStatus.SUCCESS

        tags = frozenset("simultaneous")

        def __init__(self, id: str | None = None, tags: frozenset[str] | None = None):
            super().__init__(id, tags)
            self.abilities: list[Ability] = [
                self.Protect_Self(self.id, self.Protect_Self.tags | {"hidden"}),
                self.Lifelink(self.id, self.Lifelink.tags | {"hidden"}),
            ]

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
            visit_targets: list[tuple[Player, ...]] = [(actor,), tuple(targets)]
            visit_types: list[AbilityType] = [AbilityType.PASSIVE, AbilityType.ACTION]
            for ability, a_targets, a_type in zip(self.abilities, visit_targets, visit_types):
                visit = Visit(
                    actor=actor, targets=a_targets, ability=ability, ability_type=a_type, game=game
                )
                game.visits.append(visit)
            return VisitStatus.SUCCESS

    actions = (Hider(),)


def Jack_of_All_Trades(
    roles: tuple[type[Role], ...] | None = None,
    id: str | None = None,
    tags: frozenset[str] | None = None,
) -> type[Role]:
    """Has multiple pre-determined 1-Shot roles."""
    
    oneshot = XShot(1)

    if roles is None:
        roles = (Cop, Vigilante, Doctor, Roleblocker)
    _roles = (oneshot(r) for r in roles)

    if id is None:
        id = "Jack of All Trades"
    
    _id = id + " " + " ".join(r.id for r in roles)

    if tags is None:
        tags = frozenset().union(*(r.tags for r in roles))

    new_role = Role.combine(*_roles)
    new_role.id = _id
    new_role.tags = tags
    return new_role


class Medical_Student(Role):
    """Protects a Vanilla player from one kill."""

    class Medical_Student(Doctor.Doctor):
        tags = frozenset({"protect", "mafia_no_gun"})

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
            if target.role.is_role(Vanilla):
                return super().perform(game, actor, targets, visit=visit)
            return VisitStatus.FAILURE

    actions = (Medical_Student(),)


class Messenger(Role):
    """Sends a custom message to a player."""

    class Messenger(Ability):
        tags = frozenset({"message"})
        player_inputs_types = (str,)

        def perform(
            self,
            game: Game,
            actor: Player,
            targets: Sequence[Player] | None = None,
            *,
            visit: Visit,
        ) -> int:
            if not isinstance(visit.player_inputs[0], str):
                raise TypeError("Expected string message.")
            if targets is None:
                targets = tuple(actor for _ in range(self.target_count))
            target, *_ = targets
            target.private_messages.send(self.id, visit.player_inputs[0])
            return VisitStatus.SUCCESS

    actions = (Messenger(),)


class Motion_Detector(Role):
    """Checks if a player targeted someone or was targeted by someone.
    Receives the same result from both checks.
    """

    class Motion_Detector(InvestigativeAbility):
        tags = frozenset({"investigate", "gun"})

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
            # Wait if target has a pending roleblock.
            if any("roleblock" in v.tags for v in target.get_visitors(game) if v.is_active(game)):
                return VisitStatus.PENDING
            # Wait if target's visitors have a pending roleblock.
            if any(
                "roleblock" in vv.tags
                for v in target.get_visitors(game)
                if v.is_active(game)
                for vv in v.actor.get_visitors(game)
                if vv.is_active(game)
            ):
                return VisitStatus.PENDING
            return super().perform(game, actor, targets, visit=visit)

        def get_message(self, game: Game, actor: Player, target: Player, *, visit: Visit) -> str:
            # Check if target visited someone.
            visited = any(
                visit_is_visible(v, game) and v is not visit and Personal.can_interact(visit, v)
                for v in target.get_visits(game)
            )
            # Check if target was visited by someone.
            was_visited = any(
                visit_is_visible(v, game) and v is not visit and Personal.can_interact(visit, v)
                for v in target.get_visitors(game)
            )
            if visited or was_visited:
                return f"{target.name} targeted someone or was targeted by someone."
            else:
                return f"{target.name} did not target anyone and was not targeted by anyone."

    actions = (Motion_Detector(),)


class Neighbor(Role):
    """Can chat with other Neighbors."""

    def player_init(self, game: Game, player: Player) -> None:
        chat_id = f"{self.id}"
        if chat_id not in game.chats:
            game.chats[chat_id] = PrivateChat(participants={player})
        elif isinstance(chat := game.chats[chat_id], PrivateChat):
            chat.participants.add(player)
        else:
            raise TypeError(f"Expected PrivateChat, got {type(chat)}.")
        game.chats[chat_id].send(self.id, f"{player.name} is a {self.id}.")
        # Hide full identity of Neighbors.

    tags = frozenset({"chat"})


class Ninja(Role):
    """If the actor performs the factional kill, it cannot be detected."""

    class Ninja(Ability):
        tags = frozenset({"ninja", "unstoppable"})

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
            successes: int = 0
            for v in target.get_visits(game):
                if (
                    "factional_kill" in v.tags
                    and v.is_active(game)
                    and Personal.can_interact(visit, v)
                ):
                    v.tags |= frozenset({"hidden"})
                    successes += 1
            return successes

        def check(
            self, game: Game, actor: Player, targets: Sequence[Player] | None = None
        ) -> bool:
            # Ninja can only target self.
            return (
                (self.phase is None or self.phase == game.phase)
                and actor.is_alive
                and (targets is None or all(t.is_alive for t in targets) and actor in targets)
            )

    actions = (Ninja(),)


class PT_Cop(Role):
    """Check if a player is in a Private Chat."""

    class PT_Cop(InvestigativeAbility):
        tags = frozenset({"investigate", "gun"})

        def get_message(self, game: Game, actor: Player, target: Player, *, visit: Visit) -> str:
            if any(
                target in chat.participants
                for id, chat in game.chats.items()
                if isinstance(chat, PrivateChat)
                and ("personal" not in visit.tags or not id.startswith("faction:"))
            ):
                return f"{target.name} is in a Private Chat!"
            else:
                return f"{target.name} is not in a Private Chat."

    actions = (PT_Cop(),)


class Reporter(Role):
    """Learns if a player targeted someone this night."""

    class Reporter(InvestigativeAbility):
        tags = frozenset({"investigate", "gun"})

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
            # Wait if target has a pending roleblock.
            if any("roleblock" in v.tags for v in target.get_visitors(game) if v.is_active(game)):
                return VisitStatus.PENDING
            return super().perform(game, actor, targets, visit=visit)

        def get_message(self, game: Game, actor: Player, target: Player, *, visit: Visit) -> str:
            if any(
                visit_is_visible(v, game) and v is not visit and Personal.can_interact(visit, v)
                for v in target.get_visits(game)
            ):
                return f"{target.name} targeted someone this night!"
            else:
                return f"{target.name} did not target anyone this night."

    actions = (Reporter(),)


class Rolestopper(Role):
    """Blocks actions used on a player."""

    Rolestopper = Rolestop
    actions = (Rolestopper(),)


class Role_Watcher(Role):
    """Checks a player to learn all roles that targeted them."""

    class Role_Watcher(InvestigativeAbility):
        tags = frozenset({"investigate", "gun"})

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
            # Check if target's visitors have a pending roleblock.
            if any(
                "roleblock" in vv.tags
                for v in target.get_visitors(game)
                if v.is_active(game)
                for vv in v.actor.get_visitors(game)
                if vv.is_active(game)
            ):
                return VisitStatus.PENDING
            return super().perform(game, actor, targets, visit=visit)

        def get_message(self, game: Game, actor: Player, target: Player, *, visit: Visit) -> str:
            roles: list[str] = []
            for v in target.get_visitors(game):
                if (
                    visit_is_visible(v, game)
                    and v is not visit
                    and Personal.can_interact(visit, v)
                ):
                    roles.append(v.actor.role.id)
            if roles:
                return f"{target.name} was targeted by the following roles: {', '.join(roles)}."
            else:
                return f"{target.name} was not targeted by anyone."

    actions = (Role_Watcher(),)


class Shield(Role):
    """If the target performs a kill, the actor dies instead of the intended target."""

    class Shield(ProtectiveAbility):
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
            # Check if a visitor to the target has a pending juggernaut.
            if any(
                "juggernaut" in v.tags
                for v in target.get_visitors(game)
                if v.is_active(game) and Personal.can_interact(visit, v)
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
            for v in target.get_visits(game):
                if (
                    v.is_active(game)
                    and "unstoppable" not in v.tags
                    and self.block_check(actor, target, v, visit=visit)
                ):
                    if self.block_visit(actor, target, v, visit=visit) >= VisitStatus.SUCCESS:
                        successes += 1
                    if max_blocks is not None and max_blocks <= successes:
                        if successes:
                            actor.kill(self.id)
                        return successes
            if successes:
                actor.kill(self.id)
            return successes

        limit: int | None = None

    actions = (Shield(),)


class Traffic_Analyst(Role):
    """Check if a player can communicate with other players privately.
    This does not include chats with only 1 remaining living player.
    """

    class Traffic_Analyst(InvestigativeAbility):
        tags = frozenset({"investigate", "gun"})

        def perform(
            self,
            game: Game,
            actor: Player,
            targets: Sequence[Player] | None = None,
            *,
            visit: Visit,
        ) -> VisitStatus:
            # Wait if kill abilities are still pending, might affect result.
            for v in game.visits:
                if v.is_active(game) and "kill" in v.tags:
                    return VisitStatus.PENDING
            return super().perform(game, actor, targets, visit=visit)

        def get_message(self, game: Game, actor: Player, target: Player, *, visit: Visit) -> str:
            has_private_chat = any(
                target in chat.participants and len({p for p in chat.participants if p.is_alive}) > 1
                for id, chat in game.chats.items()
                if isinstance(chat, PrivateChat)
                and ("personal" not in visit.tags or not id.startswith("faction:"))
            )
            # Check if "message" is an ability tag (for Messenger)
            can_message_privately = any(
                "message" in a.tags
                for a in [*target.actions, *target.shared_actions]
                # Check if ability is actually usable (i.e. blocked by X-Shot)
                if has_valid_targets(a, game, target)
                and ("personal" not in visit.tags or "factional" not in a.tags)
            ) or any(
                "message" in p.tags
                for p in target.passives
                # Check if ability is actually usable (i.e. blocked by X-Shot)
                if has_valid_targets(p, game, target, True)
                and ("personal" not in visit.tags or "factional" not in p.tags)
            )
            if has_private_chat or can_message_privately:
                return f"{target.name} can communicate with other players privately!"
            else:
                return f"{target.name} cannot communicate with other players privately."

    actions = (Traffic_Analyst(),)


class Universal_Backup(Role):
    """Inherits the role of the first allied Non-Vanilla player to die."""

    class Universal_Backup(Ability):
        phase = None
        immediate = True
        target_count = 0

        def perform(
            self,
            game: Game,
            actor: Player,
            targets: Sequence[Player] | None = None,
            *,
            visit: Visit,
        ) -> int:
            dead_players = sorted(
                (p for p in game.players if p.death_causes and p.alignment is actor.alignment),
                key=lambda p: ("Mafia Factional Kill" in p.death_causes),
            )
            if not dead_players:
                return VisitStatus.FAILURE
            # Remove this ability.
            try:
                actor.actions.remove(self)
            except ValueError:
                try:
                    actor.passives.remove(self)
                except ValueError:
                    try:
                        actor.shared_actions.remove(self)
                    except ValueError:
                        pass
            # Gain abilities of dead player's role:
            dead_player = dead_players[0]
            actor.actions.extend(dead_player.role.actions)
            actor.passives.extend(dead_player.role.passives)
            actor.shared_actions.extend(dead_player.role.shared_actions)
            for action in dead_player.role.actions:
                actor.uses[action] = actor.uses.get(action, 0) + dead_player.uses.get(action, 0)
            for passive in dead_player.role.passives:
                actor.uses[passive] = actor.uses.get(passive, 0) + dead_player.uses.get(passive, 0)
            for shared_action in dead_player.role.shared_actions:
                actor.uses[shared_action] = actor.uses.get(
                    shared_action, 0
                ) + dead_player.uses.get(shared_action, 0)
            return VisitStatus.SUCCESS

        def check(
            self, game: Game, actor: Player, targets: Sequence[Player] | None = None
        ) -> bool:
            return (self.phase is None or game.phase == self.phase) and actor.is_alive

    passives = (Universal_Backup(),)


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
        if issubclass(ability, XShot.XShotPrototype):
            raise TypeError(f"{ability} is already X-Shot.")

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
                id=ability.id,
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


class Activated(Modifier):
    """Turns passives into actions, requiring the ability to be "activated"."""

    T = TypeVar("T", Role, Alignment)

    def modify(self, cls: type[T], cls_dict: dict[str, Any] | None = None) -> type[T]:
        if cls_dict is None:
            cls_dict = {
                "id": f"{self.id} {cls.id}" if issubclass(cls, Role) else cls.id,
                "actions": cls.actions + cls.passives,
                "passives": (),
                "shared_actions": cls.shared_actions,
                "tags": cls.tags | self.tags,
            }
        return type(
            f"{self!r}({cls.__name__})",
            (cls,),
            cls_dict,
        )

    def modify_role(self, role: type[Role], *args: Any, **kwargs: Any) -> type[Role]:
        return self.modify(role)

    def modify_alignment(
        self, alignment: type[Alignment], *args: Any, **kwargs: Any
    ) -> type[Alignment]:
        return self.modify(alignment)


class Disloyal(AbilityModifier):
    """Actions only succeed if used on non-allied players."""

    def modify_ability(self, ability: type[Ability]) -> type[Ability]:
        def perform(
            method_self: Ability,
            game: Game,
            actor: Player,
            targets: Sequence[Player] | None = None,
            *,
            visit: Visit,
        ) -> int:
            if targets is None:
                targets = tuple(actor for _ in range(method_self.target_count))
            target, *_ = targets
            if actor.alignment is target.alignment:
                return VisitStatus.FAILURE
            return ability.perform(method_self, game, actor, targets, visit=visit)

        return type(
            f"{self!r}({ability.__name__})",
            (ability,),
            dict(
                id=ability.id,
                tags=ability.tags | self.tags,
                perform=perform,
            ),
        )


class Loyal(AbilityModifier):
    """Actions only succeed if used on allied players."""

    def modify_ability(self, ability: type[Ability]) -> type[Ability]:
        def perform(
            method_self: Ability,
            game: Game,
            actor: Player,
            targets: Sequence[Player] | None = None,
            *,
            visit: Visit,
        ) -> int:
            if targets is None:
                targets = tuple(actor for _ in range(method_self.target_count))
            target, *_ = targets
            if actor.alignment is not target.alignment:
                return VisitStatus.FAILURE
            return ability.perform(method_self, game, actor, targets, visit=visit)

        return type(
            f"{self!r}({ability.__name__})",
            (ability,),
            dict(
                id=ability.id,
                tags=ability.tags | self.tags,
                perform=perform,
            ),
        )


class Indecisive(AbilityModifier):
    """Cannot target the same person two times in a row."""

    def modify_ability(self, ability: type[Ability]) -> type[Ability]:
        def check(
            method_self: Ability,
            game: Game,
            actor: Player,
            targets: Sequence[Player] | None = None,
        ) -> bool:
            if targets is None:
                targets = tuple(actor for _ in range(method_self.target_count))
            for v in actor.action_history:
                if (
                    method_self is v.ability
                    and game.day_no <= v.day_no + 1
                    and any(a is b for a, b in zip(targets, v.targets))
                ):
                    return False
            return ability.check(method_self, game, actor, targets)

        return type(
            f"{self!r}({ability.__name__})",
            (ability,),
            dict(
                id=ability.id,
                tags=ability.tags | self.tags,
                check=check,
            ),
        )


class Non_Consecutive_Night(AbilityModifier):
    """Cannot use the ability on consecutive nights."""

    id = "Non-Consecutive Night"

    def modify_ability(self, ability: type[Ability]) -> type[Ability]:
        def check(
            method_self: Ability,
            game: Game,
            actor: Player,
            targets: Sequence[Player] | None = None,
        ) -> bool:
            for v in actor.action_history:
                if method_self is v.ability and game.day_no <= v.day_no + 1:
                    return False
            return ability.check(method_self, game, actor, targets)

        return type(
            f"{self!r}({ability.__name__})",
            (ability,),
            dict(
                id=ability.id,
                tags=ability.tags | self.tags,
                check=check,
            ),
        )


class Lazy(AbilityModifier):
    """Ability fails if there is only 1 anti-town player left at the start of the phase.
    Modifier does not check: use Resolver.check_lazy_allowed() before resolving the game.
    """

    tags = frozenset({"lazy"})


class Weak(AbilityModifier):
    """Dies if targets an anti-town player."""

    def modify_ability(self, ability: type[Ability]) -> type[Ability]:
        def perform(
            method_self: Ability,
            game: Game,
            actor: Player,
            targets: Sequence[Player] | None = None,
            *,
            visit: Visit,
        ) -> int:
            if targets is not None and any("town" not in t.alignment.tags for t in targets):
                actor.kill(self.id)
            return ability.perform(method_self, game, actor, targets, visit=visit)

        return type(
            f"{self!r}({ability.__name__})",
            (ability,),
            dict(
                id=ability.id,
                tags=ability.tags | self.tags,
                perform=perform,
            ),
        )


class Personal(AbilityModifier):
    """Cannot interact with factional abilities.
    Does not check: implement in ability.
    """

    tags = frozenset({"personal"})

    @staticmethod
    def can_interact(visit: Visit, affected_visit: Visit) -> bool:
        return "personal" not in visit.tags or "factional" not in affected_visit.tags


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
        chat_id = f"faction:{self.id}"
        chat: Chat
        if chat_id not in game.chats:
            chat = PrivateChat(participants={player})
            game.chats[chat_id] = chat
        elif isinstance(chat := game.chats[chat_id], PrivateChat):
            chat.participants.add(player)
        else:
            raise TypeError(f"Expected PrivateChat, got {type(chat)}.")
        chat.send(
            self.id, f"{player.name} is a {player.role_name}."
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


ROLES: dict[str, type[Role]] = {
    v.id: v
    for v in vars().values()
    if isinstance(v, type)
    and issubclass(v, Role)
    and v is not Role
}

ALIGNMENTS: dict[str, type[Alignment]] = {
    v.id: v
    for v in vars().values()
    if isinstance(v, type)
    and issubclass(v, Alignment)
    and v is not Alignment
    and v is not Faction
}
