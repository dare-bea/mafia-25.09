from datetime import datetime
from secrets import token_urlsafe
from typing import Any, Callable, Literal, cast
from itertools import count
import random

from flask import Blueprint, request
from pydantic import BaseModel, Field, field_validator
from werkzeug.datastructures import Headers
from flask_pydantic import validate  # type: ignore[import-untyped]

import mafia as m
import examples as ex

# CUSTOM EXTENSIONS #

class Game(m.Game):
    def __init__(self, *args: Any, mod_token: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if mod_token is None:
            mod_token = token_urlsafe(16)
        self.mod_token = mod_token
        self.chats["global"] = m.Chat()
        self.queued_visits: list[m.Visit] = []

    def next_phase(self) -> None:
        super().next_phase()
        self.queued_visits.clear()

r = ex.Resolver()

# PERMISSION CHECKING #

def get_permissions(game: Game, headers: Headers) -> tuple[str | None, m.Player | None]:
    mod_token: str | None = headers.get("Authorization-Mod-Token")
    player_name: str | None = headers.get("Authorization-Player-Name")
    player: m.Player | None = next((p for p in game.players if p.name == player_name), None)
    return mod_token, player

# API V1 MODELS #

ErrorResponse = tuple[dict[str, str], int]
EmptyResponse = tuple[Literal[''], int]

class GameSummaryModel(BaseModel):
    id: int
    players: list[str]
    phase: m.Phase
    day_no: int

class GameListQueryModel(BaseModel):
    start: int = 0
    limit: int = 25

class GameListResponseModel(BaseModel):
    games: list[GameSummaryModel]
    total_games: int

class RoleModel(BaseModel):
    node: Literal["role"] = "role"
    id: str

    @field_validator('id')
    def validate_id(cls, v: Any) -> Any:
        if v not in ex.ROLES:
            raise ValueError(f"id must be one of {ex.ROLES.keys()}")
        return v

    def value(self) -> type[m.Role] | Callable[..., m.Role]:
        return ex.ROLES[self.id]

class CombinedRoleModel(BaseModel):
    node: Literal["combined_role"] = "combined_role"
    id: str
    roles: list["RoleModel | ModifierModel"]
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator('id')
    def validate_id(cls, v: Any) -> Any:
        if v not in ex.COMBINED_ROLES:
            raise ValueError(f"id must be one of {ex.COMBINED_ROLES.keys()}")
        return v

    def value(self) -> Callable[..., m.Role]:
        return ex.COMBINED_ROLES[self.id](*(r.value() for r in self.roles), **self.params)

class ModifierModel(BaseModel):
    node: Literal["modifier"] = "modifier"
    id: str
    role: "RoleModel | CombinedRoleModel | ModifierModel"
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator('id')
    def validate_id(cls, v: Any) -> Any:
        if v not in ex.MODIFIERS:
            raise ValueError(f"id must be one of {ex.MODIFIERS.keys()}")
        return v

    def value(self) -> type[m.Role]:
        r = self.role.value()
        if isinstance(r, type) and issubclass(r, m.Role):
            return ex.MODIFIERS[self.id](**self.params)(r)
        else:
            return ex.MODIFIERS[self.id](**self.params)(cast(type[m.Role], type(r())))

class GameCreateRequestRole(BaseModel):
    role: RoleModel | CombinedRoleModel | ModifierModel
    alignment: str
    role_params: dict[str, Any] = Field(default_factory=dict)
    alignment_id: str | None = None
    alignment_demonym: str | Literal[''] | None = None
    alignment_role_names: dict[str, str] | None = None

    @field_validator('alignment')
    def validate_alignment(cls, v: Any) -> Any:
        if v not in ex.ALIGNMENTS:
            raise ValueError(f"alignment must be one of {ex.ALIGNMENTS.keys()}")
        return v

    def alignment_value(self) -> type[m.Alignment] | Callable[..., m.Alignment]:
        return ex.ALIGNMENTS[self.alignment]

class GameCreateRequestModel(BaseModel):
    players: list[str]
    day_no: int = 1
    phase: m.Phase = m.Phase.DAY
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
    phase: m.Phase
    players: list[ShortPlayerModel | ShortPartialPlayerModel]
    chats: list[ShortChatModel]

class GamePutRequestModel(BaseModel):
    day_no: int | None = None
    phase: m.Phase | None = None

class GamePatchRequestModel(BaseModel):
    actions: list[Literal[
        "dequeue",
        "resolve",
        "next_phase",
    ]]

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
    phase: m.Phase | None = None
    immediate: bool
    target_count: int
    targets: list[list[str]]
    queued: list[str] | None = None

class PlayerAbilitiesPassiveModel(BaseModel):
    id: str
    phase: m.Phase | None = None
    immediate: bool
    queued: bool

class PlayerAbilitiesSharedActionModel(BaseModel):
    id: str
    used_by: str | None = None
    phase: m.Phase | None = None
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
    shared_actions: dict[str, PlayerQueueAbilityModel | None] = Field(default_factory=dict)

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

# API V1 ENDPOINTS #

api = Blueprint("api_v1", __name__, url_prefix="/api/v1")
games: dict[int, Game] = {}
game_count = count(0)

@api.get("/games")
@validate()  # type: ignore[misc]
def game_list(query: GameListQueryModel) -> GameListResponseModel:
    """
    Get the list of games.
    """
    start = 0 if query.start < 0 else query.start
    limit = 25 if query.limit < 0 else query.limit
    game_result = sorted(games.items(), key=lambda x: x[0])[start : start + limit]
    return GameListResponseModel(
        games=[
            GameSummaryModel(
                id=id,
                players=[player.name for player in game.players],
                phase=game.phase,
                day_no=game.day_no,
            )
            for id, game in game_result
        ],
        total_games=len(games)
    )

@api.post("/games")
@validate()  # type: ignore[misc]
def game_create(body: GameCreateRequestModel) -> tuple[GameCreateResponseModel, int]:
    """
    Create a new game.
    """

    roles = [role for role in body.roles]

    if body.shuffle_roles:
        random.shuffle(roles)

    alignments: dict[tuple[type[m.Alignment] | Callable[..., m.Alignment], str | None], m.Alignment] = {}
    for r in roles:
        a = r.alignment_value()
        if (a, r.alignment_id) not in alignments:
            alignments[a, r.alignment_id] = a(id=r.alignment_id, demonym=r.alignment_demonym, role_names=r.alignment_role_names)

    game = Game(body.day_no, start_phase=body.phase)

    for player_name, role in zip(body.players, roles):
        game.add_player(m.Player(player_name, role.role.value()(**role.role_params), alignments[role.alignment_value(), role.alignment_id]))

    id = next(game_count)

    games[id] = game

    return GameCreateResponseModel(id=id, mod_token=game.mod_token), 201

@api.get("/games/<int:id>")
@validate()  # type: ignore[misc]
def game_get(id: int) -> GameResponseModel | ErrorResponse:
    """
    Get a game.
    """
    if id not in games:
        return {"message": "Game not found"}, 404
    game = games[id]
    mod_token, player = get_permissions(game, request.headers)
    return GameResponseModel(
        id = id,
        day_no = game.day_no,
        phase = game.phase,
        players = [
            ShortPlayerModel(
                name = p.name,
                is_alive = p.is_alive,
                role_name = p.role_name,
                role = p.role.id,
                alignment = p.alignment.id,
            )
            if mod_token == game.mod_token or player is p or not p.is_alive or (player is not None and p in player.known_players) else 
            ShortPartialPlayerModel(
                name = p.name,
                is_alive = p.is_alive,
            )
            for p in game.players
        ],
        chats = [
            ShortChatModel(
                id = chat_id,
                total_messages = len(chat),
            )
            for chat_id, chat in game.chats.items()
            if mod_token == game.mod_token or chat.has_read_perms(game, player)
        ],
    )

@api.put("/games/<int:id>")
@validate()  # type: ignore[misc]
def game_put(id: int, body: GamePutRequestModel) -> EmptyResponse | ErrorResponse:
    """
    Update a game.
    """
    if id not in games:
        return {"message": "Game not found"}, 404
    game = games[id]
    mod_token, player = get_permissions(game, request.headers)
    if mod_token is None and player is None:
        return {"message": "Not authenticated"}, 401
    if mod_token != game.mod_token:
        return {"message": "Not the moderator"}, 403
    if body.day_no is not None:
        game.day_no = body.day_no
    if body.phase is not None:
        game.phase = body.phase
    return "", 204

@api.patch("/games/<int:id>")
@validate()  # type: ignore[misc]
def game_patch(id: int, body: GamePatchRequestModel) -> EmptyResponse | ErrorResponse:
    """
    Update a game.
    """
    if id not in games:
        return {"message": "Game not found"}, 404
    game = games[id]
    mod_token, player = get_permissions(game, request.headers)
    if mod_token is None and player is None:
        return {"message": "Not authenticated"}, 401
    if mod_token != game.mod_token:
        return {"message": "Not the moderator"}, 403
    for action in body.actions:
        if action == "dequeue":
            for v in game.queued_visits:
                if v.is_active_time(game):
                    game.visits.append(v)
            game.queued_visits.clear()
        elif action == "resolve":
            for v in game.queued_visits:
                if v.is_active_time(game):
                    game.visits.append(v)
            game.queued_visits.clear()
            r.resolve_game(game)
        elif action == "next_phase":
            game.next_phase()
    return "", 204

@api.get("/games/<int:id>/players")
@validate()  # type: ignore[misc]
def game_players(id: int) -> list[ShortPlayerModel | ShortPartialPlayerModel] | ErrorResponse:
    """
    Get the players in a game.
    """
    if id not in games:
        return {"message": "Game not found"}, 404
    game = games[id]
    mod_token, player = get_permissions(game, request.headers)
    return [
        ShortPlayerModel(
            name = p.name,
            is_alive = p.is_alive,
            role_name = p.role_name,
            role = p.role.id,
            alignment = p.alignment.id,
        )
        if mod_token == game.mod_token or player is p or not p.is_alive or (player is not None and p in player.known_players) else 
        ShortPartialPlayerModel(
            name = p.name,
            is_alive = p.is_alive,
        )
        for p in game.players
    ]

@api.get("/games/<int:id>/chats")
@validate()  # type: ignore[misc]
def game_chats(id: int) -> list[ShortChatModel] | ErrorResponse:
    """
    Get the chats in a game.
    """
    if id not in games:
        return {"message": "Game not found"}, 404
    game = games[id]
    mod_token, player = get_permissions(game, request.headers)
    return [
        ShortChatModel(
            id = chat_id,
            total_messages = len(chat),
        )
        for chat_id, chat in game.chats.items()
        if mod_token == game.mod_token or chat.has_read_perms(game, player)
    ]

@api.get("/games/<int:id>/players/<string:name>")
@validate()  # type: ignore[misc]
def game_player(id: int, name: str) -> PlayerResponseModel | ErrorResponse:
    """
    Get a player in a game.
    """
    if id not in games:
        return {"message": "Game not found"}, 404
    game = games[id]
    player = next((p for p in game.players if p.name == name), None)
    if player is None:
        return {"message": "Player not found"}, 404
    mod_token, player_auth = get_permissions(game, request.headers)
    if mod_token is None and player_auth is None:
        return {"message": "Not authenticated"}, 401
    if mod_token != game.mod_token and player_auth is not player:
        return {"message": "Not the moderator or the player"}, 403
    return PlayerResponseModel(
        name = player.name,
        is_alive = player.is_alive,
        role_name = player.role_name,
        role = PlayerRAModel(
            id = player.role.id,
            actions = [a.id for a in player.actions],
            passives = [a.id for a in player.passives],
            shared_actions = [a.id for a in player.shared_actions],
        ),
        alignment = PlayerRAModel(
            id = player.alignment.id,
            actions = [a.id for a in player.alignment.actions],
            passives = [a.id for a in player.alignment.passives],
            shared_actions = [a.id for a in player.alignment.shared_actions],
        ),
        known_players = [
            ShortPlayerModel(
                name = p.name,
                is_alive = p.is_alive,
                role_name = p.role_name,
                role = p.role.id,
                alignment = p.alignment.id,
            )
            for p in player.known_players
        ],
        total_private_messages = len(player.private_messages),
        chats = [
            ShortChatModel(
                id = chat_id,
                total_messages = len(chat),
            )
            for chat_id, chat in game.chats.items()
            if chat.has_read_perms(game, player)
        ],
    )

@api.get("/games/<int:id>/players/<string:name>/abilities")
@validate()  # type: ignore[misc]
def game_player_abilities(id: int, name: str) -> PlayerAbiltiesResponseModel | ErrorResponse:
    """
    Get the abilities of a player in a game.
    """
    if id not in games:
        return {"message": "Game not found"}, 404
    game = games[id]
    player = next((p for p in game.players if p.name == name), None)
    if player is None:
        return {"message": "Player not found"}, 404
    mod_token, player_auth = get_permissions(game, request.headers)
    if mod_token is None and player_auth is None:
        return {"message": "Not authenticated"}, 401
    if mod_token != game.mod_token and player_auth is not player:
        return {"message": "Not the moderator or the player"}, 403
    return PlayerAbiltiesResponseModel(
        actions = [
            PlayerAbilitiesActionModel(
                id = a.id,
                phase = a.phase,
                immediate = a.immediate,
                target_count = a.target_count,
                targets = [
                    [t.name for t in targets]
                    for targets in ex.get_valid_targets(a, game, player)
                ] if a.target_count > 0 else [],
                queued = [t.name for t in v.targets]
                if (v := next((v for v in game.queued_visits if v.actor == player and v.ability == a), None)) is not None
                else None,
            )
            for a in player.actions
        ],
        passives = [
            PlayerAbilitiesPassiveModel(
                id = a.id,
                phase = a.phase,
                immediate = a.immediate,
                queued = a.check(game, player),
            )
            for a in player.passives
        ],
        shared_actions = [
            PlayerAbilitiesSharedActionModel(
                id = a.id,
                used_by = v.actor.name
                if (v := next((v for v in game.queued_visits if v.ability == a and v.actor.alignment == player.alignment), None)) is not None
                else None,
                phase = a.phase,
                immediate = a.immediate,
                target_count = a.target_count,
                targets = [
                    [t.name for t in targets]
                    for targets in ex.get_valid_targets(a, game, player)
                ] if a.target_count > 0 else [],
                queued = [t.name for t in v.targets]
                if (v := next((v for v in game.queued_visits if v.ability == a and v.actor.alignment == player.alignment), None)) is not None
                else None
            )
            for a in player.shared_actions
        ],
    )

@api.post("/games/<int:id>/players/<string:name>/abilities")
@validate()  # type: ignore[misc]
def game_player_queue_ability(id: int, name: str, body: PlayerQueueAbilityRequestModel) -> EmptyResponse | ErrorResponse:
    """
    Queue an ability for a player in a game.
    """
    if id not in games:
        return {"message": "Game not found"}, 404
    game = games[id]
    player = next((p for p in game.players if p.name == name), None)
    if player is None:
        return {"message": "Player not found"}, 404
    mod_token, player_auth = get_permissions(game, request.headers)
    if mod_token is None and player_auth is None:
        return {"message": "Not authenticated"}, 401
    if mod_token != game.mod_token and player_auth is not player:
        return {"message": "Not the moderator or the player"}, 403
    
    valid_players = {p.name: p for p in game.players}
    valid_actions = {a.id: a for a in player.actions}
    valid_shared_actions = {a.id: a for a in player.shared_actions}

    for ability_id, requested_visit in body.actions.items():
        if ability_id not in valid_actions:
            return {"message": f"Invalid action '{ability_id}' for player '{player.name}'"}, 400
        if requested_visit is not None:
            invalid_targets = {t for t in requested_visit.targets if t not in valid_players}
            if invalid_targets:
                return {"message": f"Invalid targets for '{ability_id}': {', '.join(invalid_targets)}"}, 400
            if not valid_actions[ability_id].check(game, player, [valid_players[t] for t in requested_visit.targets]):
                return {"message": f"Check failed for '{ability_id}': {', '.join(requested_visit.targets)}"}, 400

    for ability_id, requested_visit in body.shared_actions.items():
        if ability_id not in valid_shared_actions:
            return {"message": f"Invalid action '{ability_id}' for player '{player.name}'"}, 400
        if requested_visit is not None:
            invalid_targets = {t for t in requested_visit.targets if t not in valid_players}
            if invalid_targets:
                return {"message": f"Invalid targets for '{ability_id}': {', '.join(invalid_targets)}"}, 400
            if not valid_shared_actions[ability_id].check(game, player, [valid_players[t] for t in requested_visit.targets]):
                return {"message": f"Invalid targets for '{ability_id}'"}, 400

    for ability_id, requested_visit in body.actions.items():
        prev_visit = next((v for v in game.queued_visits if v.actor == player), None)
        if prev_visit is not None:
            game.queued_visits.remove(prev_visit)
        if requested_visit is not None:
            game.queued_visits.append(m.Visit(
                actor=player,
                targets=tuple(valid_players[t] for t in requested_visit.targets), 
                ability=valid_actions[ability_id], 
                ability_type=m.AbilityType.ACTION, 
                game=game, 
                player_inputs=tuple(requested_visit.player_inputs),
            ))

    for ability_id, requested_visit in body.shared_actions.items():
        prev_visit = next((v for v in game.queued_visits if v.ability == valid_shared_actions[ability_id] and v.actor.alignment == player.alignment), None)
        if prev_visit is not None:
            game.queued_visits.remove(prev_visit)
        if requested_visit is not None:
            game.queued_visits.append(m.Visit(
                actor=player,
                targets=tuple(valid_players[t] for t in requested_visit.targets),
                ability=valid_shared_actions[ability_id],
                ability_type=m.AbilityType.SHARED_ACTION,
                game=game,
                player_inputs=tuple(requested_visit.player_inputs)
            ))

    return "", 204

@api.get("/games/<int:id>/players/<string:name>/messages")
@validate()  # type: ignore[misc]
def game_player_messages(id: int, name: str, query: ChatQueryModel) -> PlayerPMResponseModel | ErrorResponse:
    """
    Get a player's private messages.
    """
    if id not in games:
        return {"message": "Game not found"}, 404
    game = games[id]
    player = next((p for p in game.players if p.name == name), None)
    if player is None:
        return {"message": "Player not found"}, 404
    mod_token, player_auth = get_permissions(game, request.headers)
    if mod_token is None and player_auth is None:
        return {"message": "Not authenticated"}, 401
    if mod_token != game.mod_token and not player.private_messages.has_read_perms(game, player_auth):
        return {"message": "Not the moderator or authorized player"}, 403
    start = 0 if query.start < 0 else query.start
    limit = 25 if query.limit < 0 else query.limit
    return PlayerPMResponseModel(
        total_messages = len(player.private_messages),
        messages = [
            ChatMessageModel(
                author = str(msg.sender),
                timestamp = datetime.now(),
                content = msg.content,
            )
            for idx, msg in enumerate(player.private_messages[start : start + limit])
        ]
    )

@api.post("/games/<int:id>/players/<string:name>/messages")
@validate()  # type: ignore[misc]
def game_player_send_message(id: int, name: str, body: ChatPostRequestModel) -> EmptyResponse | ErrorResponse:
    """
    Send a private message to a player.
    """
    if id not in games:
        return {"message": "Game not found"}, 404
    game = games[id]
    player = next((p for p in game.players if p.name == name), None)
    if player is None:
        return {"message": "Player not found"}, 404
    mod_token, player_auth = get_permissions(game, request.headers)
    if mod_token is None and player_auth is None:
        return {"message": "Not authenticated"}, 401
    if mod_token != game.mod_token and player.private_messages.has_write_perms(game, player_auth):
        return {"message": "Not the moderator or authorized player"}, 403
    player.private_messages.send(player_auth.name if player_auth is not None else "Moderator", body.content)
    return "", 204

@api.get("/games/<int:id>/chats/<string:chat_id>")
@validate()  # type: ignore[misc]
def game_chat(id: int, chat_id: str) -> ChatGetResponseModel | ErrorResponse:
    """
    Get a chat in a game.
    """
    if id not in games:
        return {"message": "Game not found"}, 404
    game = games[id]
    mod_token, player = get_permissions(game, request.headers)
    chat = game.chats.get(chat_id)
    read_perms = False if chat is None else chat.has_read_perms(game, player)
    if mod_token is None and player is None and not read_perms:
        return {"message": "Not authenticated"}, 401
    if chat is None or (mod_token != game.mod_token and not read_perms):
        return {"message": "Chat not found"}, 404
    return ChatGetResponseModel(
        chat_id = chat_id,
        read_perms = [p.name for p in chat.read_perms(game)],
        write_perms = [p.name for p in chat.write_perms(game)],
        total_messages = len(chat)
    )

@api.get("/games/<int:id>/chats/<string:chat_id>/messages")
@validate()  # type: ignore[misc]
def game_chat_messages(id: int, chat_id: str, query: ChatQueryModel) -> ChatMessagesResponseModel | ErrorResponse:
    """
    Get the messages in a chat.
    """
    if id not in games:
        return {"message": "Game not found"}, 404
    game = games[id]
    mod_token, player = get_permissions(game, request.headers)
    chat = game.chats.get(chat_id)
    read_perms = False if chat is None else chat.has_read_perms(game, player)
    if mod_token is None and player is None and not read_perms:
        return {"message": "Not authenticated"}, 401
    if chat is None or (mod_token != game.mod_token and not read_perms):
        return {"message": "Chat not found"}, 404
    start = 0 if query.start < 0 else query.start
    limit = 25 if query.limit < 0 else query.limit
    return ChatMessagesResponseModel(
        chat_id = chat_id,
        total_messages = len(chat),
        messages = [
            ChatMessageModel(
                author = str(msg.sender),
                timestamp = datetime.now(),
                content = msg.content,
            )
            for idx, msg in enumerate(chat[start : start + limit])
        ],
    )

@api.post("/games/<int:id>/chats/<string:chat_id>")
@api.post("/games/<int:id>/chats/<string:chat_id>/messages")
@validate()  # type: ignore[misc]
def game_chat_send_message(id: int, chat_id: str, body: ChatPostRequestModel) -> EmptyResponse | ErrorResponse:
    """
    Send a message to a chat.
    """
    if id not in games:
        return {"message": "Game not found"}, 404
    game = games[id]
    mod_token, player = get_permissions(game, request.headers)
    chat = game.chats.get(chat_id)
    read_perms = False if chat is None else chat.has_read_perms(game, player)
    write_perms = False if chat is None else chat.has_write_perms(game, player)
    if mod_token is None and player is None and not read_perms and not write_perms:
        return {"message": "Not authenticated"}, 401
    if chat is None or (mod_token != game.mod_token and not read_perms):
        return {"message": "Chat not found"}, 404
    if mod_token != game.mod_token and not write_perms:
        return {"message": "Not the moderator or player authorized to write to this chat"}, 403
    chat.send(player.name if player is not None else "Moderator", body.content)
    return "", 204
