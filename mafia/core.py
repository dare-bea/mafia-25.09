"""Mafia game framework."""

from __future__ import annotations

import re
from collections.abc import Callable, Generator, Iterable, Iterator, Sequence
from dataclasses import InitVar, dataclass, field
from enum import Enum, IntEnum, auto
from itertools import product
from typing import Any, TypeGuard, TypeVar, cast


class VisitStatus(IntEnum):
    """Visit status codes."""

    PENDING = -1
    FAILURE = 0
    SUCCESS = 1


class Phase(Enum):
    """Game phases."""

    DAY = "day"
    NIGHT = "night"


class WinResult(Enum):
    """Win result codes for alignment win checks."""

    ONGOING = 0
    WIN = 1
    LOSE = -1


class AbilityType(Enum):
    """Ability types."""

    ACTION = auto()
    PASSIVE = auto()
    SHARED_ACTION = auto()


def role_name(role: Role, alignment: Alignment) -> str:
    """Compute a role name from a role and alignment pair.

    - `role.is_adjective` -- Use `{role} {alignment.demonym}`
      instead of `{alignment} {role}`.
    - `alignment.demonym` -- defaults to `str(alignment)`.
    - `alignment.role_names[role.id]` -- a custom role name.

    `alignment.demonym` and `alignment.role_names[role.id]` both support format strings,
    passing `role` and `alignment`.
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
    """Base class for abilities.

    Each ability has an ID, a description, and a set of tags.
    Extend this class to create custom abilities.
    """

    def __init__(
        self,
        id: str | None = None,
        tags: frozenset[str] | None = None,
    ):
        """Initialize an ability.

        :param id: The ID of the ability. Defaults to the class `id`.
        :param tags: The tags of the ability.
        """
        if id is not None:
            self.id = id
        if tags is not None:
            self.tags = frozenset(tags)

    def __init_subclass__(cls) -> None:
        """Initialize a subclass of Ability.

        If the subclass does not have an `id` attribute, it will be set to the class name.
        If the subclass does not have a `description` attribute,
        it will be set to the class docstring.
        """
        if "id" not in cls.__dict__:
            cls.id = re.sub(r"(_*[A-Z_])", r" \1", cls.__name__).strip()
        if "description" not in cls.__dict__ and cls.__doc__ is not None:
            cls.description = cls.__doc__.strip()

    def __str__(self) -> str:
        """Return the ID of the ability."""
        return self.id

    def __repr__(self) -> str:
        """Return a string representation of the ability."""
        values = self.__dict__.copy()
        if "tags" in values:
            values["tags"] = set(values["tags"])
        return (
            f"{self.__class__.__name__}("
            + ", ".join(f"{k}={v!r}" for k, v in values.items())
            + ")"
        )

    id: str
    description: str | None = None  # Description of the ability.
    player_inputs_types: tuple[type, ...] = ()  # Input types for player input validation.
    tags: frozenset[str] = frozenset()

    target_count: int = 1
    phase: Phase | None = Phase.NIGHT  # None means it can be used at any time.
    immediate: bool = False  # If True, the ability is performed immediately.

    def check(
        self,
        game: Game,
        actor: Player,
        targets: Sequence[Player] | None = None,
    ) -> bool:
        """Check if an ability can be used by a player.

        Depends on the the given targets and game state.
        """
        return (
            (self.phase is None or game.phase == self.phase)
            and actor.is_alive
            and (
                targets is None
                or (all(t.is_alive for t in targets) and actor not in targets)
            )
        )

    def perform(
        self,
        game: Game,
        actor: Player,
        targets: Sequence[Player] | None = None,
        *,
        visit: Visit,
    ) -> int:
        """Perform an ability."""
        raise NotImplementedError

    def has_valid_targets(
        self,
        game: Game,
        actor: Player,
        *,
        is_passive: bool = False,
    ) -> bool:
        """Check if an ability has any valid targets."""
        if is_passive:
            return self.check(game, actor)
        if self.target_count == 0:
            return self.check(game, actor, ())
        for targets in product(game.players, repeat=self.target_count):
            if self.check(game, actor, targets):
                return True
        return False

    def valid_targets(
        self,
        game: Game,
        actor: Player,
        *,
        is_passive: bool = False,
    ) -> Generator[tuple[Player, ...], None, None]:
        """Get all valid targets for an ability."""
        if is_passive and self.check(game, actor):
            yield tuple(actor for _ in range(self.target_count))
            return
        for targets in product(game.players, repeat=self.target_count):
            if self.check(game, actor, targets):
                yield targets


@dataclass(eq=False)
class Visit:
    """A record of a player using an ability on a target.

    The visit is stored in the game's visit history and is used to resolve the game state.
    """

    def __post_init__(self, game: Game | None) -> None:
        """Record the current game phase and day number if not provided."""
        if self.phase is None or self.day_no is None:
            if game is None:
                err = "game must be provided if phase or day_no is None"
                raise ValueError(err)
            self.phase = game.phase
            self.day_no = game.day_no
        if self.targets is None:
            self.targets = tuple(self.actor for _ in range(self.ability.target_count))
        self.tags = self.tags | self.ability.tags

    def __str__(self) -> str:
        """Return a string representation of the visit."""
        targets = ", ".join(t.name for t in self.targets)
        return (
            f"{self.actor.name}: {self.ability_type.name} {self.ability.id} -> "
            f"{targets} - {self.status}"
        )

    def __repr__(self) -> str:
        """Return a string representation of the visit."""
        targets = ", ".join(t.name for t in self.targets)
        return (
            f"Visit({self.actor.name}, [{targets}], {self.ability!r}, "
            "{self.ability_type!r}, {self.status!r}, {self.tags!r})"
        )

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
        """Perform the ability of the visit."""
        return self.ability.perform(game, self.actor, self.targets, visit=self)

    def is_active(self, game: Game) -> bool:
        """Check if the visit is active with the current game state."""
        return (
            self.phase == game.phase
            and self.day_no == game.day_no
            and self.status == VisitStatus.PENDING
        )

    def is_active_time(self, game: Game) -> bool:
        """Check if the visit is active with the current game time."""
        return self.time == game.time

    def is_self_target(self) -> bool:
        """Check if the visit targets the actor."""
        return all(t is self.actor for t in self.targets)

    @property
    def time(self) -> tuple[int, Phase]:
        """Get the time of the visit."""
        return (self.day_no, self.phase)

    @time.setter
    def time(self, value: tuple[int, Phase]) -> None:
        """Set the time of the visit."""
        self.day_no, self.phase = value

    def is_success(self) -> bool:
        """Check if the visit was successful."""
        return self.status >= VisitStatus.SUCCESS


class Role:
    """Base class for roles.

    Each role has an ID, a set of actions, a set of passives, and a set of tags.
    Extend this class to create custom roles.
    """

    def __init__(
        self,
        id: str | None = None,
        actions: tuple[Ability, ...] | None = None,
        passives: tuple[Ability, ...] | None = None,
        tags: frozenset[str] | None = None,
        *,
        is_adjective: bool | None = None,
    ):
        """Initialize a role."""
        if id is not None:
            self.id = id
        if actions is not None:
            self.actions = actions
        if passives is not None:
            self.passives = passives
        if tags is not None:
            self.tags = tags
        if is_adjective is not None:
            self.is_adjective = is_adjective

    def __init_subclass__(cls) -> None:
        """Initialize a subclass of Role.

        If the subclass does not have an `id` attribute, it will be set to the class name.
        """
        if "id" not in cls.__dict__:
            cls.id = re.sub(r"(_*[A-Z_])", r" \1", cls.__name__).strip()

    def __str__(self) -> str:
        """Return the ID of the role."""
        return self.id

    def __repr__(self) -> str:
        """Return a string representation of the role."""
        values = self.__dict__.copy()
        if "tags" in values:
            values["tags"] = set(values["tags"])
        return (
            f"{self.__class__.__name__}("
            + ", ".join(f"{k}={v!r}" for k, v in values.items())
            + ")"
        )

    def player_init(self, game: Game, player: Player) -> None:
        """Initialize a player with this role."""

    id: str
    actions: tuple[Ability, ...] = ()
    passives: tuple[Ability, ...] = ()
    tags: frozenset[str] = frozenset()
    is_adjective: bool = False

    modifiers: frozenset[str] = frozenset()

    # too non-specific, deprecate and remove later.
    def is_role(  # noqa: PLR0911
        self,
        role: Any,
    ) -> TypeGuard[
        type[Role | Modifier] | Role | str | Modifier | Callable[..., type[Role]]
    ]:
        """Check if this role is the given role."""
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

    @classmethod
    def combine(cls, *roles: type[Role]) -> type[Role]:
        """Combine multiple roles into one with the abilities of all of them."""
        _roles = roles if cls is Role else (cls, *roles)

        class CombinedRole(Role):
            roles = tuple(r() for r in _roles)
            id = " ".join(r.id for r in roles)
            actions = tuple(a for r in roles for a in r.actions)
            passives = tuple(a for r in roles for a in r.passives)
            tags = frozenset().union(*(r.tags for r in roles))
            is_adjective = all(r.is_adjective for r in roles)
            modifiers = frozenset().union(*(r.modifiers for r in roles))

            def player_init(self, game: Game, player: Player) -> None:
                super().player_init(game, player)
                for r in self.roles:
                    r.player_init(game, player)

            def is_role(
                self,
                role: Any,
            ) -> TypeGuard[
                type[Role | Modifier] | Role | str | Modifier | Callable[..., type[Role]]
            ]:
                return any(r.is_role(role) for r in self.roles) or super().is_role(role)

        return CombinedRole


class Alignment:
    """Base class for alignments.

    Each alignment has an ID, a set of actions, a set of passives, and a set of tags.
    Extend this class to create custom alignments.
    """

    def __init__(  # noqa: PLR0913
        self,
        id: str | None = None,
        actions: tuple[Ability, ...] | None = None,
        passives: tuple[Ability, ...] | None = None,
        shared_actions: tuple[Ability, ...] | None = None,
        tags: frozenset[str] | None = None,
        demonym: str | None = None,
        role_names: dict[str, str] | None = None,
    ):
        """Initialize an alignment.

        :param id: The ID of the alignment. Defaults to the class `id`.
        :param demonym: The demonym of the alignment. Defaults to the class `demonym`.
        Set to `''` to disable the default demonym.
        :param role_names: A dictionary of role names for this alignment.
        Defaults to the class `role_names`.

        `demonym` and `role_names` support format strings, passing `role` and `alignment`.
        """
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
        if demonym is not None:
            self.demonym = demonym
        self.role_names = self.role_names.copy() if role_names is None else role_names

    def __str__(self) -> str:
        """Return the ID of the alignment."""
        return self.id

    def __repr__(self) -> str:
        """Return a string representation of the alignment."""
        values = self.__dict__.copy()
        if "tags" in values:
            values["tags"] = set(values["tags"])
        return (
            f"{self.__class__.__name__}("
            + ", ".join(f"{k}={v!r}" for k, v in values.items())
            + ")"
        )

    def __init_subclass__(cls) -> None:
        """Initialize a subclass of Alignment.

        If the subclass does not have an `id` attribute, it will be set to the class name.
        """
        if "id" not in cls.__dict__:
            cls.id = re.sub(r"(_*[A-Z_])", r" \1", cls.__name__).strip()

    def player_init(self, game: Game, player: Player) -> None:
        """Initialize a player with this alignment."""

    id: str
    actions: tuple[Ability, ...] = ()
    passives: tuple[Ability, ...] = ()
    shared_actions: tuple[Ability, ...] = ()
    tags: frozenset[str] = frozenset()
    demonym: str = ""
    role_names: dict[str, str] = {}

    def check_win(self, game: Game, player: Player) -> WinResult:
        """Check if the player has won or lost the game."""
        return WinResult.WIN if player.is_alive else WinResult.LOSE


class Faction(Alignment):
    """Base class for factions.

    Factions are alignments that win as a team when all other factions are dead.
    If a faction has no players alive, it is considered dead and cannot win.
    Extend this class to create custom factions.
    """

    id: str

    def check_win(self, game: Game, player: Player) -> WinResult:
        """Check if the player has won or lost the game."""
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
    """Base class for modifiers.

    Modifiers are used to modify abilities, roles, and alignments.
    They are applied to the class by calling the modifier as a function.
    Extend this class to create custom modifiers.
    """

    def __init__(
        self,
        id: str | None = None,
        tags: frozenset[str] | None = None,
    ):
        """Initialize a modifier.

        :param id: The ID of the modifier. Defaults to the class `id`.
        """
        if id is not None:
            self.id = id
        if tags is not None:
            self.tags = tags

    def __init_subclass__(cls) -> None:
        """Initialize a subclass of Modifier.

        If the subclass does not have an `id` attribute, it will be set to the class name.
        """
        if "id" not in cls.__dict__:
            cls.id = re.sub(r"(_*[A-Z_])", r" \1", cls.__name__).strip()

    id: str
    tags: frozenset[str] = frozenset()

    def modify_ability(self, ability: type[Ability]) -> type[Ability]:
        """Modify an ability."""
        message = f"Cannot apply {self.__class__.__name__} to {ability.__name__}"
        raise TypeError(message)

    def modify_role(self, role: type[Role]) -> type[Role]:
        """Modify a role."""
        message = f"Cannot apply {self.__class__.__name__} to {role.__name__}"
        raise TypeError(message)

    def modify_alignment(self, alignment: type[Alignment]) -> type[Alignment]:
        """Modify an alignment."""
        message = f"Cannot apply {self.__class__.__name__} to {alignment.__name__}"
        raise TypeError(message)

    def modify(self, cls: type[RAA], *args: Any, **kwargs: Any) -> type[RAA]:
        """Apply the modifier to a class."""
        result: type[RAA]
        if issubclass(cls, Ability):
            result = cast("type[RAA]", self.modify_ability(cls, *args, **kwargs))
        elif issubclass(cls, Role):
            result = cast("type[RAA]", self.modify_role(cls, *args, **kwargs))
        elif issubclass(cls, Alignment):
            result = cast("type[RAA]", self.modify_alignment(cls, *args, **kwargs))
        else:
            message = f"Cannot apply {self.__class__.__name__} to {cls.__name__}"
            raise TypeError(message)
        result.__name__ = f"{self!r}({cls.__name__})"
        return result

    def __call__(self, cls: type[RAA], *args: Any, **kwargs: Any) -> type[RAA]:
        """Apply the modifier to a class."""
        return self.modify(cls, *args, **kwargs)

    def __repr__(self) -> str:
        """Return a string representation of the modifier."""
        values = self.__dict__.copy()
        if "tags" in values:
            values["tags"] = set(values["tags"])
        return (
            f"{self.__class__.__name__}("
            + ", ".join(f"{k}={v!r}" for k, v in values.items())
            + ")"
        )


class AbilityModifier(Modifier):
    """Base class for ability modifiers.

    Ability modifiers are used to modify abilities.
    If the modifier is applied to a role or alignment,
    it will be applied to all of their abilities.
    Extend this class to create custom ability modifiers.
    """

    def __init_subclass__(cls) -> None:
        """Initialize a subclass of AbilityModifier.

        If the subclass does not have an `id` attribute, it will be set to the class name.
        """
        if "id" not in cls.__dict__:
            cls.id = re.sub(r"(_*[A-Z_])", r" \1", cls.__name__).strip()

    id: str

    def modify_ability(self, ability: type[Ability]) -> type[Ability]:
        """Modify an ability."""
        return type(
            f"{self!r}({ability.__name__})",
            (ability,),
            {
                "id": ability.id,
                "tags": ability.tags | self.tags,
            },
        )

    def get_modified_abilities(
        self,
        role: type[Role | Alignment],
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, list[Ability]]:
        """Get the modified abilities of a role or alignment."""
        abilities: dict[str, list[Ability]] = {
            "actions": [],
            "passives": [],
            "shared_actions": [],
        }
        for ability_type, ability_list in abilities.items():
            ability_inst: Ability
            for ability_inst in getattr(role, ability_type, []):
                ability = self(type(ability_inst), *args, **kwargs)
                ability_list.append(ability())
        return abilities

    T = TypeVar("T", Role, Alignment)

    def modify_cls(self, cls: type[T], cls_dict: dict[str, Any] | None = None) -> type[T]:
        """Modify a role or alignment."""
        abilities = self.get_modified_abilities(cls)
        if cls_dict is None:
            cls_dict = {
                "id": f"{self.id} {cls.id}" if issubclass(cls, Role) else cls.id,
                "actions": tuple(abilities["actions"]),
                "passives": tuple(abilities["passives"]),
                "shared_actions": tuple(abilities["shared_actions"]),
                "tags": cls.tags | self.tags,
            }
        return type(
            f"{self!r}({cls.__name__})",
            (cls,),
            cls_dict,
        )

    def modify_role(self, role: type[Role], *args: Any, **kwargs: Any) -> type[Role]:
        """Modify a role."""
        return self.modify_cls(role, *args, **kwargs)

    def modify_alignment(
        self,
        alignment: type[Alignment],
        *args: Any,
        **kwargs: Any,
    ) -> type[Alignment]:
        """Modify an alignment."""
        return self.modify_cls(alignment, *args, **kwargs)


@dataclass(frozen=True, eq=True)
class ChatMessage:
    """A message in a chat."""

    sender: Player | str
    content: str


class Chat(list[ChatMessage]):
    """A public chat that can be read and written to by players."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize a chat."""
        super().__init__(*args, **kwargs)

    def __repr__(self) -> str:
        """Return a string representation of the chat."""
        return f"{self.__class__.__name__}({super().__repr__()})"

    def has_read_perms(self, game: Game, player: Player | None) -> bool:
        """Check if a player has read permissions for the chat."""
        return True

    def has_write_perms(self, game: Game, player: Player | None) -> bool:
        """Check if a player has write permissions for the chat."""
        return (
            player is not None
            and player in game.alive_players
            and game.phase not in game.chat_phases
        )

    def read_perms(self, game: Game) -> Iterator[Player]:
        """Get all players with read permissions for the chat."""
        return filter(lambda p: self.has_read_perms(game, p), game.players)

    def write_perms(self, game: Game) -> Iterator[Player]:
        """Get all players with write permissions for the chat."""
        return filter(lambda p: self.has_write_perms(game, p), game.players)

    def send(
        self, *args: Any, type: type[ChatMessage] = ChatMessage, **kwargs: Any
    ) -> None:
        """Send a message to the chat."""
        self.append(type(*args, **kwargs))


class PrivateChat(Chat):
    """A private chat that can only be read and written to by specific players."""

    def __init__(
        self,
        *args: Any,
        participants: Iterable[Player] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a private chat."""
        super().__init__(*args, **kwargs)
        self.participants = set() if participants is None else set(participants)

    def has_read_perms(self, game: Game, player: Player | None) -> bool:
        """Check if a player has read permissions for the chat."""
        return player is not None and player in self.participants

    def has_write_perms(self, game: Game, player: Player | None) -> bool:
        """Check if a player has write permissions for the chat."""
        return (
            player is not None
            and player in self.participants
            and player in game.alive_players
        )

    def __repr__(self) -> str:
        """Return a string representation of the chat."""
        return (
            f"{self.__class__.__name__}({super().__repr__()}, "
            f"participants={self.participants!r})"
        )

    participants: set[Player]


@dataclass(eq=False)
class Player:
    """A player in a game."""

    def __post_init__(self) -> None:
        """Initialize the player's actions, passives, and shared actions."""
        self.private_messages.participants.add(self)
        for ability in self.role.actions:
            self.actions.append(ability)
        for ability in self.role.passives:
            self.passives.append(ability)
        for ability in self.alignment.actions:
            self.actions.append(ability)
        for ability in self.alignment.passives:
            self.passives.append(ability)
        for ability in self.alignment.shared_actions:
            self.shared_actions.append(ability)

    def __str__(self) -> str:
        """Return the player's name."""
        return self.name

    @property
    def role_name(self) -> str:
        """Return the player's role name."""
        return role_name(self.role, self.alignment)

    name: str
    role: Role
    alignment: Alignment
    private_messages: PrivateChat = field(default_factory=PrivateChat, kw_only=True)
    death_causes: list[str] = field(default_factory=list, kw_only=True)
    actions: list[Ability] = field(default_factory=list, kw_only=True)
    passives: list[Ability] = field(default_factory=list, kw_only=True)
    shared_actions: list[Ability] = field(default_factory=list, kw_only=True)
    uses: dict[Ability, int] = field(default_factory=dict, kw_only=True)
    action_history: list[Visit] = field(default_factory=list, kw_only=True)
    known_players: set[Player] = field(default_factory=set, kw_only=True)

    def kill(self, cause: str) -> None:
        """Kill the player with the given cause."""
        self.death_causes.append(cause)

    @property
    def is_alive(self) -> bool:
        """Check if the player is alive."""
        return not self.death_causes

    def get_visits(self, game: Game) -> Iterator[Visit]:
        """Get all visits that this player is performing."""
        return filter(lambda v: v.actor == self, game.visits)

    def get_visitors(self, game: Game) -> Iterator[Visit]:
        """Get all visits that are targeting this player."""
        return filter(lambda v: self in v.targets, game.visits)


@dataclass(eq=False)
class Game:
    """A game of Mafia."""

    def __post_init__(self, start_phase: Any | None) -> None:
        """Initialize the game's phase."""
        if start_phase is not None:
            self.phase = start_phase

    day_no: int = 1
    phase_order: tuple[Any, ...] = (Phase.DAY, Phase.NIGHT)
    players: list[Player] = field(default_factory=list, kw_only=True)
    # History of visits: ALL visits are stored, even if they are not active.
    visits: list[Visit] = field(default_factory=list, kw_only=True)
    chats: dict[str, Chat] = field(default_factory=dict, kw_only=True)
    votes: dict[Player, Player | None] = field(default_factory=dict, kw_only=True)
    phase_idx: int = field(default=0, kw_only=True)
    start_phase: InitVar[Any | None] = field(default=None, kw_only=True)
    chat_phases: frozenset[Any] = field(default=frozenset({Phase.DAY}), kw_only=True)
    voting_phases: frozenset[Any] = field(default=frozenset({Phase.DAY}), kw_only=True)

    @property
    def phase(self) -> Any:
        """Get the current phase of the game."""
        return self.phase_order[self.phase_idx]

    @phase.setter
    def phase(self, value: Any) -> None:
        """Set the current phase of the game."""
        self.phase_idx = self.phase_order.index(value)

    @property
    def time(self) -> tuple[int, Any]:
        """Get the current time of the game."""
        return (self.day_no, self.phase)

    @time.setter
    def time(self, value: tuple[int, Any]) -> None:
        """Set the current time of the game."""
        self.day_no, self.phase = value

    def advance_phase(self) -> tuple[int, Any]:
        """Advance the game to the next phase."""
        if self.phase_idx + 1 >= len(self.phase_order):
            self.phase_idx = 0
            self.day_no += 1
        else:
            self.phase_idx += 1
        self.votes.clear()
        return (self.day_no, self.phase)

    @property
    def alive_players(self) -> Iterator[Player]:
        """Get all alive players in the game."""
        return filter(lambda p: p.is_alive, self.players)

    def add_player(self, *players: Player) -> None:
        """Add a player to the game, initializing their role and alignment."""
        for player in players:
            self.players.append(player)
            player.role.player_init(self, player)
            player.alignment.player_init(self, player)
            for p in self.players:
                if p is player:
                    continue
                if (
                    "informed" in player.alignment.tags
                    and p.alignment.id == player.alignment.id
                ):
                    player.known_players.add(p)
                if "informed" in player.role.tags and p.role.id == player.role.id:
                    player.known_players.add(p)
                if (
                    "informed" in p.alignment.tags
                    and p.alignment.id == player.alignment.id
                ):
                    p.known_players.add(player)
                if "informed" in p.role.tags and p.role.id == player.role.id:
                    p.known_players.add(player)

    def is_voting_phase(self) -> bool:
        """Check if the game is in a voting phase."""
        return self.phase in self.voting_phases

    def vote(self, player: Player, target: Player | None) -> None:
        """Vote for a player to be eliminated by majority vote."""
        self.votes[player] = target

    def unvote(self, player: Player) -> None:
        """Remove a player's vote."""
        self.votes.pop(player, None)

    def get_votes(self, target: Player | None) -> int:
        """Get the number of votes a player has received."""
        return len(tuple(self.get_voters(target)))

    def get_voters(self, target: Player | None) -> Iterator[Player]:
        """Get the players who have voted for a player."""
        return (p for p in self.votes if self.votes[p] == target)

    def get_vote_counts(self) -> dict[Player | None, int]:
        """Get the number of votes each player has received."""
        counts: dict[Player | None, int] = {}
        for p in self.votes.values():
            counts[p] = counts.get(p, 0) + 1
        return counts
