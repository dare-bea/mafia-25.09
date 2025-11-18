"""Models for API v1."""

from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, cast

from pydantic import BaseModel, Field, field_validator
from pydantic_core import PydanticCustomError

from mafia import core, normal

ErrorResponse = tuple[dict[str, str], int]
EmptyResponse = tuple[Literal[""], int]


class GameSummaryModel(BaseModel):
    id: int
    players: list[str]
    phase: core.Phase
    day_no: int
    phase_order: list[Any]
    chat_phases: list[Any]


class GameListQueryModel(BaseModel):
    start: int = 0
    limit: int = 25


class GameListResponseModel(BaseModel):
    games: list[GameSummaryModel]
    total_games: int


class RoleModel(BaseModel):
    node: Literal["role"] = "role"
    id: str

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: Any) -> Any:
        if v not in normal.ROLES:
            raise PydanticCustomError(
                "unknown_role",
                "Id must be one of {expected}, recieved {input}.",
                {"input": v, "expected": list(normal.ROLES.keys())},
            )
        return v

    def value(self) -> type[core.Role] | Callable[..., core.Role]:
        return normal.ROLES[self.id]


class CombinedRoleModel(BaseModel):
    node: Literal["combined_role"] = "combined_role"
    id: str
    roles: list["RoleModel | ModifierModel"]
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: Any) -> Any:
        if v not in normal.COMBINED_ROLES:
            raise PydanticCustomError(
                "unknown_combined_role",
                "Id must be one of {expected}, recieved {input}.",
                {"input": v, "expected": list(normal.COMBINED_ROLES.keys())},
            )
        return v

    def value(self) -> Callable[..., core.Role]:
        return normal.COMBINED_ROLES[self.id](
            *(r.value() for r in self.roles),
            **self.params,
        )


class ModifierModel(BaseModel):
    node: Literal["modifier"] = "modifier"
    id: str
    role: "RoleModel | CombinedRoleModel | ModifierModel"
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: Any) -> Any:
        if v not in normal.MODIFIERS:
            raise PydanticCustomError(
                "unknown_modifier",
                "Id must be one of {expected}, recieved {input}.",
                {"input": v, "expected": list(normal.MODIFIERS.keys())},
            )
        return v

    def value(self) -> type[core.Role]:
        r = self.role.value()
        if isinstance(r, type) and issubclass(r, core.Role):
            return normal.MODIFIERS[self.id](**self.params)(r)
        return normal.MODIFIERS[self.id](**self.params)(
            cast("type[core.Role]", type(r())),
        )


class GameCreateRequestRole(BaseModel):
    role: RoleModel | CombinedRoleModel | ModifierModel
    alignment: str
    role_params: dict[str, Any] = Field(default_factory=dict)
    alignment_id: str | None = None
    alignment_demonym: str | None = None
    alignment_role_names: dict[str, str] | None = None

    @field_validator("alignment")
    @classmethod
    def validate_alignment(cls, v: Any) -> Any:
        if v not in normal.ALIGNMENTS:
            raise PydanticCustomError(
                "unknown_alignment",
                "Alignment must be one of {expected}, recieved {input}.",
                {"input": v, "expected": list(normal.ALIGNMENTS.keys())},
            )
        return v

    def alignment_value(
        self,
    ) -> type[core.Alignment] | Callable[..., core.Alignment]:
        return normal.ALIGNMENTS[self.alignment]


class GameCreateRequestModel(BaseModel):
    players: list[str]
    day_no: int = 1
    phase_order: list[Any] = Field(
        default_factory=lambda: [core.Phase.DAY, core.Phase.NIGHT],
    )
    chat_phases: list[Any] = Field(default_factory=lambda: [core.Phase.NIGHT])
    phase: Any | None = None
    shuffle_roles: bool = True
    roles: list[GameCreateRequestRole]


class GameCreateResponseModel(BaseModel):
    id: int
    mod_token: str


class ShortPartialPlayerModel(BaseModel):
    name: str
    is_alive: bool


class ShortPlayerModel(BaseModel):
    name: str
    is_alive: bool
    role_name: str
    role: str
    alignment: str


class ShortChatModel(BaseModel):
    id: str
    total_messages: int


class GameResponseModel(BaseModel):
    id: int
    day_no: int
    phase: core.Phase
    players: list[ShortPlayerModel | ShortPartialPlayerModel]
    chats: list[ShortChatModel]
    phase_order: list[Any]
    chat_phases: list[Any]


class GamePutRequestModel(BaseModel):
    day_no: int | None = None
    phase: core.Phase | None = None
    phase_order: list[Any] | None = None
    chat_phases: list[Any] | None = None


class GamePatchAction(StrEnum):
    DEQUEUE = "dequeue"
    RESOLVE = "resolve"
    NEXT_PHASE = "next_phase"
    ADVANCE_PHASE = "advance_phase"
    CLEAR_VOTES = "clear_votes"
    POST_VOTE_COUNT = "post_vote_count"


class GamePatchRequestModel(BaseModel):
    actions: list[GamePatchAction]


class PlayerRAModel(BaseModel):
    id: str
    actions: list[str]
    passives: list[str]
    shared_actions: list[str]


class PlayerResponseModel(BaseModel):
    name: str
    is_alive: bool
    role_name: str
    role: PlayerRAModel
    alignment: PlayerRAModel
    known_players: list[ShortPlayerModel]
    total_private_messages: int
    chats: list[ShortChatModel]


class PlayerAbilitiesActionModel(BaseModel):
    id: str
    phase: core.Phase | None = None
    immediate: bool
    target_count: int
    targets: list[list[str]]
    queued: list[str] | None = None


class PlayerAbilitiesPassiveModel(BaseModel):
    id: str
    phase: core.Phase | None = None
    immediate: bool
    queued: bool


class PlayerAbilitiesSharedActionModel(BaseModel):
    id: str
    used_by: str | None = None
    phase: core.Phase | None = None
    immediate: bool
    target_count: int
    targets: list[list[str]]
    queued: list[str] | None = None


class PlayerAbiltiesResponseModel(BaseModel):
    actions: list[PlayerAbilitiesActionModel]
    passives: list[PlayerAbilitiesPassiveModel]
    shared_actions: list[PlayerAbilitiesSharedActionModel]


class PlayerQueueAbilityModel(BaseModel):
    targets: list[str] = Field(default_factory=list)
    player_inputs: list[Any] = Field(default_factory=list)


class PlayerQueueAbilityRequestModel(BaseModel):
    actions: dict[str, PlayerQueueAbilityModel | None] = Field(default_factory=dict)
    shared_actions: dict[str, PlayerQueueAbilityModel | None] = Field(
        default_factory=dict,
    )


class ChatQueryModel(BaseModel):
    start: int = 0
    limit: int = 25


class ChatMessageModel(BaseModel):
    author: str
    timestamp: datetime
    content: str


class PlayerPMResponseModel(BaseModel):
    total_messages: int
    messages: list[ChatMessageModel]


class ChatPostRequestModel(BaseModel):
    content: str


class ChatGetResponseModel(BaseModel):
    chat_id: str
    read_perms: list[str]
    write_perms: list[str]
    total_messages: int


class ChatMessagesResponseModel(BaseModel):
    chat_id: str
    total_messages: int
    messages: list[ChatMessageModel]


class PlayerVoteRequestModel(BaseModel):
    target: str | None


class GameVotesResponseModel(BaseModel):
    votes: dict[str, str | None]
    vote_counts: dict[str, list[str]]
    no_elim_vote_count: list[str]


class ObjectReferenceModel(BaseModel):
    name: str
    description: str | None = None
