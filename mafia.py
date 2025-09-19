"""
Mafia game framework.
"""

from __future__ import annotations

from collections.abc import Sequence, Iterator
from enum import Enum, auto
from dataclasses import InitVar, dataclass, field
from abc import ABC, abstractmethod
from typing import cast

class VisitStatus(Enum):
    PENDING = auto()
    SUCCESS = auto()
    FAILURE = auto()
    USED = auto()

class Phase(Enum):
    DAY = auto()
    NIGHT = auto()

class WinResult(Enum):
    ONGOING = 0
    WIN = 1
    LOSE = -1

class AbilityType(Enum):
    ACTION = auto()
    PASSIVE = auto()
    SHARED_ACTION = auto()

@dataclass(eq=False)
class Visit:
    def __post_init__(self) -> None:
        if self.targets is None:
            self.targets = tuple(self.actor for _ in range(self.ability.target_count))
        self.tags = self.tags | self.ability.tags

    def __str__(self) -> str:
        targets = ', '.join(t.name for t in self.targets)
        return f"{self.actor.name}: {self.ability_type.name} {self.ability.id} -> {targets} - {self.status.name}"
    
    def __repr__(self) -> str:
        targets = ', '.join(t.name for t in self.targets)
        return f"Visit({self.actor.name}, [{targets}], {self.ability!r}, {self.ability_type!r}, {self.status!r}, {self.tags!r})"
    
    actor: Player
    targets: tuple[Player, ...] = cast(tuple, field(default=None))
    ability: Ability = field(kw_only=True)
    ability_type: AbilityType = field(kw_only=True)
    status: VisitStatus = VisitStatus.PENDING
    tags: frozenset[str] = field(default_factory=frozenset, kw_only=True)

    def perform(self, game: Game) -> VisitStatus:
        return self.ability.perform(game, self.actor, self.targets, visit=self)

class Ability(ABC):
    def __init__(
        self,
        id: str | None = None,
        tags: frozenset[str] | None = None,
    ):
        if id is not None:
            self.id = id
        if tags is not None:
            self.tags = frozenset(tags)
    
    def __init_subclass__(cls):
        if 'id' not in cls.__dict__:
            cls.id: str = cls.__name__.replace('_', ' ')

    def __str__(self):
        return self.id
    
    def __repr__(self):
        values = self.__dict__.copy()
        if 'tags' in values:
            values['tags'] = set(values['tags'])
        return f"{self.__class__.__name__}(" + ', '.join(f"{k}={v!r}" for k, v in values.items()) + ")"
    
    id: str
    tags: frozenset[str] = frozenset()

    target_count: int = 1
    phase: Phase | None = Phase.NIGHT  # None means it can be used at any time.
    immediate: bool = False  # If True, the ability is performed immediately.

    def check(self, game: Game, actor: Player, targets: Sequence[Player] | None = None) -> bool:
        return (
            (self.phase is None or game.phase == self.phase)
            and actor.is_alive
            and (targets is None or actor not in targets)
        )

    @abstractmethod
    def perform(self, game: Game, actor: Player, targets: Sequence[Player] | None = None, *, visit: Visit) -> VisitStatus:
        ...

class Role:
    def __init__(
        self,
        id: str | None = None,
        actions: tuple[Ability, ...] | None = None,
        passives: tuple[Ability, ...] | None = None,
        shared_actions: tuple[Ability, ...] | None = None,
        tags: frozenset[str] | None = None,
    ):
        if id is not None:
            self.id = id
        if actions is not None:
            self.actions = actions
        if passives is not None:
            self.passives = passives
        if shared_actions is not None:
            self.shared_actions = shared_actions
        if tags is not None:
            self.tags = tags
    
    def __init_subclass__(cls):
        if 'id' not in cls.__dict__:
            cls.id: str = cls.__name__.replace('_', ' ')

    def __str__(self):
        return self.id

    def __repr__(self):
        values = self.__dict__.copy()
        if 'tags' in values:
            values['tags'] = set(values['tags'])
        return f"{self.__class__.__name__}(" + ', '.join(f"{k}={v!r}" for k, v in values.items()) + ")"

    def player_init(self, game: Game, player: Player) -> None:
        """Called when a player is initialized with this role."""
        pass

    id: str
    actions: tuple[Ability, ...] = ()
    passives: tuple[Ability, ...] = ()
    shared_actions: tuple[Ability, ...] = ()
    tags: frozenset[str] = frozenset()

class Alignment(ABC):
    def __init__(
        self,
        id: str | None = None,
        actions: tuple[Ability, ...] | None = None,
        passives: tuple[Ability, ...] | None = None,
        shared_actions: tuple[Ability, ...] | None = None,
        tags: frozenset[str] | None = None,
    ):
        if id is not None:
            self.id = id
        if actions is not None:
            self.actions = actions
        if passives is not None:
            self.passives = passives
        if shared_actions is not None:
            self.shared_actions = shared_actions
        if tags is not None:
            self.tags = tags

    def __str__(self):
        return self.id
    
    def __repr__(self):
        values = self.__dict__.copy()
        if 'tags' in values:
            values['tags'] = set(values['tags'])
        return f"{self.__class__.__name__}(" + ', '.join(f"{k}={v!r}" for k, v in values.items()) + ")"
    
    def __init_subclass__(cls):
        if 'id' not in cls.__dict__:
            cls.id: str = cls.__name__.replace('_', ' ')
    
    def player_init(self, game: Game, player: Player) -> None:
        """Called when a player is initialized with this alignment."""
        pass

    id: str = '<Alignment>'
    actions: tuple[Ability, ...] = ()
    passives: tuple[Ability, ...] = ()
    shared_actions: tuple[Ability, ...] = ()
    tags: frozenset[str] = frozenset()

    def check_win(self, game: Game, player: Player) -> WinResult:
        return WinResult.WIN if Player.is_alive else WinResult.LOSE

class Faction(Alignment):
    id: str
    
    def check_win(self, game: Game, player: Player) -> WinResult:
        faction_alive: bool = False
        opponent_alive: bool = False
        for p in game.alive_players:
            if p.alignment == self:
                faction_alive = True
            elif isinstance(p.alignment, Faction):
                opponent_alive = True
        if not faction_alive:
            return WinResult.LOSE
        if not opponent_alive:
            return WinResult.WIN
        return WinResult.ONGOING

@dataclass(eq=False)
class ChatMessage:
    sender: Player | str
    content: str

class Chat(list[ChatMessage]):
    def __init__(self, *args, participants: set[Player] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.participants = set() if participants is None else participants

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({super().__repr__()}, participants={self.participants!r})"
    
    participants: set[Player]
    
    def send(self, sender: Player | str, content: str) -> None:
        self.append(ChatMessage(sender, content))

@dataclass(eq=False)
class Player:
    def __post_init__(self, game: Game | None) -> None:
        if game is not None:
            game.players.append(self)
            self.role.player_init(game, self)
            self.alignment.player_init(game, self)
        for ability in self.role.actions:
            self.actions.append(ability)
        for ability in self.role.passives:
            self.passives.append(ability)
        for ability in self.role.shared_actions:
            self.shared_actions.append(ability)
        for ability in self.alignment.actions:
            self.actions.append(ability)
        for ability in self.alignment.passives:
            self.passives.append(ability)
        for ability in self.alignment.shared_actions:
            self.shared_actions.append(ability)

    def __repr__(self) -> str:
        return f"Player({self.name!r}, {self.role!r}, {self.alignment!r}, private_messages={self.private_messages!r})"

    def __str__(self) -> str:
        return self.name
    
    name: str
    role: Role
    alignment: Alignment
    private_messages: Chat = field(default_factory=Chat, kw_only=True)
    death_causes: list[str] = field(default_factory=list, kw_only=True)
    actions: list[Ability] = field(default_factory=list, kw_only=True)
    passives: list[Ability] = field(default_factory=list, kw_only=True)
    shared_actions: list[Ability] = field(default_factory=list, kw_only=True)
    game: InitVar[Game | None] = field(default=None, kw_only=True)

    def kill(self, cause: str) -> None:
        self.death_causes.append(cause)

    @property
    def is_alive(self) -> bool:
        return not self.death_causes

    def get_visits(self, game: Game) -> Iterator[Visit]:
        """Get all visits that this player is performing."""
        return filter(lambda v: v.actor == self, game.visits)
        
    def get_visitors(self, game: Game) -> Iterator[Visit]:
        """Get all visits that are targeting this player."""
        return filter(lambda v: self in v.targets, game.visits)

@dataclass(eq=False)
class Game:
    players: list[Player] = field(default_factory=list, kw_only=True)
    visits: list[Visit] = field(default_factory=list, kw_only=True)
    chats: dict[str, Chat] = field(default_factory=dict, kw_only=True)
    day_no: int = 0
    phase: Phase = Phase.DAY
    
    @property
    def alive_players(self) -> Iterator[Player]:
        return filter(lambda p: p.is_alive, self.players)