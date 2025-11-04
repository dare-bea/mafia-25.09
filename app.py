from __future__ import annotations

import re
from itertools import count
import random
from secrets import token_urlsafe
from typing import Any

from flask import Flask, render_template_string, request
from markupsafe import Markup
from werkzeug.datastructures import Headers

import mafia as m
import examples as ex

# CUSTOM EXTENSIONS #


class Game(m.Game):
    def __init__(self, *args, mod_token: str | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if mod_token is None:
            mod_token = token_urlsafe(16)
        self.mod_token = mod_token
        self.chats["global"] = m.Chat()
        self.queued_visits: list[m.Visit] = []


r = ex.Resolver()

# JINJA2 HELPERS #


def slugify(obj: object) -> str:
    return re.sub(r"\s", "-", str(obj))


def role(player: m.Player) -> Markup:
    return Markup(
        render_template_string(
            '<span class="role_name Alignment-{{ player.alignment |e|s }}">'
            "{{ player.role_name |e}}</span>",
            player=player,
        )
    )


app = Flask(__name__)

app.jinja_env.filters.update(
    dict(
        s=slugify,
        slugify=slugify,
        role=role,
    )
)

# API V0 ENDPOINTS #


def get_permissions(game: Game, headers: Headers) -> tuple[str | None, m.Player | None]:
    mod_token: str | None = headers.get("Authorization-Mod-Token")
    player_name: str | None = headers.get("Authorization-Player-Name")
    player: m.Player | None = next((p for p in game.players if p.name == player_name), None)
    return mod_token, player


@app.get("/api/v0/games")
def api_v0_games() -> Any:
    """
    Get a list of games.

    Authorization: None

    Response Body:
    * `games`: `object[]`
        * `game_id`: `int`
        * `players`: `string[]`
        * `phase`: `PHASE`
        * `day_no`: `int`

    Status Codes:
    * 200 OK
    """
    return {
        "games": [
            {
                "id": id,
                "players": [player.name for player in game.players],
                "phase": game.phase.name,
                "day_no": game.day_no,
            }
            for id, game in games.items()
        ]
    }


@app.post("/api/v0/games")
def api_v0_create_game() -> Any:
    """Create a new game.

    Authorization: None

    Request Body:
    * `players`: `string[]`
    * `roles`: `object[]`
        * `role`: `string`
        * `alignment`: `string`
    * `start_day`: `int` (default: `1`)
    * `start_phase`: `PHASE` (default: `"DAY"`)
    * `shuffle_roles`: `bool` (default: `true`)

    Response Body:
    * `game_id`: `int`
    * `mod_token`: `string`

    Status Codes:
    * 201 Created
    * 400 Bad Request
    * 415 Unsupported Media Type
    ```
    """
    body = request.get_json()

    # Body validation
    if body is None:
        return {"message": "Request body is not JSON"}, 415
    if not isinstance(body, dict):
        return {"message": "Request body is not a JSON object"}, 400

    # Field existence validation
    if "players" not in body:
        return {"message": "Missing 'players' field"}, 400
    if "roles" not in body:
        return {"message": "Missing 'roles' field"}, 400

    body.setdefault("start_day", 1)
    body.setdefault("start_phase", m.Phase.DAY.name)
    body.setdefault("shuffle_roles", True)

    # Field type validation
    if not isinstance(body["players"], list):
        return {"message": "'players' field is not a list"}, 400
    if not isinstance(body["roles"], list):
        return {"message": "'roles' field is not a list"}, 400
    if not isinstance(body["start_day"], int):
        return {"message": "'start_day' field is not an integer"}, 400
    if not isinstance(body["shuffle_roles"], bool):
        return {"message": "'shuffle_roles' field is not a boolean"}, 400

    # Field member type validation
    if not all(isinstance(player, str) for player in body["players"]):
        return {"message": "'players' field contains non-string values"}, 400
    if not all(isinstance(role, dict) for role in body["roles"]):
        return {"message": "'roles' field contains non-object values"}, 400
    if not all("role" in role and "alignment" in role for role in body["roles"]):
        return {
            "message": "'roles' field contains objects missing 'role' or 'alignment' fields"
        }, 400
    if not all(isinstance(role["role"], str) for role in body["roles"]):
        return {"message": "'roles' field contains objects with non-string 'role' fields"}, 400
    if not all(isinstance(role["alignment"], str) for role in body["roles"]):
        return {
            "message": "'roles' field contains objects with non-string 'alignment' fields"
        }, 400

    # Field value validation
    if len(body["players"]) != len(body["roles"]):
        return {"message": "'players' and 'roles' fields have different lengths"}, 400
    try:
        phase: m.Phase = m.Phase(body["start_phase"])
    except ValueError:
        try:
            phase = m.Phase[body["start_phase"]]
        except KeyError:
            return {
                "message": f"'start_phase' field is not a valid phase: {body['start_phase']}"
            }, 400

    # Create game
    role_list = []
    roles: dict[str, type[m.Role]] = {}
    alignments: dict[str, m.Alignment] = {}

    for role_align in body["roles"]:
        role_name = role_align["role"]
        alignment_name = role_align["alignment"]
        if role_name not in roles:
            role_type = ex.ROLES.get(role_name)
            if role_type is None:
                return {"message": f"Role '{role_name}' does not exist"}, 400
            roles[role_name] = role_type
        else:
            role_type = roles[role_name]
        if alignment_name not in alignments:
            alignment_type = ex.ALIGNMENTS.get(alignment_name)
            if alignment_type is None:
                return {"message": f"Alignment '{alignment_name}' does not exist"}, 400
            alignment = alignment_type()
            alignments[alignment_name] = alignment
        else:
            alignment = alignments[alignment_name]
        role_list.append((role_type(), alignment))

    if body["shuffle_roles"]:
        random.shuffle(role_list)

    if "mod_token" in body:
        game = Game(body["start_day"], phase, mod_token=body["mod_token"])
    else:
        game = Game(body["start_day"], phase)
    game.chats["global"].send("System", "Welcome to the game!")
    for player_name, (role, alignment) in zip(body["players"], role_list):
        game.add_player(m.Player(player_name, role, alignment))

    id = next(game_count)
    games[id] = game
    return {"game_id": id, "mod_token": game.mod_token}, 201


@app.get("/api/v0/games/<int:id>")
def api_v0_get_game(id: int) -> Any:
    """Get game overview.

    Authorization: None (Moderators/Players get extra information)

    Response Body:
    * `game_id`: `int`
    * `day_no`: `int`
    * `phase`: `PHASE`
    * `players`: `object[]`
        * `name`: `string`
        * `is_alive`: `bool`
        * `role_name`: `string?`
        * `role`: `string?`
        * `alignment`: `string?`
    * `chats`: `object[]`
        * `id`: `string`
        * `message_count`: `int`

    Status Codes:
    * 200 OK
    * 404 Not Found
    """

    if id not in games:
        return {"message": "Game not found"}, 404

    game = games[id]

    """Headers:
    * Authorization-Player-Name
    * Authorization-Mod-Token
    """  # Get permissions
    mod_token, player = get_permissions(game, request.headers)
    is_mod = mod_token == game.mod_token

    return {
        "game_id": id,
        "day_no": game.day_no,
        "phase": game.phase.name,
        "players": [
            {
                "name": p.name,
                "is_alive": p.is_alive,
                "role_name": p.role_name,
                "role_name_html": role(p),
                "role": p.role.id,
                "alignment": p.alignment.id,
            }
            if is_mod
            or not p.is_alive
            or (player is not None and (p == player or p in player.known_players))
            else {"name": p.name, "is_alive": p.is_alive}
            for p in game.players
        ],
        "chats": [
            {
                "id": id,
                "message_count": len(chat),
            }
            for id, chat in game.chats.items()
            if chat.has_read_perms(game, player)
        ],
    }


@app.put("/api/v0/games/<int:id>")
def api_v0_update_game(id: int) -> Any:
    """Update game data.

    Authorization: Moderator

    Request Body:
    * `day_no`: `int` (default: `1`)
    * `phase`: `PHASE` (default: `"DAY"`)

    Status Codes:
    * 204 No Content
    * 400 Bad Request
    * 401 Unauthorized
    * 403 Forbidden
    * 404 Not Found
    * 415 Unsupported Media Type
    """
    if id not in games:
        return {"message": "Game not found"}, 404

    game = games[id]
    mod_token, player = get_permissions(game, request.headers)
    if mod_token is None and player is None:
        return {"message": "Not authenticated"}, 401
    if mod_token != game.mod_token:
        return {"message": "Not the moderator"}, 403

    body = request.get_json()
    if body is None:
        return {"message": "Request body is not JSON"}, 415
    if not isinstance(body, dict):
        return {"message": "Request body is not a JSON object"}, 400

    body.setdefault("day_no", game.day_no)
    body.setdefault("phase", game.phase.name)

    if not isinstance(body["day_no"], int):
        return {"message": "'day_no' field is not an integer"}, 400
    try:
        phase: m.Phase = m.Phase(body["phase"])
    except ValueError:
        try:
            phase = m.Phase[body["start_phase"]]
        except KeyError:
            return {
                "message": f"'start_phase' field is not a valid phase: {body['start_phase']}"
            }, 400

    game.day_no = body["day_no"]
    game.phase = phase
    return "", 204


@app.patch("/api/v0/games/<int:id>")
def api_v0_patch_game(id: int) -> Any:
    """Update game data.

    Authorization: Moderator

    Request Body:
    * `actions`: An array containing any number of the following strings:
        * `"dequeue"` - Dequeue all queued visits.
        * `"resolve"` - Resolve the game.
        * `"next_phase"` - Will advance game phase/day.
    """

    if id not in games:
        return {"message": "Game not found"}, 404
    game = games[id]
    mod_token, player = get_permissions(game, request.headers)
    if mod_token is None and player is None:
        return {"message": "Not authenticated"}, 401
    if mod_token != game.mod_token:
        return {"message": "Not the moderator"}, 403
    body = request.get_json()
    if body is None:
        return {"message": "Request body is not JSON"}, 415
    if not isinstance(body, dict):
        return {"message": "Request body is not a JSON object"}, 400
    if "actions" not in body:
        return {"message": "Missing 'actions' field"}, 400
    if not isinstance(body["actions"], list):
        return {"message": "'actions' field is not a list"}, 400
    if not all(isinstance(action, str) for action in body["actions"]):
        return {"message": "'actions' field contains non-string values"}, 400
    if "dequeue" in body["actions"]:
        for v in game.queued_visits:
            if v.is_active_time(game):
                game.visits.append(v)
    if "resolve" in body["actions"]:
        r.resolve_game(game)
    if "next_phase" in body["actions"]:
        if game.phase == m.Phase.DAY:
            game.phase = m.Phase.NIGHT
        else:
            game.phase = m.Phase.DAY
            game.day_no += 1
    return "", 204


@app.get("/api/v0/games/<int:game_id>/players")
def api_v0_get_players(game_id: int) -> Any:
    """Get an array of players.

    Returns `"players"` field from using `GET /api/v0/games/{game_id}`."""
    if game_id not in games:
        return {"message": "Game not found"}, 404

    return api_v0_get_game(game_id)["players"]


@app.get("/api/v0/games/<int:game_id>/players/<string:name>")
def api_v0_get_player(game_id: int, name: str) -> Any:
    """Get player-specific information.

    Authorization: Player (Self), Moderator

    Response Body:
    * `name`: `string`
    * `is_alive`: `bool`
    * `role_name`: `string`
    * `role`: `object`
        * `id`: `string`
        * `actions`: `string[]`
        * `passives`: `string[]`
        * `shared_actions`: `string[]`
    * `alignment`: `object`
        * `id`: `string`
        * `actions`: `string[]`
        * `passives`: `string[]`
        * `shared_actions`: `string[]`
    * `known_players`: `object[]`
        * `name`: `string`
        * `is_alive`: `bool`
        * `role_name`: `string`
        * `role`: `string`
        * `alignment`: `string`
    * `private_messages`: `object`
        * `message_count`: `int`

    Status Codes:
    * 200 OK
    * 401 Unauthorized
    * 403 Forbidden
    * 404 Not Found
    """

    if game_id not in games:
        return {"message": "Game not found"}, 404

    game = games[game_id]
    player = next((p for p in game.players if p.name == name), None)
    if player is None:
        return {"message": "Player not found"}, 404
    mod_token, auth_player = get_permissions(game, request.headers)
    is_mod = mod_token == game.mod_token
    if mod_token is None and auth_player is None:
        return {"message": "Not authenticated"}, 401
    if not is_mod and auth_player is None:
        return {"message": "Not the moderator"}, 403
    if not is_mod and auth_player is not player:
        return {"message": "Not your player"}, 403

    return {
        "name": player.name,
        "is_alive": player.is_alive,
        "role_name": player.role_name,
        "role_name_html": role(player),
        "role": {
            "id": player.role.id,
            "actions": [a.id for a in player.actions],
            "passives": [a.id for a in player.passives],
            "shared_actions": [a.id for a in player.shared_actions],
        },
        "alignment": {
            "id": player.alignment.id,
            "actions": [a.id for a in player.alignment.actions],
            "passives": [a.id for a in player.alignment.passives],
            "shared_actions": [a.id for a in player.alignment.shared_actions],
        },
        "known_players": [
            {
                "name": p.name,
                "is_alive": p.is_alive,
                "role_name": p.role_name,
                "role_name_html": role(p),
                "role": p.role.id,
                "alignment": p.alignment.id,
            }
            for p in player.known_players
        ],
        "private_messages": {
            "message_count": len(player.private_messages),
        },
    }


@app.get("/api/v0/games/<int:game_id>/players/<string:name>/abilities")
def api_v0_get_abilities(game_id: int, name: str) -> Any:
    """Get a list of abilities a player has.

    Authorization: Player (Self), Moderator

    Response Body:
    * `actions`: `object[]`
        * `id`: `string`
        * `owner`: `string | null`
        * `phase`: `PHASE | null`
        * `immediate`: `bool`
        * `target_count`: `int`
        * `targets`: `string[][]` &mdash; list of valid targets
        * `queued`: `string[] | null` &mdash; the queued targets of the action
    * `shared_actions`: `object[]`
        * `id`: `string`
        * `owner`: `string | null`
        * `used_by`: `string | null` &mdash; who is currently queuing the action
        * `phase`: `PHASE | null`
        * `immediate`: `bool`
        * `target_count`: `int`
        * `targets`: `string[][]` &mdash; list of valid targets
        * `queued`: `string[] | null` &mdash; the queued targets of the action
    * `passives`: `object[]`
        * `id`: `string`
        * `owner`: `string | null`
        * `phase`: `PHASE | null`
        * `immediate`: `bool`
        * `queued`: `bool` &mdash; is this passive being used this phase

    Status Codes:
    * 200 OK
    * 401 Unauthorized
    * 403 Forbidden
    * 404 Not Found
    """

    if game_id not in games:
        return {"message": "Game not found"}, 404
    game = games[game_id]
    player = next((p for p in game.players if p.name == name), None)
    if player is None:
        return {"message": "Player not found"}, 404
    mod_token, auth_player = get_permissions(game, request.headers)
    is_mod = mod_token == game.mod_token
    if mod_token is None and auth_player is None:
        return {"message": "Not authenticated"}, 401
    if not is_mod and auth_player is None:
        return {"message": "Not the moderator"}, 403
    if not is_mod and auth_player is not player:
        return {"message": "Not your player"}, 403
    return {
        "actions": [
            {
                "id": a.id,
                "phase": a.phase.name if a.phase is not None else None,
                "immediate": a.immediate,
                "target_count": a.target_count,
                "targets": [
                    [t.name for t in targets] for targets in ex.get_valid_targets(a, game, player)
                ]
                if a.target_count > 0
                else [],
                "queued": [t.name for t in v]
                if (
                    v := next(
                        (
                            v.targets
                            for v in game.queued_visits
                            if v.actor == player and v.ability == a
                        ),
                        None,
                    )
                )
                is not None
                else None,
            }
            for a in player.actions
        ],
        "shared_actions": [
            {
                "id": a.id,
                "used_by": visit.actor.name
                if (visit := next((v for v in game.queued_visits if v.ability is a), None))
                is not None
                else None,
                "phase": a.phase.name if a.phase is not None else None,
                "immediate": a.immediate,
                "target_count": a.target_count,
                "targets": [
                    [t.name for t in targets] for targets in ex.get_valid_targets(a, game, player)
                ]
                if a.target_count > 0
                else [],
                "queued": [t.name for t in v]
                if (v := next((v.targets for v in game.queued_visits if v.ability == a), None))
                is not None
                else None,
            }
            for a in player.shared_actions
        ],
        "passives": [
            {
                "id": a.id,
                "phase": a.phase.name if a.phase is not None else None,
                "immediate": a.immediate,
                "queued": a.check(game, player),
            }
            for a in player.passives
        ],
    }


@app.post("/api/v0/games/<int:game_id>/players/<string:name>/abilities")
def api_v0_queue_ability(game_id: int, name: str) -> Any:
    """Queue an action.

    Authorization: Player (Self), Moderator

    Request Body:
    * `actions`: `object?`
        * (Action Id): `string[] | null` &mdash; Action targets
    * `shared_actions`: `object?`
        * (Action Id): `string[] | null` &mdash; Action targets

    Status Codes:
    * 204 No Content
    * 400 Bad Request
    * 401 Unauthorized
    * 403 Forbidden
    * 404 Not Found
    * 415 Unsupported Media Type"""

    if game_id not in games:
        return {"message": "Game not found"}, 404
    game = games[game_id]
    player = next((p for p in game.players if p.name == name), None)
    if player is None:
        return {"message": "Player not found"}, 404
    mod_token, auth_player = get_permissions(game, request.headers)
    is_mod = mod_token == game.mod_token
    if mod_token is None and auth_player is None:
        return {"message": "Not authenticated"}, 401
    if not is_mod and auth_player is None:
        return {"message": "Not the moderator"}, 403
    if not is_mod and auth_player is not player:
        return {"message": "Not your player"}, 403
    body = request.get_json()
    if body is None:
        return {"message": "Request body is not JSON"}, 415
    if not isinstance(body, dict):
        return {"message": "Request body is not a JSON object"}, 400
    body.setdefault("actions", {})
    body.setdefault("shared_actions", {})
    if not isinstance(body["actions"], dict):
        return {"message": "'actions' field is not a JSON object"}, 400
    if not isinstance(body["shared_actions"], dict):
        return {"message": "'shared_actions' field is not a JSON object"}, 400

    # Check all actions
    for action_id, target_list in body["actions"].items():
        ability = next((a for a in player.actions if a.id == action_id), None)
        if ability is None:
            return {"message": f"'actions[{action_id!r}]' field contains invalid action id"}, 400
        if target_list is None:
            # Remove action from queue
            prev_visit = next(
                (v for v in game.queued_visits if v.actor is player and v.ability is ability), None
            )
            if prev_visit is not None:
                game.queued_visits.remove(prev_visit)
            continue
        if not isinstance(target_list, list):
            return {"message": f"'actions[{action_id!r}]' field is not a list"}, 400
        if not all(isinstance(target, str) for target in target_list):
            return {"message": f"'actions[{action_id!r}]' field contains non-string values"}, 400
        targets = []
        for target_name in target_list:
            target = next((p for p in game.players if p.name == target_name), None)
            if target is None:
                return {
                    "message": f"'actions[{action_id!r}]' field contains invalid player name: {target_name}"
                }, 400
            targets.append(target)
        if ability.phase is not None and ability.phase != game.phase:
            return {
                "message": f"'actions[{action_id!r}]' field contains action with non-current phase"
            }, 400
        if not ability.check(game, player, targets):
            return {
                "message": f"'actions[{action_id!r}]' field contains failed check with targets {target_list!r}"
            }, 400
        if ability.immediate:
            ability.perform(
                game,
                player,
                targets,
                visit=m.Visit(
                    actor=player,
                    targets=tuple(targets),
                    ability=ability,
                    ability_type=m.AbilityType.ACTION,
                    game=game,
                ),
            )
            continue
        prev_visit = next(
            (v for v in game.queued_visits if v.actor is player and v.ability is ability), None
        )
        if prev_visit is not None:
            game.queued_visits.remove(prev_visit)
        game.queued_visits.append(
            m.Visit(
                actor=player,
                targets=tuple(targets),
                ability=ability,
                ability_type=m.AbilityType.ACTION,
                game=game,
            )
        )
    for action_id, target_list in body["shared_actions"].items():
        ability = next((a for a in player.shared_actions if a.id == action_id), None)
        if ability is None:
            return {
                "message": f"'shared_actions[{action_id!r}]' field contains invalid action id"
            }, 400
        if target_list is None:
            # Remove action from queue
            prev_visit = next(
                (v for v in game.queued_visits if v.ability is ability),
                None,
            )
            if prev_visit is not None:
                game.queued_visits.remove(prev_visit)
            continue
        if not isinstance(target_list, list):
            return {"message": f"'shared_actions[{action_id!r}]' field is not a list"}, 400
        if not all(isinstance(target, str) for target in target_list):
            return {
                "message": f"'shared_actions[{action_id!r}]' field contains non-string values"
            }, 400
        targets = []
        for target_name in target_list:
            target = next((p for p in game.players if p.name == target_name), None)
            if target is None:
                return {
                    "message": f"'shared_actions[{action_id!r}]' field contains invalid player name: {target_name}"
                }, 400
            targets.append(target)
        if ability.phase is not None and ability.phase != game.phase:
            return {
                "message": f"'shared_actions[{action_id!r}]' field contains action with non-current phase"
            }, 400
        if not ability.check(game, player, targets):
            return {
                "message": f"'shared_actions[{action_id!r}]' field contains failed check with targets {target_list!r}"
            }, 400
        if ability.immediate:
            ability.perform(
                game,
                player,
                targets,
                visit=m.Visit(
                    actor=player,
                    targets=tuple(targets),
                    ability=ability,
                    ability_type=m.AbilityType.SHARED_ACTION,
                    game=game,
                ),
            )
            continue
        prev_visit = next(
            (v for v in game.queued_visits if v.ability is ability),
            None,
        )
        if prev_visit is not None:
            game.queued_visits.remove(prev_visit)
        game.queued_visits.append(
            m.Visit(
                actor=player,
                targets=tuple(targets),
                ability=ability,
                ability_type=m.AbilityType.SHARED_ACTION,
                game=game,
            )
        )
    return "", 204


@app.get("/api/v0/games/<int:game_id>/players/<string:name>/messages")
def api_v0_get_messages(game_id: int, name: str) -> Any:
    """Get a player's private messages (zero-indexed).

    Authorization: Player (Self), Moderator

    URL Parameters:
    * `start`: `int` (default: `0`)
    * `limit`: `int` (default: `25`)

    Response Body:
    * `total_messages`: `int`
    * `messages`: `object[]`
        * `author`: `string`
        * `timestamp`: `int`
        * `content`: `string`

    Status Codes:
    * 200 OK
    * 401 Unauthorized
    * 403 Forbidden
    * 404 Not Found &mdash; unlike with private chats, all players have private messages, even if they don't use it, so we do not return 404 if unauthorized."""
    if game_id not in games:
        return {"message": "Game not found"}, 404
    game = games[game_id]
    player = next((p for p in game.players if p.name == name), None)
    if player is None:
        return {"message": "Player not found"}, 404
    mod_token, auth_player = get_permissions(game, request.headers)
    is_mod = mod_token == game.mod_token
    if mod_token is None and auth_player is None:
        return {"message": "Not authenticated"}, 401
    if not is_mod and auth_player is None:
        return {"message": "Not the moderator"}, 403
    if not is_mod and auth_player is not player:
        return {"message": "Not your player"}, 403
    start = request.args.get("start", 0)
    limit = request.args.get("limit", 25)
    if not isinstance(start, int):
        return {"message": "'start' field is not an integer"}, 400
    if not isinstance(limit, int):
        return {"message": "'limit' field is not an integer"}, 400
    return {
        "total_messages": len(player.private_messages),
        "messages": [
            {
                "author": msg.sender,
                "timestamp": idx,
                "content": msg.content,
            }
            for idx, msg in enumerate(player.private_messages[start : start + limit])
        ],
    }


@app.post("/api/v0/games/<int:game_id>/players/<string:name>/messages")
def api_v0_send_message(game_id: int, name: str) -> Any:
    """Send a private message to a player.

    Authorization: Player (Self), Moderator

    Request Body:
    * `content`: `string`

    Status Codes:
    * 204 No Content
    * 400 Bad Request
    * 401 Unauthorized
    * 403 Forbidden
    * 404 Not Found
    * 415 Unsupported Media Type
    """
    if game_id not in games:
        return {"message": "Game not found"}, 404
    game = games[game_id]
    player = next((p for p in game.players if p.name == name), None)
    if player is None:
        return {"message": "Player not found"}, 404
    mod_token, auth_player = get_permissions(game, request.headers)
    is_mod = mod_token == game.mod_token
    if mod_token is None and auth_player is None:
        return {"message": "Not authenticated"}, 401
    if not is_mod and auth_player is None:
        return {"message": "Not the moderator"}, 403
    if not is_mod and auth_player is not player:
        return {"message": "Not your player"}, 403
    body = request.get_json()
    if body is None:
        return {"message": "Request body is not JSON"}, 415
    if not isinstance(body, dict):
        return {"message": "Request body is not a JSON object"}, 400
    if "content" not in body:
        return {"message": "Missing 'content' field"}, 400
    if not isinstance(body["content"], str):
        return {"message": "'content' field is not a string"}, 400
    player.private_messages.send(
        auth_player.name if auth_player is not None else "Moderator", body["content"]
    )


@app.get("/api/v0/games/<int:game_id>/chats")
def api_v0_get_chats(game_id: int) -> Any:
    """Get an array of chats.

    Returns `"chats"` field from using `GET /api/v0/games/{game_id}`.
    """
    if game_id not in games:
        return {"message": "Game not found"}, 404
    return api_v0_get_game(game_id)["chats"]


@app.get("/api/v0/games/<int:game_id>/chats/<string:chat_id>")
def api_v0_get_chat(game_id: int, chat_id: str) -> Any:
    """Get a chat's data.

    Authorization: None (Public Chats), Player (Read Perms), Moderator

    Response Body:
    * `chat_id`: `string`
    * `read_perms`: `string[]`
    * `write_perms`: `string[]`
    * `total_messages`: `int`

    Status Codes:
    * 200 OK
    * 404 Not Found &mdash; Returned in place of 401 or 403 for those without read permissions.
    """
    if game_id not in games:
        return {"message": "Game not found"}, 404
    game = games[game_id]
    chat = game.chats.get(chat_id)
    if chat is None:
        return {"message": "Chat not found"}, 404
    mod_token, player = get_permissions(game, request.headers)
    is_mod = mod_token == game.mod_token
    if not is_mod and not chat.has_read_perms(game, player):
        return {"message": "Chat not found"}, 404
    return {
        "chat_id": chat_id,
        "read_perms": [p.name for p in chat.read_perms(game)],
        "write_perms": [p.name for p in chat.write_perms(game)],
        "total_messages": len(chat),
    }


@app.get("/api/v0/games/<int:game_id>/chats/<string:chat_id>/messages")
def api_v0_get_chat_messages(game_id: int, chat_id: str) -> Any:
    """Get chat messages (zero-indexed).

    Authorization: None (Public Chats), Player (Read Perms), Moderator

    URL Parameters:
    * `start`: `int` (default: `0`)
    * `limit`: `int` (default: `25`)

    Response Body:
    * `chat_id`: `string`
    * `total_messages`: `int`
    * `messages`: `object[]`
        * `author`: `string`
        * `timestamp`: `int`
        * `content`: `string`

    Status Codes:
    * 200 OK
    * 404 Not Found &mdash; Returned in place of 401 or 403 for those without read permissions.
    """
    if game_id not in games:
        return {"message": "Game not found"}, 404
    game = games[game_id]
    chat = game.chats.get(chat_id)
    if chat is None:
        return {"message": "Chat not found"}, 404
    mod_token, player = get_permissions(game, request.headers)
    is_mod = mod_token == game.mod_token
    if not is_mod and not chat.has_read_perms(game, player):
        return {"message": "Chat not found"}, 404
    start = request.args.get("start", 0)
    limit = request.args.get("limit", 25)
    if not isinstance(start, int):
        return {"message": "'start' field is not an integer"}, 400
    if not isinstance(limit, int):
        return {"message": "'limit' field is not an integer"}, 400
    return {
        "chat_id": chat_id,
        "total_messages": len(chat),
        "messages": [
            {"author": msg.sender, "timestamp": idx, "content": msg.content}
            for idx, msg in enumerate(chat[start : start + limit])
        ],
    }


@app.post("/api/v0/games/<int:game_id>/chats/<string:chat_id>")
@app.post("/api/v0/games/<int:game_id>/chats/<string:chat_id>/messages")
def api_v0_send_chat_message(game_id: int, chat_id: str) -> Any:
    """Send a chat message. Message is attributed to the authorized sender.

    Authorization: Player (Write Perms), Moderator

    Request Body:
    * `content`: `string`

    Status Codes:
    * 204 No Content
    * 400 Bad Request
    * 401 Unauthorized
    * 403 Forbidden
    * 404 Not Found &mdash; Returned in place of 401 or 403 for those without read permissions.
    * 415 Unsupported Media Type
    """

    if game_id not in games:
        return {"message": "Game not found"}, 404
    game = games[game_id]
    chat = game.chats.get(chat_id)
    if chat is None:
        return {"message": "Chat not found"}, 404
    mod_token, player = get_permissions(game, request.headers)
    is_mod = mod_token == game.mod_token
    if not is_mod and not chat.has_write_perms(game, player):
        return {"message": "Chat not found"}, 404
    body = request.get_json()
    if body is None:
        return {"message": "Request body is not JSON"}, 415
    if not isinstance(body, dict):
        return {"message": "Request body is not a JSON object"}, 400
    if "content" not in body:
        return {"message": "Missing 'content' field"}, 400
    if not isinstance(body["content"], str):
        return {"message": "'content' field is not a string"}, 400
    chat.send(player.name if player is not None else "Moderator", body["content"])
    return "", 204


games: dict[int, Game] = {}
game_count = count(0)

with app.test_client() as client:
    client.post(
        "/api/v0/games",
        json={
            "players": [
                "Alice",
                "Bob",
                "Charlie",
                "David",
                "Eve",
                "Frank",
                "Grace",
                "Heidi",
                "Ivan",
            ],
            "roles": [
                {"role": "Gunsmith", "alignment": "Town"},
                {"role": "Doctor", "alignment": "Town"},
                {"role": "Cop", "alignment": "Town"},
                {"role": "Rolestopper", "alignment": "Town"},
                {"role": "Bulletproof", "alignment": "Town"},
                {"role": "Vanilla", "alignment": "Town"},
                {"role": "Vanilla", "alignment": "Serial Killer"},
                {"role": "Roleblocker", "alignment": "Mafia"},
                {"role": "Vanilla", "alignment": "Mafia"},
            ],
            "start_phase": "DAY",
            "mod_token": "__test__",
        },
    )
