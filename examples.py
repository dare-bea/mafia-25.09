from abc import ABC, abstractmethod
from mafia import AbilityType, Alignment, Chat, Faction, Role, Ability, Game, Player, Visit, VisitStatus
from collections.abc import Sequence

def roleblock_player(game: Game, player: Player) -> None:
    """Roleblocks a player."""
    for visit in player.get_visits(game):
        if visit.ability_type is not AbilityType.PASSIVE and 'juggernaut' not in visit.tags:
            visit.status = VisitStatus.FAILURE

def full_role_name(role: Role, alignment: Alignment) -> str:
    return f"{alignment.id} {role.id}"

class Resolver:
    def resolve_visit(self, game: Game, visit: Visit) -> VisitStatus:
        """Resolve a visit and return the result. If the visit cannot be resolved, return VisitStatus.PENDING."""
        # Check if the ability is immediate. If so, perform the visit.
        if visit.ability.immediate:
            status = visit.perform(game)
            visit.status = status
            return status
        # Check if the actor has a pending roleblock.
        if (visit.ability_type is not AbilityType.PASSIVE
            and any('roleblock' in v.tags and v.status is VisitStatus.PENDING
                    for v in visit.actor.get_visitors(game))
        ):
            return VisitStatus.PENDING
        # Perform the visit.
        status = visit.perform(game)
        visit.status = status
        return status

    def resolve_game(self, game: Game) -> None:
        """Resolve all visits in the game."""
        failed_to_resolve: bool = True
        while failed_to_resolve:
            failed_to_resolve = False
            successfully_resolved: bool = False
            for visit in game.visits:
                if visit.status is not VisitStatus.PENDING:
                    continue
                result = self.resolve_visit(game, visit)
                if result is VisitStatus.PENDING:
                    failed_to_resolve = True
                else:
                    successfully_resolved = True
            if failed_to_resolve and not successfully_resolved:
                # TODO: Check for mutual roleblocks and invoke the Catastrophic Rule.
                raise RuntimeError("Failed to resolve game.")

class Vanilla(Role):
    pass

class Kill(Ability):
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
        if 'juggernaut' not in visit.tags and any('protect' in v.tags and v.status is VisitStatus.PENDING
               for v in target.get_visitors(game)):
            return VisitStatus.PENDING
        target.kill(self.killer)
        return VisitStatus.SUCCESS

class InvestigativeAbility(Ability, ABC):
    tags = frozenset({'investigate'})
    def perform(self, game: Game, actor: Player, targets: Sequence[Player] | None = None, *, visit: Visit) -> VisitStatus:
        if targets is None:
            targets = tuple(actor for _ in range(self.target_count))
        target, *_ = targets
        message: str = self.get_message(game, target)
        actor.private_messages.send(self.id, message)
        return VisitStatus.SUCCESS

    @staticmethod
    @abstractmethod
    def get_message(game: Game, target: Player) -> str:
        ...

class Bodyguard(Role):
    class Bodyguard(Ability):
        """Protects a player from one kill, but dies if successful."""
        tags = frozenset({'protect'})
        def perform(self, game: Game, actor: Player, targets: Sequence[Player] | None = None, *, visit: Visit) -> VisitStatus:
            if targets is None:
                targets = tuple(actor for _ in range(self.target_count))
            target, *_ = targets
            for visit in target.get_visitors(game):
                if ('kill' in visit.tags and 'juggernaut' not in visit.tags
                    and visit.status is VisitStatus.PENDING):
                    actor.kill(getattr(visit.ability, 'killer', 'Unknown'))
                    visit.status = VisitStatus.FAILURE
                    return VisitStatus.SUCCESS  # Allow only one kill to be blocked.
            return VisitStatus.FAILURE
    actions = (Bodyguard(),)

class Bulletproof(Role):
    """Blocks all kills targeting the player."""
    class Bulletproof(Ability):
        tags = frozenset({'protect'})
        def perform(self, game: Game, actor: Player, targets: Sequence[Player] | None = None, *, visit: Visit) -> VisitStatus:
            if targets is None:
                targets = tuple(actor for _ in range(self.target_count))
            target, *_ = targets
            return_result = VisitStatus.FAILURE
            for visit in target.get_visitors(game):
                if ('kill' in visit.tags and 'juggernaut' not in visit.tags
                    and visit.status is VisitStatus.PENDING):
                    visit.status = VisitStatus.FAILURE
                    return_result = VisitStatus.SUCCESS  # Allow multiple kills to be blocked.
            return return_result
    passives = (Bulletproof(),)

class Cop(Role):
    """Checks if a player is aligned with the Town."""
    class Cop(InvestigativeAbility):
        tags = frozenset({'investigate', 'gun'})
        @staticmethod
        def get_message(game: Game, target: Player) -> str:
            if 'town' in target.alignment.tags:
                return f"{target.name} is aligned with the Town."
            else:
                return f"{target.name} is not aligned with the Town!."
    actions = (Cop(),)
    tags = frozenset({'gun'})

class Doctor(Role):
    """Protects a player from one kill."""
    class Doctor(Ability):
        tags = frozenset({'protect', 'mafia_no_gun'})
        def perform(self, game: Game, actor: Player, targets: Sequence[Player] | None = None, *, visit: Visit) -> VisitStatus:
            if targets is None:
                targets = tuple(actor for _ in range(self.target_count))
            target, *_ = targets
            for visit in target.get_visitors(game):
                if ('kill' in visit.tags and 'juggernaut' not in visit.tags
                    and visit.status is VisitStatus.PENDING):
                    visit.status = VisitStatus.FAILURE
                    return VisitStatus.SUCCESS  # Allow only one kill to be blocked.
            return VisitStatus.FAILURE
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
        @staticmethod
        def get_message(game: Game, target: Player) -> str:
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
    class Jailkeeper(Ability):
        tags = frozenset({'protect', 'roleblock'})
        def perform(self, game: Game, actor: Player, targets: Sequence[Player] | None = None, *, visit: Visit) -> VisitStatus:
            if targets is None:
                targets = tuple(actor for _ in range(self.target_count))
            target, *_ = targets
            for visit in target.get_visitors(game):
                if ('kill' in visit.tags and 'juggernaut' not in visit.tags
                    and visit.status is VisitStatus.PENDING):
                    visit.status = VisitStatus.FAILURE
            roleblock_player(game, target)
            return VisitStatus.SUCCESS
    actions = (Jailkeeper(),)

class Juggernaut(Role):
    """If the actor performs the factional kill, it cannot be prevented."""
    class Juggernaut(Ability):
        def perform(self, game: Game, actor: Player, targets: Sequence[Player] | None = None, *, visit: Visit) -> VisitStatus:
            for visit in actor.get_visits(game):
                if 'factional_kill' in visit.tags and visit.status is VisitStatus.PENDING:
                    visit.tags |= frozenset({'juggernaut'})
                    return VisitStatus.SUCCESS
            return VisitStatus.FAILURE
    passives = (Juggernaut(),)
    tags = frozenset({'juggernaut'})

class Macho(Role):
    """Cannot be protected from kills."""
    class Macho(Ability):
        def perform(self, game: Game, actor: Player, targets: Sequence[Player] | None = None, *, visit: Visit) -> VisitStatus:
            for visit in actor.get_visitors(game):
                if 'protect' in visit.tags and visit.status is VisitStatus.PENDING:
                    visit.status = VisitStatus.FAILURE
                    return VisitStatus.SUCCESS
            return VisitStatus.FAILURE
    passives = (Macho(),)

class Mason(Role):
    """Can chat with other Masons."""
    def player_init(self, game: Game, player: Player) -> None:
        if self.id not in game.chats:
            game.chats[self.id] = Chat(participants={player})
        else:
            game.chats[self.id].participants.add(player)
        game.chats[self.id].send(self.id, f"{player.name} is a {full_role_name(player.role, player.alignment)}.")
    tags = frozenset({'chat', 'informed'})

class Neapolitan(Role):
    """Checks if a player is a Vanilla Townie."""
    class Neapolitan(InvestigativeAbility):
        tags = frozenset({'investigate', 'gun'})
        @staticmethod
        def get_message(game: Game, target: Player) -> str:
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
        @staticmethod
        def get_message(game: Game, target: Player) -> str:
            return f"{target.name} is a {target.role.id}."
    actions = (Rolecop(),)

class Tracker(Role):
    """Checks a player to learn who they targeted."""
    class Tracker(InvestigativeAbility):
        tags = frozenset({'investigate', 'gun'})
        @staticmethod
        def get_message(game: Game, target: Player) -> str:
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
        @staticmethod
        def get_message(game: Game, target: Player) -> str:
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
        @staticmethod
        def get_message(game: Game, target: Player) -> str:
            visits: list[Player] = []
            for visit in target.get_visitors(game):
                if visit.ability_type is not AbilityType.PASSIVE and 'hidden' not in visit.tags:
                    visits.append(visit.actor)
            if visits:
                return f"{target.name} was targeted by {', '.join(p.name for p in visits)}."
            else:
                return f"{target.name} was not targeted by anyone."

class Town(Faction):
    tags = frozenset({'town'})
    pass

class Mafia(Faction):
    class Mafia_Factional_Kill(Kill):
        tags = frozenset({'kill', 'factional_kill'})

    def player_init(self, game: Game, player: Player) -> None:
        if self.id not in game.chats:
            game.chats[self.id] = Chat(participants={player})
        else:
            game.chats[self.id].participants.add(player)
        game.chats[self.id].send(self.id, f"{player.name} is a {full_role_name(player.role, player.alignment)}.")
    
    shared_actions = (Mafia_Factional_Kill(),)
    tags = frozenset({'mafia', 'chat', 'informed'})