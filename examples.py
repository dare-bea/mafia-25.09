"""
Simple Normal roles, abilities, and alignments.
"""

from abc import ABC, abstractmethod
from typing import TypeVar, cast
from mafia import AbilityModifier, AbilityType, Alignment, Chat, Faction, Role, Ability, Game, Player, Visit, VisitStatus, role_name
from collections.abc import Sequence, Callable
from nodes import nodes_in_cycles

def roleblock_player(game: Game, player: Player) -> None:
    """Roleblocks a player."""
    for visit in player.get_visits(game):
        if visit.ability_type is not AbilityType.PASSIVE and 'juggernaut' not in visit.tags:
            visit.status = VisitStatus.FAILURE

class Resolver:
    def resolve_visit(self, game: Game, visit: Visit) -> int:
        """Resolve a visit and return the result. If the visit cannot be resolved, return VisitStatus.PENDING."""
        # Check if the ability is immediate. If so, perform the visit.
        if visit.ability.immediate:
            status = visit.perform(game)
            visit.status = status
            return status
        # Check if the actor has a pending roleblock.
        if (visit.ability_type is not AbilityType.PASSIVE
            and any('roleblock' in v.tags and v.status == VisitStatus.PENDING
                    for v in visit.actor.get_visitors(game))
        ):
            return VisitStatus.PENDING
        # Perform the visit.
        status = visit.perform(game)
        visit.status = status
        if visit.ability_type is AbilityType.PASSIVE and status != VisitStatus.PENDING:
            visit.actor.uses.setdefault(visit.ability, 0)
            visit.actor.uses[visit.ability] += status
        return status

    def resolve_game(self, game: Game) -> None:
        """Resolve all visits in the game."""
        for visit in game.visits:
            if (visit.ability_type is not AbilityType.PASSIVE
                and visit.status == VisitStatus.PENDING):
                visit.actor.uses.setdefault(visit.ability, 0)
                visit.actor.uses[visit.ability] += 1
        failed_to_resolve: bool = True
        while failed_to_resolve:
            failed_to_resolve = False
            successfully_resolved: bool = False
            for visit in game.visits:
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
            if visit.status == VisitStatus.PENDING and 'roleblock' in visit.tags:
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
    def __init__(self, id: str | None = None, killer: str | None = None, tags: frozenset[str] | None = None):
        super().__init__(id, tags)
        if killer is not None:
            self.killer = killer
    
    def __init_subclass__(cls):
        super().__init_subclass__()
        if 'killer' not in cls.__dict__:
            cls.killer = cls.__name__.replace('_', ' ')

    tags = frozenset({'kill'})
    killer: str
    
    def perform(self, game: Game, actor: Player, targets: Sequence[Player] | None = None, *, visit: Visit) -> VisitStatus:
        if targets is None:
            targets = tuple(actor for _ in range(self.target_count))
        target, *_ = targets
        if 'juggernaut' not in visit.tags and any('protect' in v.tags and v.status == VisitStatus.PENDING
               for v in target.get_visitors(game)):
            return VisitStatus.PENDING
        target.kill(self.killer)
        return VisitStatus.SUCCESS

class InvestigativeAbility(Ability, ABC):
    """Investigates someone and learns the result."""
    tags = frozenset({'investigate'})
    def perform(self, game: Game, actor: Player, targets: Sequence[Player] | None = None, *, visit: Visit) -> VisitStatus:
        if targets is None:
            targets = tuple(actor for _ in range(self.target_count))
        target, *_ = targets
        message: str = self.get_message(game, actor, target, visit=visit)
        actor.private_messages.send(self.id, message)
        return VisitStatus.SUCCESS

    @abstractmethod
    def get_message(self, game: Game, actor: Player, target: Player, *, visit: Visit) -> str:
        ...

class Rolestop(Ability):
    """Protects a player from a kill."""
    tags = frozenset({'rolestop'})

    def perform(self, game: Game, actor: Player, targets: Sequence[Player] | None = None, *, visit: Visit) -> int:
        if targets is None:
            targets = tuple(actor for _ in range(self.target_count))
        target, *_ = targets
        max_protects: int | None
        if visit.ability_type is AbilityType.PASSIVE and hasattr(visit.ability, 'max_uses'):
            uses_remaining = cast(XShot.XShotPrototype, visit.ability).max_uses - actor.uses.get(visit.ability, 0)
            max_protects = min(self.limit, uses_remaining) if self.limit is not None else uses_remaining
        else:
            max_protects = self.limit
        successes: int = VisitStatus.FAILURE
        for v in target.get_visitors(game):
            if (v.status == VisitStatus.PENDING
                and 'juggernaut' not in v.tags
                and self.block_check(actor, target, v, visit=visit)):
                successes += self.block_visit(actor, target, v, visit=visit)
                if max_protects is not None and max_protects <= successes:
                    return successes
        return successes
    
    def block_visit(self, actor: Player, target: Player, blocked_visit: Visit, *, visit: Visit) -> VisitStatus:
        blocked_visit.status = VisitStatus.FAILURE
        return VisitStatus.SUCCESS
    
    def block_check(self, actor: Player, target: Player, checked_visit: Visit, *, visit: Visit) -> bool:
        return True

    limit: int | None = None

class ProtectiveAbility(Rolestop):
    tags = frozenset({'protect'})

    def perform(self, game: Game, actor: Player, targets: Sequence[Player] | None = None, *, visit: Visit) -> int:
        if targets is None:
            targets = tuple(actor for _ in range(self.target_count))
        target, *_ = targets
        if any('macho' in v.tags and v.status == VisitStatus.PENDING
                for v in target.get_visitors(game)):
            return VisitStatus.PENDING
        return super().perform(game, actor, targets, visit=visit)

    def block_check(self, actor: Player, target: Player, checked_visit: Visit, *, visit: Visit) -> bool:
        return 'kill' in checked_visit.tags

# ROLES #

class Vanilla(Role):
    """No abilities."""
    is_adjective: bool = True

class Bodyguard(Role):
    """Protects a player from one kill, but dies if successful."""
    class Bodyguard(ProtectiveAbility):
        def block_kill(self, actor: Player, target: Player, kill_visit: Visit, *, visit: Visit) -> VisitStatus:
            actor.kill(getattr(visit.ability, 'killer', 'Unknown'))
            return super().block_visit(actor, target, kill_visit, visit=visit)
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
        tags = frozenset({'investigate', 'gun'})
        def get_message(self, game: Game, actor: Player, target: Player, *, visit: Visit) -> str:
            if 'town' in target.alignment.tags:
                return f"{target.name} is aligned with the Town."
            else:
                return f"{target.name} is not aligned with the Town!."
    actions = (Cop(),)
    tags = frozenset({'gun'})

class Doctor(Role):
    """Protects a player from one kill."""
    class Doctor(ProtectiveAbility):
        tags = frozenset({'protect', 'mafia_no_gun'})
        limit = 1
    actions = (Doctor(),)

class Friendly_Neighbor(Role):
    """Informs a player of the actor's alignment."""
    class Friendly_Neighbor(Ability):
        tags = frozenset({'inform'})
        def perform(self, game: Game, actor: Player, targets: Sequence[Player] | None = None, *, visit: Visit) -> VisitStatus:
            if targets is None:
                targets = tuple(actor for _ in range(self.target_count))
            target, *_ = targets
            message: str = f"{actor.name} is aligned with the {actor.alignment}!"
            target.private_messages.send(self.id, message)
            return VisitStatus.SUCCESS
    actions = (Friendly_Neighbor(),)

class Gunsmith(Role):
    """Checks if a player has a gun in flavor. Mafia (except Traitors, Doctors, and Medical Students), Cops, Vigilantes, Gunsmiths, Role Cops, Vanilla Cops, PT Cops, Vengefuls, Modifier Cops, Detectives, Neapolitans, Goon Cops, Agents, Auditors, Specialists, Backups and JoATs of the aforementioned roles, Inventors that can give out the aforementioned roles, and players with inventions of the aforementioned roles have guns."""
    class Gunsmith(InvestigativeAbility):
        tags = frozenset({'investigate', 'gun'})
        def get_message(self, game: Game, actor: Player, target: Player, *, visit: Visit) -> str:
            if (
                any('gun' in a.tags for a in [
                    *target.actions, *target.passives, *target.shared_actions])
                or (
                    'mafia' in target.alignment.tags
                    and not any('mafia_no_gun' in a.tags for a in [
                        *target.actions, *target.passives,
                        *target.shared_actions]))
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
        tags = frozenset({'inform'})
        def check(self, game: Game, actor: Player, targets: Sequence[Player] | None = None) -> bool:
            return super().check(game, actor, targets)
        def perform(self, game: Game, actor: Player, targets: Sequence[Player] | None = None, *, visit: Visit) -> VisitStatus:
            message: str = f"{actor.name} is aligned with the {actor.alignment.id}!"
            game.chats['global'].send(self.id, message)
            return VisitStatus.SUCCESS
    actions = (Innocent_Child(),)

class Jailkeeper(Role):
    """Protects and roleblocks a player simultaneously."""
    class Jailkeeper(ProtectiveAbility):
        tags = frozenset({'protect', 'roleblock'})
        def perform(self, game: Game, actor: Player, targets: Sequence[Player] | None = None, *, visit: Visit) -> VisitStatus:
            if targets is None:
                targets = tuple(actor for _ in range(self.target_count))
            target, *_ = targets
            roleblock_player(game, target)
            super().perform(game, actor, targets, visit=visit)
            return VisitStatus.SUCCESS
        limit = None
    actions = (Jailkeeper(),)

class Juggernaut(Role):
    """If the actor performs the factional kill, it cannot be prevented."""
    class Juggernaut(Ability):
        def perform(self, game: Game, actor: Player, targets: Sequence[Player] | None = None, *, visit: Visit) -> VisitStatus:
            for visit in actor.get_visits(game):
                if 'factional_kill' in visit.tags and visit.status == VisitStatus.PENDING:
                    visit.tags |= frozenset({'juggernaut'})
                    return VisitStatus.SUCCESS
            return VisitStatus.FAILURE
    passives = (Juggernaut(),)
    tags = frozenset({'juggernaut'})

class Macho(Role):
    """Cannot be protected from kills."""
    class Macho(Rolestop):
        tags = frozenset({'macho'})
        def block_check(self, actor: Player, target: Player, checked_visit: Visit, *, visit: Visit) -> bool:
            return 'protect' in checked_visit.tags
    passives = (Macho(),)
    is_adjective: bool = True

class Mason(Role):
    """Can chat with other Masons."""
    def player_init(self, game: Game, player: Player) -> None:
        if self.id not in game.chats:
            game.chats[self.id] = Chat(participants={player})
        else:
            game.chats[self.id].participants.add(player)
        game.chats[self.id].send(self.id, f"{player.name} is a {role_name(player.role, player.alignment)}.")
    tags = frozenset({'chat', 'informed'})

class Neapolitan(Role):
    """Checks if a player is a Vanilla Townie."""
    class Neapolitan(InvestigativeAbility):
        tags = frozenset({'investigate', 'gun'})
        def get_message(self, game: Game, actor: Player, target: Player, *, visit: Visit) -> str:
            if target.role.id == 'Vanilla' and 'town' in target.alignment.tags:
                return f"{target.name} is a Vanilla Townie."
            else:
                return f"{target.name} is not a Vanilla Townie."
    actions = (Neapolitan(),)

class Neighborizer(Role):
    """Adds a player into a neighborhood."""
    class Neighborizer(Ability):
        def perform(self, game: Game, actor: Player, targets: Sequence[Player] | None = None, *, visit: Visit) -> VisitStatus:
            if targets is None:
                targets = tuple(actor for _ in range(self.target_count))
            target, *_ = targets
            chat_id = f"{self.id}:{actor.name}"
            if chat_id not in game.chats:
                game.chats[chat_id] = Chat(participants={actor, target})
            else:
                game.chats[chat_id].participants.add(target)
            game.chats[chat_id].send(self.id, f"{target.name} has been added into the neighborhood.")
            return VisitStatus.SUCCESS
    
    def player_init(self, game: Game, player: Player) -> None:
        chat_id = f"{self.id}:{player.name}"
        game.chats[chat_id] = Chat(participants={player})
        game.chats[chat_id].send(self.id, f"{player.name} is a {player.role.id}.")

    tags = frozenset({'chat'})
    actions = (Neighborizer(),)

class Roleblocker(Role):
    """Roleblocks a player."""
    class Roleblocker(Ability):
        tags = frozenset({'roleblock'})
        def perform(self, game: Game, actor: Player, targets: Sequence[Player] | None = None, *, visit: Visit) -> VisitStatus:
            if targets is None:
                targets = tuple(actor for _ in range(self.target_count))
            target, *_ = targets
            roleblock_player(game, target)
            return VisitStatus.SUCCESS
    actions = (Roleblocker(),)

class Rolecop(Role):
    """Checks a player to learn their role."""
    class Rolecop(InvestigativeAbility):
        tags = frozenset({'investigate', 'gun'})
        def get_message(self, game: Game, actor: Player, target: Player, *, visit: Visit) -> str:
            return f"{target.name} is a {target.role.id}."
    actions = (Rolecop(),)

class Tracker(Role):
    """Checks a player to learn who they targeted."""
    class Tracker(InvestigativeAbility):
        tags = frozenset({'investigate', 'gun'})
        def get_message(self, game: Game, actor: Player, target: Player, *, visit: Visit) -> str:
            visits: list[Player] = []
            for visit in target.get_visits(game):
                if visit.ability_type is not AbilityType.PASSIVE and 'hidden' not in visit.tags:
                    visits.extend(visit.targets)
            if visits:
                return f"{target.name} targeted {', '.join(p.name for p in visits)}."
            else:
                return f"{target.name} did not target anyone."
    actions = (Tracker(),)

class Vanilla_Cop(Role):
    """Checks if a player is Vanilla."""
    class Vanilla_Cop(InvestigativeAbility):
        tags = frozenset({'investigate', 'gun'})
        def get_message(self, game: Game, actor: Player, target: Player, *, visit: Visit) -> str:
            if target.role.id == 'Vanilla':
                return f"{target.name} is Vanilla."
            else:
                return f"{target.name} is not Vanilla."
    actions = (Vanilla_Cop(),)

class Vigilante(Role):
    """Kills a player."""
    class Vigilante(Kill):
        tags = frozenset({'kill', 'gun'})
    actions = (Vigilante(),)

class Watcher(Role):
    """Checks a player to learn who targeted them."""
    class Watcher(InvestigativeAbility):
        tags = frozenset({'investigate', 'gun'})
        def get_message(self, game: Game, actor: Player, target: Player, *, visit: Visit) -> str:
            visits: list[Player] = []
            for visit in target.get_visitors(game):
                if visit.ability_type is not AbilityType.PASSIVE and 'hidden' not in visit.tags:
                    visits.append(visit.actor)
            if visits:
                return f"{target.name} was targeted by {', '.join(p.name for p in visits)}."
            else:
                return f"{target.name} was not targeted by anyone."
    actions = (Watcher(),)

# ROLE MODIFIERS #

T_RoleAlign = TypeVar("T_RoleAlign", Role, Alignment)

class XShot(AbilityModifier):
    """Can only use their abilities X amount of times."""
    class XShotPrototype(Ability):
        max_uses: int

    def __init__(self, max_uses: int | None = None, id: str | None = None, tags: frozenset[str] | None = None):
        super().__init__(id, tags)
        if max_uses is not None:
            self.max_uses = max_uses

    
    def modify_ability(self, ability: type[Ability]) -> type[Ability]:
        def check(method_self: XShot.XShotPrototype, game: Game, actor: Player, targets: Sequence[Player] | None = None) -> bool:
            return ability.check(method_self, game, actor, targets) and actor.uses.get(method_self, 0) < method_self.max_uses
        
        return type(
            f"{self!r}({ability.__name__})",
            (ability,),
            dict(
                id = ability.id,
                max_uses = self.max_uses,
                tags = ability.tags | self.tags,
                check = check,
            )
        )
    
    @property
    def id(self):
        return f"{self.max_uses}-Shot"
    
    max_uses: int = 1

class Night_Specific(AbilityModifier):
    def __init__(self, id: str | None = None, night_check: Callable[[int], bool] | None = None, tags: frozenset[str] | None = None):
        super().__init__(id, tags)
        if night_check is not None:
            self.night_check = night_check  # type: ignore[method-assign]

    def modify_ability(self, ability: type[Ability]) -> type[Ability]:
        def check(method_self, game: Game, actor: Player, targets: Sequence[Player] | None = None) -> bool:
            return ability.check(method_self, game, actor, targets) and self.night_check(game.day_no)

        return type(
            f"{self!r}({ability.__name__})",
            (ability,),
            dict(
                tags = ability.tags | self.tags,
                check = check,
            )
        )
    
    def night_check(self, day_no: int, /) -> bool:
        raise NotImplementedError

class Novice(Night_Specific):
    def night_check(self, day_no: int, /) -> bool:
        return day_no > 1

class Odd_Night(Night_Specific):
    def night_check(self, day_no: int, /) -> bool:
        return bool(day_no % 2)

class Even_Night(Night_Specific):
    def night_check(self, day_no: int) -> bool:
        return not (day_no % 2)

# ALIGNMENTS #
    
class Town(Faction):
    """The uninformed majority."""
    tags = frozenset({'town'})
    demonym: str = "{alignment}ie"

class Mafia(Faction):
    """The informed minority."""
    class Mafia_Factional_Kill(Kill):
        tags = frozenset({'kill', 'factional_kill'})

    def player_init(self, game: Game, player: Player) -> None:
        if self.id not in game.chats:
            game.chats[self.id] = Chat(participants={player})
        else:
            game.chats[self.id].participants.add(player)
        game.chats[self.id].send(self.id, f"{player.name} is a {role_name(player.role, player.alignment)}.")
    
    shared_actions = (Mafia_Factional_Kill(),)
    tags = frozenset({'mafia', 'chat', 'informed'})
    demonym: str = "{alignment._demonym}"
    role_names: dict[str, str] = {
        "Vanilla": "{alignment} Goon",
    }

    @property
    def _demonym(self) -> str:
        if self.id.endswith('fia'):
            return f"{self.id[:1]}oso"
        else:
            return f"{self} Goon"