# from __future__ import annotations

from secrets import token_urlsafe
from typing import Any, Callable, Literal
from itertools import count
import random

from flask import Blueprint, request
# from flask.typing import ResponseReturnValue as RRV
from pydantic import BaseModel, Field, field_validator
from werkzeug.datastructures import Headers
from flask_pydantic import validate

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
    type: Literal["role"] = "role"
    id: str

    @field_validator('id')
    def validate_id(cls, v: Any) -> Any:
        if v not in ex.ROLES:
            raise ValueError(f"id must be one of {ex.ROLES.keys()}")
        return v

    def value(self) -> Callable:
        return ex.ROLES[self.id]

class CombinedRoleModel(BaseModel):
    type: Literal["combined_role"] = "combined_role"
    id: str
    roles: list["RoleModel | ModifierModel"]
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator('id')
    def validate_id(cls, v: Any) -> Any:
        if v not in ex.COMBINED_ROLES:
            raise ValueError(f"id must be one of {ex.COMBINED_ROLES.keys()}")
        return v

    def value(self) -> Callable:
        return ex.COMBINED_ROLES[self.id](*(r.value() for r in self.roles), **self.params)

class ModifierModel(BaseModel):
    type: Literal["modifier"] = "modifier"
    id: str
    role: "RoleModel | CombinedRoleModel | ModifierModel"
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator('id')
    def validate_id(cls, v: Any) -> Any:
        if v not in ex.MODIFIERS:
            raise ValueError(f"id must be one of {ex.MODIFIERS.keys()}")
        return v

    def value(self) -> Callable:
        return ex.MODIFIERS[self.id](**self.params)(self.role.value())

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

    def alignment_value(self) -> Callable:
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

class PlayerModel(BaseModel):
    name: str
    is_alive: bool
    role_name: str | None = None
    role: str | None = None
    alignment: str | None = None

class ChatModel(BaseModel):
    id: str
    message_count: int

class GameResponseModel(BaseModel):
    id: int
    day_no: int
    phase: m.Phase
    players: list[PlayerModel]
    chats: list[ChatModel]

class GamePutRequestModel(BaseModel):
    day_no: int | None = None
    phase: m.Phase | None = None

class GamePatchRequestModel(BaseModel):
    actions: list[Literal[
        "dequeue",
        "resolve",
        "next_phase",
    ]]

# API V1 ENDPOINTS #

api = Blueprint("api_v1", __name__, url_prefix="/api/v1")
games: dict[int, Game] = {}
game_count = count(0)

@api.get("/games")
@validate()
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
@validate()
def game_create(body: GameCreateRequestModel) -> tuple[GameCreateResponseModel, int]:
    """
    Create a new game.
    """

    roles = [role for role in body.roles]

    if body.shuffle_roles:
        random.shuffle(roles)

    alignments: dict[tuple[Callable, str | None], m.Alignment] = {}
    for r in roles:
        a = r.alignment_value()
        if (a, r.alignment_id) not in alignments:
            alignments[a, r.alignment_id] = a(id=r.alignment_id, demonym=r.alignment_demonym, role_names=r.alignment_role_names)

    game = Game(body.day_no, body.phase)

    for player_name, role in zip(body.players, roles):
        game.add_player(m.Player(player_name, role.role.value()(**role.role_params), alignments[role.alignment_value(), role.alignment_id]))

    id = next(game_count)

    games[id] = game

    return GameCreateResponseModel(id=id, mod_token=game.mod_token), 201

@api.get("/games/<int:id>")
@validate()
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
            PlayerModel(
                name = p.name,
                is_alive = p.is_alive,
                role_name = p.role_name,
                role = p.role.id,
                alignment = p.alignment.id,
            )
            if mod_token == game.mod_token or player is p or not p.is_alive or (player is not None and p in player.known_players) else 
            PlayerModel(
                name = p.name,
                is_alive = p.is_alive,
            )
            for p in game.players
        ],
        chats = [
            ChatModel(
                id = chat_id,
                message_count = len(chat),
            )
            for chat_id, chat in game.chats.items()
            if mod_token == game.mod_token or chat.has_read_perms(game, player)
        ],
    )

@api.put("/games/<int:id>")
@validate()
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
@validate()
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
            r.resolve_game(game)
        elif action == "next_phase":
            game.next_phase()
    return "", 204

# TESTING #

if __name__ == "__main__":
    d = {
        "players": ["Alice", "Bob", "Eve"],
        "roles": [
            # Vanilla Townie
            {
                "role": {
                    "type": "role",
                    "id": "Vanilla"
                },
                "alignment": "Town"
            },
            # Town JoAT Doctor Cop
            {
                "role": {
                    "type": "combined_role",
                    "id": "Jack_of_All_Trades",
                    "roles": [
                        {
                            "type": "role",
                            "id": "Doctor"
                        },
                        {
                            "type": "role",
                            "id": "Cop"
                        }
                    ]
                },
                "alignment": "Town"
            },
            # Mafia 1-Shot Juggernaut
            {
                "role": {
                    "type": "modifier",
                    "id": "XShot",
                    "params": {
                        "max_uses": 1
                    },
                    "role": {
                        "type": "role",
                        "id": "Juggernaut"
                    }
                },
                "alignment": "Mafia"
            },
        ]
    }
    GameCreateRequestModel.model_validate(d)
    print("Validated!")

    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(api)

    with app.test_client() as client:
        response = client.post("/api/v1/games", json=d)
        print(response.status_code, response.json, "\n")

        if response.json is not None:
            response2 = client.get(f"/api/v1/games/{response.json['id']}")
            print(response2.status_code, response2.json, "\n")

            response2 = client.get(f"/api/v1/games/{response.json['id']}", headers={"Authorization-Mod-Token": response.json['mod_token']})
            print(response2.status_code, response2.json, "\n")

            response2 =  client.get(f"/api/v1/games/{response.json['id']}", headers={"Authorization-Player-Name": "Alice"})
            print(response2.status_code, response2.json, "\n")

            response2 =  client.get(f"/api/v1/games/{response.json['id'] + 1}")
            print(response2.status_code, response2.json, "\n")