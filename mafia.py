"""
Mafia game framework.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence, Iterator
from types import EllipsisType
from typing import Any, TypeGuard, TypeVar, cast
from enum import Enum, auto, IntEnum
from dataclasses import InitVar, dataclass, field
from abc import ABC, abstractmethod


class VisitStatus(IntEnum):
    PENDING = -1
    FAILURE = 0
    SUCCESS = 1


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


def role_name(role: Role, alignment: Alignment) -> str:
    """
    Computes a role name from a role and alignment pair.

    - `role.is_adjective` -- Use `{role} {alignment.demonym}` instead of `{alignment} {role}`.
    - `alignment.demonym` -- defaults to `str(alignment)`.
    - `alignment.role_names[role.id]` -- a custom role name.

    `alignment.demonym` and `alignment.role_names[role.id]` both support format strings, passing `role` and `alignment`
    """
    role_name_override: str | None = alignment.role_names.get(role.id)
    if role_name_override is not None:
        return role_name_override.format(role=role, alignment=alignment)
    if role.is_adjective:
        if alignment.demonym:
            return f"{role} {alignment.demonym.format(role=role, alignment=alignment)}"
        return f"{role} {alignment}"
    return f"{alignment} {role}"


class Ability:
    def __init__(
        self,
        id: str | None = None,
        tags: frozenset[str] | None = None,
    ):
        if id is not None:
            self.id = id
        if tags is not None:
            self.tags = frozenset(tags)

    def __init_subclass__(cls) -> None:
        if "id" not in cls.__dict__:
            cls.id = cls.__name__.replace("_", " ")

    def __str__(self) -> str:
        return self.id

    def __repr__(self) -> str:
        values = self.__dict__.copy()
        if "tags" in values:
            values["tags"] = set(values["tags"])
        return (
            f"{self.__class__.__name__}("
            + ", ".join(f"{k}={v!r}" for k, v in values.items())
            + ")"
        )

    id: str
    player_inputs_types: tuple[type, ...] = ()  # Input types for player input validation.
    tags: frozenset[str] = frozenset()

    target_count: int = 1
    phase: Phase | None = Phase.NIGHT  # None means it can be used at any time.
    immediate: bool = False  # If True, the ability is performed immediately.

    def check(self, game: Game, actor: Player, targets: Sequence[Player] | None = None) -> bool:
        return (
            (self.phase is None or game.phase == self.phase)
            and actor.is_alive
            and (targets is None or (all(t.is_alive for t in targets) and actor not in targets))
        )

    def perform(
        self, game: Game, actor: Player, targets: Sequence[Player] | None = None, *, visit: Visit
    ) -> int:
        raise NotImplementedError


@dataclass(eq=False)
class Visit:
    def __post_init__(self, game: Game | None) -> None:
        if self.phase is None or self.day_no is None:
            if game is None:
                raise ValueError("game must be provided if phase or day_no is None")
            self.phase = game.phase
            self.day_no = game.day_no
        if self.targets is None:
            self.targets = tuple(self.actor for _ in range(self.ability.target_count))
        self.tags = self.tags | self.ability.tags

    def __str__(self) -> str:
        targets = ", ".join(t.name for t in self.targets)
        return f"{self.actor.name}: {self.ability_type.name} {self.ability.id} -> {targets} - {self.status}"

    def __repr__(self) -> str:
        targets = ", ".join(t.name for t in self.targets)
        return f"Visit({self.actor.name}, [{targets}], {self.ability!r}, {self.ability_type!r}, {self.status!r}, {self.tags!r})"

    actor: Player
    targets: tuple[Player, ...] = None  # type: ignore[assignment]
    ability: Ability = field(kw_only=True)
    ability_type: AbilityType = field(kw_only=True)
    phase: Phase = field(default=None, kw_only=True)  # type: ignore[assignment]
    day_no: int = field(default=None, kw_only=True)  # type: ignore[assignment]
    game: InitVar[Game | None] = field(default=None, kw_only=True)
    player_inputs: tuple[object, ...] = field(default=(), kw_only=True)
    status: int = field(default=VisitStatus.PENDING, kw_only=True)
    tags: frozenset[str] = field(default_factory=frozenset, kw_only=True)

    def perform(self, game: Game) -> int:
        return self.ability.perform(game, self.actor, self.targets, visit=self)

    def is_active(self, game: Game) -> bool:
        return (
            self.phase == game.phase
            and self.day_no == game.day_no
            and self.status == VisitStatus.PENDING
        )

    def is_active_time(self, game: Game) -> bool:
        return self.phase == game.phase and self.day_no == game.day_no

    def is_self_target(self) -> bool:
        return all(t is self.actor for t in self.targets)


class Role:
    def __init__(
        self,
        id: str | None = None,
        actions: tuple[Ability, ...] | None = None,
        passives: tuple[Ability, ...] | None = None,
        shared_actions: tuple[Ability, ...] | None = None,
        tags: frozenset[str] | None = None,
        is_adjective: bool | None = None,
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
        if is_adjective is not None:
            self.is_adjective = is_adjective

    def __init_subclass__(cls) -> None:
        if "id" not in cls.__dict__:
            cls.id = cls.__name__.replace("_", " ")

    def __str__(self) -> str:
        return self.id

    def __repr__(self) -> str:
        values = self.__dict__.copy()
        if "tags" in values:
            values["tags"] = set(values["tags"])
        return (
            f"{self.__class__.__name__}("
            + ", ".join(f"{k}={v!r}" for k, v in values.items())
            + ")"
        )

    def player_init(self, game: Game, player: Player) -> None:
        """Called when a player is initialized with this role."""
        pass

    id: str
    actions: tuple[Ability, ...] = ()
    passives: tuple[Ability, ...] = ()
    shared_actions: tuple[Ability, ...] = ()
    tags: frozenset[str] = frozenset()
    is_adjective: bool = False

    modifiers: frozenset[str] = frozenset()

    def is_role(
        self, role: Any
    ) -> TypeGuard[
        Role | str | type[Role] | Modifier | type[Modifier] | Callable[..., type[Role]]
    ]:
        if isinstance(role, str):
            return self.id == role or role in self.modifiers
        if isinstance(role, Role):
            return self.id == role.id or isinstance(self, type(role))
        if isinstance(role, type) and issubclass(role, Role):
            return isinstance(self, role)
        if isinstance(role, Modifier):
            return role.id in self.modifiers or any(
                isinstance(m, type(role)) for m in self.modifiers
            )
        if isinstance(role, type) and issubclass(role, Modifier):
            return any(isinstance(m, role) for m in self.modifiers)
        if hasattr(role, "id"):
            return self.id == role.id or role.id in self.modifiers
        if callable(role):
            try:
                return self.is_role(role())
            except TypeError:
                pass
        return False


class Alignment(ABC):
    def __init__(
        self,
        id: str | None = None,
        actions: tuple[Ability, ...] | None = None,
        passives: tuple[Ability, ...] | None = None,
        shared_actions: tuple[Ability, ...] | None = None,
        tags: frozenset[str] | None = None,
        demonym: str | None | EllipsisType = ...,
        role_names: dict[str, str] | None = None,
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
        if demonym is not ...:
            self.demonym = demonym
        if role_names is not None:
            self.role_names = role_names

    def __str__(self) -> str:
        return self.id

    def __repr__(self) -> str:
        values = self.__dict__.copy()
        if "tags" in values:
            values["tags"] = set(values["tags"])
        return (
            f"{self.__class__.__name__}("
            + ", ".join(f"{k}={v!r}" for k, v in values.items())
            + ")"
        )

    def __init_subclass__(cls) -> None:
        if "id" not in cls.__dict__:
            cls.id = cls.__name__.replace("_", " ")

    def player_init(self, game: Game, player: Player) -> None:
        """Called when a player is initialized with this alignment."""
        pass

    id: str
    actions: tuple[Ability, ...] = ()
    passives: tuple[Ability, ...] = ()
    shared_actions: tuple[Ability, ...] = ()
    tags: frozenset[str] = frozenset()
    demonym: str | None = None
    role_names: dict[str, str] = {}

    def check_win(self, game: Game, player: Player) -> WinResult:
        return WinResult.WIN if player.is_alive else WinResult.LOSE


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


RAA = TypeVar("RAA", bound=Ability | Role | Alignment)


class Modifier:
    def __init__(
        self,
        id: str | None = None,
        tags: frozenset[str] | None = None,
    ):
        if id is not None:
            self.id = id
        if tags is not None:
            self.tags = tags

    def __init_subclass__(cls) -> None:
        if "id" not in cls.__dict__:
            cls.id = cls.__name__.replace("_", " ")

    id: str
    tags: frozenset[str] = frozenset()

    def modify_ability(self, ability: type[Ability]) -> type[Ability]:
        raise TypeError(f"Cannot apply {self.__class__.__name__} to {ability.__name__}")

    def modify_role(self, role: type[Role]) -> type[Role]:
        raise TypeError(f"Cannot apply {self.__class__.__name__} to {role.__name__}")

    def modify_alignment(self, alignment: type[Alignment]) -> type[Alignment]:
        raise TypeError(f"Cannot apply {self.__class__.__name__} to {alignment.__name__}")

    def __call__(self, cls: type[RAA], *args: Any, **kwargs: Any) -> type[RAA]:
        result: type[RAA]
        if issubclass(cls, Ability):
            result = cast(type[RAA], self.modify_ability(cls, *args, **kwargs))
        elif issubclass(cls, Role):
            result = cast(type[RAA], self.modify_role(cls, *args, **kwargs))
        elif issubclass(cls, Alignment):
            result = cast(type[RAA], self.modify_alignment(cls, *args, **kwargs))
        else:
            raise TypeError(f"Cannot apply {self.__class__.__name__} to {cls.__name__}")
        result.__name__ = f"{self!r}({cls.__name__})"
        return result

    def __repr__(self) -> str:
        values = self.__dict__.copy()
        if "tags" in values:
            values["tags"] = set(values["tags"])
        return (
            f"{self.__class__.__name__}("
            + ", ".join(f"{k}={v!r}" for k, v in values.items())
            + ")"
        )


class AbilityModifier(Modifier, ABC):
    def __init_subclass__(cls) -> None:
        if "id" not in cls.__dict__:
            cls.id = cls.__name__.replace("_", " ")

    id: str

    @abstractmethod
    def modify_ability(self, ability: type[Ability]) -> type[Ability]:
        raise NotImplementedError

    def get_modified_abilities(
        self, role: type[Role] | type[Alignment], *args: Any, **kwargs: Any
    ) -> dict[str, list[Ability]]:
        abilities: dict[str, list[Ability]] = {"actions": [], "passives": [], "shared_actions": []}
        for ability_type in abilities:
            ability_inst: Ability
            for ability_inst in getattr(role, ability_type):
                ability = self(type(ability_inst), *args, **kwargs)
                abilities[ability_type].append(ability())
        return abilities

    T = TypeVar("T", Role, Alignment)

    def modify(self, cls: type[T], cls_dict: dict[str, Any] | None = None) -> type[T]:
        abilities = self.get_modified_abilities(cls)
        if cls_dict is None:
            cls_dict = {
                "actions": tuple(abilities["actions"]),
                "passives": tuple(abilities["passives"]),
                "shared_actions": tuple(abilities["shared_actions"]),
                "tags": cls.tags | self.tags,
            }
            if issubclass(cls, Role):
                cls_dict["id"] = f"{cls.id} {self.id}"
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


@dataclass(eq=False)
class ChatMessage:
    sender: Player | str
    content: str


class Chat(list[ChatMessage]):
    def __init__(self, *args: Any, participants: set[Player] | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.participants = set() if participants is None else participants

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}({super().__repr__()}, participants={self.participants!r})"
        )

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

    # def __repr__(self) -> str:
    #     return f"Player({self.name!r}, {self.role!r}, {self.alignment!r}, private_messages={self.private_messages!r})"

    def __str__(self) -> str:
        return self.name

    @property
    def role_name(self) -> str:
        return role_name(self.role, self.alignment)

    name: str
    role: Role
    alignment: Alignment
    private_messages: Chat = field(default_factory=Chat, kw_only=True)
    death_causes: list[str] = field(default_factory=list, kw_only=True)
    actions: list[Ability] = field(default_factory=list, kw_only=True)
    passives: list[Ability] = field(default_factory=list, kw_only=True)
    shared_actions: list[Ability] = field(default_factory=list, kw_only=True)
    uses: dict[Ability, list[tuple[int, Phase, tuple[Player, ...]]]] = field(default_factory=dict, kw_only=True)
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
    day_no: int = 1
    phase: Phase = Phase.DAY
    players: list[Player] = field(default_factory=list, kw_only=True)
    visits: list[Visit] = field(default_factory=list, kw_only=True)
    chats: dict[str, Chat] = field(default_factory=dict, kw_only=True)

    @property
    def alive_players(self) -> Iterator[Player]:
        return filter(lambda p: p.is_alive, self.players)
