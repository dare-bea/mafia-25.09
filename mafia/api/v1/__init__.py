"""API v1 endpoints."""

import random
from collections.abc import Callable
from datetime import UTC, datetime

from flask import Blueprint, request
from flask_pydantic import validate  # type: ignore[import-untyped]

from mafia import core, normal
from mafia.api.core import Game, game_count, games, get_permissions, resolver

from . import models

api_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")


@api_bp.get("/games")
@validate()  # type: ignore[misc]
def game_list(query: models.GameListQueryModel) -> models.GameListResponseModel:
    """Get the list of games."""
    start = max(query.start, 0)
    limit = 25 if query.limit < 0 else query.limit
    game_result = sorted(games.items(), key=lambda x: x[0])[start : start + limit]
    return models.GameListResponseModel(
        games=[
            models.GameSummaryModel(
                id=gid,
                players=[player.name for player in game.players],
                phase=game.phase,
                day_no=game.day_no,
                phase_order=list(game.phase_order),
                chat_phases=list(game.chat_phases),
            )
            for gid, game in game_result
        ],
        total_games=len(games),
    )


@api_bp.post("/games")
@validate()  # type: ignore[misc]
def game_create(
    body: models.GameCreateRequestModel,
) -> tuple[models.GameCreateResponseModel, int]:
    """Create a new game."""
    roles = list(body.roles)

    if body.shuffle_roles:
        random.shuffle(roles)

    alignments: dict[
        tuple[type[core.Alignment] | Callable[..., core.Alignment], str | None],
        core.Alignment,
    ] = {}
    for r in roles:
        a = r.alignment_value()
        if (a, r.alignment_id) not in alignments:
            alignments[a, r.alignment_id] = a(
                id=r.alignment_id,
                demonym=r.alignment_demonym,
                role_names=r.alignment_role_names,
            )

    if body.phase is None:
        body.phase = body.phase_order[0]

    game = Game(
        body.day_no,
        start_phase=body.phase,
        phase_order=tuple(body.phase_order),
        chat_phases=frozenset(body.chat_phases),
    )

    for player_name, role in zip(body.players, roles, strict=False):
        game.add_player(
            core.Player(
                player_name,
                role.role.value()(**role.role_params),
                alignments[role.alignment_value(), role.alignment_id],
            ),
        )

    gid = next(game_count)

    games[gid] = game

    return models.GameCreateResponseModel(id=gid, mod_token=game.mod_token), 201


@api_bp.get("/games/<int:gid>")
@validate()  # type: ignore[misc]
def game_get(gid: int) -> models.GameResponseModel | models.ErrorResponse:
    """Get a game."""
    if gid not in games:
        return {"message": "Game not found"}, 404
    game = games[gid]
    mod_token, player = get_permissions(game, request.headers)
    return models.GameResponseModel(
        id=gid,
        day_no=game.day_no,
        phase=game.phase,
        players=[
            models.ShortPlayerModel(
                name=p.name,
                is_alive=p.is_alive,
                role_name=p.role_name,
                role=p.role.id,
                alignment=p.alignment.id,
            )
            if mod_token == game.mod_token
            or player is p
            or not p.is_alive
            or (player is not None and p in player.known_players)
            else models.ShortPartialPlayerModel(
                name=p.name,
                is_alive=p.is_alive,
            )
            for p in game.players
        ],
        chats=[
            models.ShortChatModel(
                id=chat_id,
                total_messages=len(chat),
            )
            for chat_id, chat in game.chats.items()
            if mod_token == game.mod_token or chat.has_read_perms(game, player)
        ],
        phase_order=list(game.phase_order),
        chat_phases=list(game.chat_phases),
    )


@api_bp.put("/games/<int:gid>")
@validate()  # type: ignore[misc]
def game_put(
    gid: int,
    body: models.GamePutRequestModel,
) -> models.EmptyResponse | models.ErrorResponse:
    """Update a game."""
    if gid not in games:
        return {"message": "Game not found"}, 404
    game = games[gid]
    mod_token, player = get_permissions(game, request.headers)
    if mod_token is None and player is None:
        return {"message": "Not authenticated"}, 401
    if mod_token != game.mod_token:
        return {"message": "Not the moderator"}, 403
    if body.day_no is not None:
        game.day_no = body.day_no
    if body.phase is not None:
        game.phase = body.phase
    if body.phase_order is not None:
        game.phase_order = tuple(body.phase_order)
    if body.chat_phases is not None:
        game.chat_phases = frozenset(body.chat_phases)
    return "", 204


def handle_patch_action(game: Game, action: models.GamePatchAction) -> None:
    """Handle a patch action."""
    match action:
        case models.GamePatchAction.DEQUEUE:
            for v in game.queued_visits:
                if v.is_active_time(game):
                    game.visits.append(v)
            game.queued_visits.clear()
        case models.GamePatchAction.RESOLVE:
            for v in game.queued_visits:
                if v.is_active_time(game):
                    game.visits.append(v)
            game.queued_visits.clear()
            resolver.resolve_game(game)
        case models.GamePatchAction.NEXT_PHASE | models.GamePatchAction.ADVANCE_PHASE:
            game.advance_phase()
        case models.GamePatchAction.CLEAR_VOTES:
            game.votes.clear()
        case models.GamePatchAction.POST_VOTE_COUNT:
            game.post_vote_count("global")


@api_bp.patch("/games/<int:gid>")
@validate()  # type: ignore[misc]
def game_patch(
    gid: int,
    body: models.GamePatchRequestModel,
) -> models.EmptyResponse | models.ErrorResponse:
    """Update a game."""
    if gid not in games:
        return {"message": "Game not found"}, 404
    game = games[gid]
    mod_token, player = get_permissions(game, request.headers)
    if mod_token is None and player is None:
        return {"message": "Not authenticated"}, 401
    if mod_token != game.mod_token:
        return {"message": "Not the moderator"}, 403
    for action in body.actions:
        handle_patch_action(game, action)
    return "", 204


@api_bp.get("/games/<int:gid>/players")
@validate()  # type: ignore[misc]
def game_players(
    gid: int,
) -> (
    list[models.ShortPlayerModel | models.ShortPartialPlayerModel] | models.ErrorResponse
):
    """Get the players in a game."""
    if gid not in games:
        return {"message": "Game not found"}, 404
    game = games[gid]
    mod_token, player = get_permissions(game, request.headers)
    return [
        models.ShortPlayerModel(
            name=p.name,
            is_alive=p.is_alive,
            role_name=p.role_name,
            role=p.role.id,
            alignment=p.alignment.id,
        )
        if mod_token == game.mod_token
        or player is p
        or not p.is_alive
        or (player is not None and p in player.known_players)
        else models.ShortPartialPlayerModel(
            name=p.name,
            is_alive=p.is_alive,
        )
        for p in game.players
    ]


@api_bp.get("/games/<int:gid>/chats")
@validate()  # type: ignore[misc]
def game_chats(gid: int) -> list[models.ShortChatModel] | models.ErrorResponse:
    """Get the chats in a game."""
    if gid not in games:
        return {"message": "Game not found"}, 404
    game = games[gid]
    mod_token, player = get_permissions(game, request.headers)
    return [
        models.ShortChatModel(
            id=chat_id,
            total_messages=len(chat),
        )
        for chat_id, chat in game.chats.items()
        if mod_token == game.mod_token or chat.has_read_perms(game, player)
    ]


@api_bp.get("/games/<int:gid>/players/<string:name>")
@validate()  # type: ignore[misc]
def game_player(gid: int, name: str) -> models.PlayerResponseModel | models.ErrorResponse:
    """Get a player in a game."""
    if gid not in games:
        return {"message": "Game not found"}, 404
    game = games[gid]
    player = next((p for p in game.players if p.name == name), None)
    if player is None:
        return {"message": "Player not found"}, 404
    mod_token, player_auth = get_permissions(game, request.headers)
    if mod_token is None and player_auth is None:
        return {"message": "Not authenticated"}, 401
    if mod_token != game.mod_token and player_auth is not player:
        return {"message": "Not the moderator or the player"}, 403
    return models.PlayerResponseModel(
        name=player.name,
        is_alive=player.is_alive,
        role_name=player.role_name,
        role=models.PlayerRAModel(
            id=player.role.id,
            actions=[a.id for a in player.actions],
            passives=[a.id for a in player.passives],
            shared_actions=[a.id for a in player.shared_actions],
        ),
        alignment=models.PlayerRAModel(
            id=player.alignment.id,
            actions=[a.id for a in player.alignment.actions],
            passives=[a.id for a in player.alignment.passives],
            shared_actions=[a.id for a in player.alignment.shared_actions],
        ),
        known_players=[
            models.ShortPlayerModel(
                name=p.name,
                is_alive=p.is_alive,
                role_name=p.role_name,
                role=p.role.id,
                alignment=p.alignment.id,
            )
            for p in player.known_players
        ],
        total_private_messages=len(player.private_messages),
        chats=[
            models.ShortChatModel(
                id=chat_id,
                total_messages=len(chat),
            )
            for chat_id, chat in game.chats.items()
            if chat.has_read_perms(game, player)
        ],
    )


@api_bp.get("/games/<int:gid>/players/<string:name>/abilities")
@validate()  # type: ignore[misc]
def game_player_abilities(
    gid: int,
    name: str,
) -> models.PlayerAbiltiesResponseModel | models.ErrorResponse:
    """Get the abilities of a player in a game."""
    if gid not in games:
        return {"message": "Game not found"}, 404
    game = games[gid]
    player = next((p for p in game.players if p.name == name), None)
    if player is None:
        return {"message": "Player not found"}, 404
    mod_token, player_auth = get_permissions(game, request.headers)
    if mod_token is None and player_auth is None:
        return {"message": "Not authenticated"}, 401
    if mod_token != game.mod_token and player_auth is not player:
        return {"message": "Not the moderator or the player"}, 403
    return models.PlayerAbiltiesResponseModel(
        actions=[
            models.PlayerAbilitiesActionModel(
                id=a.id,
                phase=a.phase,
                immediate=a.immediate,
                target_count=a.target_count,
                targets=[
                    [t.name for t in targets] for targets in a.valid_targets(game, player)
                ]
                if a.target_count > 0
                else [],
                queued=[t.name for t in v.targets]
                if (
                    v := next(
                        (
                            v
                            for v in game.queued_visits
                            if v.actor == player and v.ability == a
                        ),
                        None,
                    )
                )
                is not None
                else None,
            )
            for a in player.actions
        ],
        passives=[
            models.PlayerAbilitiesPassiveModel(
                id=a.id,
                phase=a.phase,
                immediate=a.immediate,
                queued=a.check(game, player),
            )
            for a in player.passives
        ],
        shared_actions=[
            models.PlayerAbilitiesSharedActionModel(
                id=a.id,
                used_by=v.actor.name
                if (
                    v := next(
                        (
                            v
                            for v in game.queued_visits
                            if v.ability == a and v.actor.alignment == player.alignment
                        ),
                        None,
                    )
                )
                is not None
                else None,
                phase=a.phase,
                immediate=a.immediate,
                target_count=a.target_count,
                targets=[
                    [t.name for t in targets] for targets in a.valid_targets(game, player)
                ]
                if a.target_count > 0
                else [],
                queued=[t.name for t in v.targets]
                if (
                    v := next(
                        (
                            v
                            for v in game.queued_visits
                            if v.ability == a and v.actor.alignment == player.alignment
                        ),
                        None,
                    )
                )
                is not None
                else None,
            )
            for a in player.shared_actions
        ],
    )


def validate_action(  # noqa: PLR0913
    game: Game,
    player: core.Player,
    ability_id: str,
    requested_visit: models.PlayerQueueAbilityModel | None,
    valid_actions: dict[str, core.Ability],
    valid_players: dict[str, core.Player],
) -> models.ErrorResponse | None:
    """Validate an action for a player in a game."""
    if ability_id not in valid_actions:
        return {
            "message": f"Invalid action '{ability_id}' for player '{player.name}'",
        }, 400
    if requested_visit is not None:
        invalid_targets = {t for t in requested_visit.targets if t not in valid_players}
        if invalid_targets:
            return {
                "message": f"Invalid targets for '{ability_id}': "
                f"{', '.join(invalid_targets)}",
            }, 400
        if not valid_actions[ability_id].check(
            game,
            player,
            [valid_players[t] for t in requested_visit.targets],
        ):
            return {
                "message": f"Check failed for '{ability_id}': "
                f"{', '.join(requested_visit.targets)}",
            }, 400
    return None


def queue_visit(  # noqa: PLR0913
    game: Game,
    player: core.Player,
    ability: core.Ability,
    ability_type: core.AbilityType,
    requested_visit: models.PlayerQueueAbilityModel | None,
    valid_players: dict[str, core.Player],
) -> None:
    """Queue a visit for a player in a game."""
    prev_visit = next(
        (
            v
            for v in game.queued_visits
            if v.ability == ability and v.actor.alignment == player.alignment
        ),
        None,
    )
    if prev_visit is not None:
        game.queued_visits.remove(prev_visit)
    if requested_visit is not None:
        game.queued_visits.append(
            core.Visit(
                actor=player,
                targets=tuple(valid_players[t] for t in requested_visit.targets),
                ability=ability,
                ability_type=ability_type,
                game=game,
                player_inputs=tuple(requested_visit.player_inputs),
            ),
        )


def validate_ability_requests(  # noqa: PLR0913
    game: Game,
    player: core.Player,
    body: models.PlayerQueueAbilityRequestModel,
    valid_actions: dict[str, core.Ability],
    valid_shared_actions: dict[str, core.Ability],
    valid_players: dict[str, core.Player],
) -> models.ErrorResponse | None:
    """Validate ability requests for a player in a game."""
    for ability_id, requested_visit in body.actions.items():
        message = validate_action(
            game,
            player,
            ability_id,
            requested_visit,
            valid_actions,
            valid_players,
        )
        if message is not None:
            return message

    for ability_id, requested_visit in body.shared_actions.items():
        message = validate_action(
            game,
            player,
            ability_id,
            requested_visit,
            valid_shared_actions,
            valid_players,
        )
        if message is not None:
            return message

    return None


@api_bp.post("/games/<int:gid>/players/<string:name>/abilities")
@validate()  # type: ignore[misc]
def game_player_queue_ability(
    gid: int,
    name: str,
    body: models.PlayerQueueAbilityRequestModel,
) -> models.EmptyResponse | models.ErrorResponse:
    """Queue an ability for a player in a game."""
    if gid not in games:
        return {"message": "Game not found"}, 404
    game = games[gid]
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

    message = validate_ability_requests(
        game,
        player,
        body,
        valid_actions,
        valid_shared_actions,
        valid_players,
    )
    if message is not None:
        return message

    for ability_id, requested_visit in body.actions.items():
        queue_visit(
            game,
            player,
            valid_actions[ability_id],
            core.AbilityType.ACTION,
            requested_visit,
            valid_players,
        )

    for ability_id, requested_visit in body.shared_actions.items():
        queue_visit(
            game,
            player,
            valid_shared_actions[ability_id],
            core.AbilityType.SHARED_ACTION,
            requested_visit,
            valid_players,
        )

    return "", 204


@api_bp.get("/games/<int:gid>/players/<string:name>/messages")
@validate()  # type: ignore[misc]
def game_player_messages(
    gid: int,
    name: str,
    query: models.ChatQueryModel,
) -> models.PlayerPMResponseModel | models.ErrorResponse:
    """Get a player's private messages."""
    if gid not in games:
        return {"message": "Game not found"}, 404
    game = games[gid]
    player = next((p for p in game.players if p.name == name), None)
    if player is None:
        return {"message": "Player not found"}, 404
    mod_token, player_auth = get_permissions(game, request.headers)
    if mod_token is None and player_auth is None:
        return {"message": "Not authenticated"}, 401
    if mod_token != game.mod_token and not player.private_messages.has_read_perms(
        game,
        player_auth,
    ):
        return {"message": "Not the moderator or authorized player"}, 403
    start = max(query.start, 0)
    limit = 25 if query.limit < 0 else query.limit
    return models.PlayerPMResponseModel(
        total_messages=len(player.private_messages),
        messages=[
            models.ChatMessageModel(
                author=str(msg.sender),
                timestamp=datetime.now(tz=UTC),
                content=msg.content,
            )
            for idx, msg in enumerate(player.private_messages[start : start + limit])
        ],
    )


@api_bp.post("/games/<int:gid>/players/<string:name>/messages")
@validate()  # type: ignore[misc]
def game_player_send_message(
    gid: int,
    name: str,
    body: models.ChatPostRequestModel,
) -> models.EmptyResponse | models.ErrorResponse:
    """Send a private message to a player."""
    if gid not in games:
        return {"message": "Game not found"}, 404
    game = games[gid]
    player = next((p for p in game.players if p.name == name), None)
    if player is None:
        return {"message": "Player not found"}, 404
    mod_token, player_auth = get_permissions(game, request.headers)
    if mod_token is None and player_auth is None:
        return {"message": "Not authenticated"}, 401
    if mod_token != game.mod_token and player.private_messages.has_write_perms(
        game,
        player_auth,
    ):
        return {"message": "Not the moderator or authorized player"}, 403
    player.private_messages.send(
        player_auth.name if player_auth is not None else "Moderator",
        body.content,
    )
    return "", 204


@api_bp.get("/games/<int:gid>/chats/<string:chat_id>")
@validate()  # type: ignore[misc]
def game_chat(
    gid: int,
    chat_id: str,
) -> models.ChatGetResponseModel | models.ErrorResponse:
    """Get a chat in a game."""
    if gid not in games:
        return {"message": "Game not found"}, 404
    game = games[gid]
    mod_token, player = get_permissions(game, request.headers)
    chat = game.chats.get(chat_id)
    read_perms = False if chat is None else chat.has_read_perms(game, player)
    if mod_token is None and player is None and not read_perms:
        return {"message": "Not authenticated"}, 401
    if chat is None or (mod_token != game.mod_token and not read_perms):
        return {"message": "Chat not found"}, 404
    return models.ChatGetResponseModel(
        chat_id=chat_id,
        read_perms=[p.name for p in chat.read_perms(game)],
        write_perms=[p.name for p in chat.write_perms(game)],
        total_messages=len(chat),
    )


@api_bp.get("/games/<int:gid>/chats/<string:chat_id>/messages")
@validate()  # type: ignore[misc]
def game_chat_messages(
    gid: int,
    chat_id: str,
    query: models.ChatQueryModel,
) -> models.ChatMessagesResponseModel | models.ErrorResponse:
    """Get the messages in a chat."""
    if gid not in games:
        return {"message": "Game not found"}, 404
    game = games[gid]
    mod_token, player = get_permissions(game, request.headers)
    chat = game.chats.get(chat_id)
    read_perms = False if chat is None else chat.has_read_perms(game, player)
    if mod_token is None and player is None and not read_perms:
        return {"message": "Not authenticated"}, 401
    if chat is None or (mod_token != game.mod_token and not read_perms):
        return {"message": "Chat not found"}, 404
    start = max(query.start, 0)
    limit = 25 if query.limit < 0 else query.limit
    return models.ChatMessagesResponseModel(
        chat_id=chat_id,
        total_messages=len(chat),
        messages=[
            models.ChatMessageModel(
                author=str(msg.sender),
                timestamp=datetime.now(UTC),
                content=msg.content,
            )
            for idx, msg in enumerate(chat[start : start + limit])
        ],
    )


@api_bp.post("/games/<int:gid>/chats/<string:chat_id>")
@api_bp.post("/games/<int:gid>/chats/<string:chat_id>/messages")
@validate()  # type: ignore[misc]
def game_chat_send_message(
    gid: int,
    chat_id: str,
    body: models.ChatPostRequestModel,
) -> models.EmptyResponse | models.ErrorResponse:
    """Send a message to a chat."""
    if gid not in games:
        return {"message": "Game not found"}, 404
    game = games[gid]
    mod_token, player = get_permissions(game, request.headers)
    chat = game.chats.get(chat_id)
    read_perms = False if chat is None else chat.has_read_perms(game, player)
    write_perms = False if chat is None else chat.has_write_perms(game, player)
    if mod_token is None and player is None and not read_perms and not write_perms:
        return {"message": "Not authenticated"}, 401
    if chat is None or (mod_token != game.mod_token and not read_perms):
        return {"message": "Chat not found"}, 404
    if mod_token != game.mod_token and not write_perms:
        return {
            "message": "Not the moderator or player authorized to write to this chat",
        }, 403
    chat.send(player.name if player is not None else "Moderator", body.content)
    return "", 204


@api_bp.get("/games/<int:gid>/votes")
@validate()  # type: ignore[misc]
def game_votes(gid: int) -> models.GameVotesResponseModel | models.ErrorResponse:
    """Get the votes in a game."""
    if gid not in games:
        return {"message": "Game not found"}, 404
    game = games[gid]
    return models.GameVotesResponseModel(
        votes={
            p.name: v.name if (v := game.votes[p]) is not None else None
            for p in game.players
        },
        vote_counts={
            p.name: [v.name for v in game.get_voters(p)]
            for p in game.players
            if game.get_votes(p) > 0
        },
        no_elim_vote_count=[v.name for v in game.get_voters(None)],
    )


@api_bp.post("/games/<int:gid>/players/<string:name>/vote")
@validate()  # type: ignore[misc]
def game_player_vote(  # noqa: PLR0911
    gid: int,
    name: str,
    body: models.PlayerVoteRequestModel,
) -> models.EmptyResponse | models.ErrorResponse:
    """Vote for a player in a game."""
    if gid not in games:
        return {"message": "Game not found"}, 404
    game = games[gid]
    player = next((p for p in game.players if p.name == name), None)
    if player is None:
        return {"message": "Player not found"}, 404
    mod_token, player_auth = get_permissions(game, request.headers)
    if mod_token is None and player_auth is None:
        return {"message": "Not authenticated"}, 401
    if mod_token != game.mod_token and player_auth is not player:
        return {"message": "Not the moderator or the player"}, 403
    if not game.is_voting_phase():
        return {"message": "Not a voting phase"}, 400
    if body.target is None:
        game.vote(player, None)
    else:
        target = next((p for p in game.alive_players if p.name == body.target), None)
        if target is None:
            return {"message": "Target not found"}, 404
        game.vote(player, target)
    return "", 204


@api_bp.delete("/games/<int:gid>/players/<string:name>/vote")
@validate()  # type: ignore[misc]
def game_player_unvote(
    gid: int,
    name: str,
) -> models.EmptyResponse | models.ErrorResponse:
    """Unvote for a player in a game."""
    if gid not in games:
        return {"message": "Game not found"}, 404
    game = games[gid]
    player = next((p for p in game.players if p.name == name), None)
    if player is None:
        return {"message": "Player not found"}, 404
    mod_token, player_auth = get_permissions(game, request.headers)
    if mod_token is None and player_auth is None:
        return {"message": "Not authenticated"}, 401
    if mod_token != game.mod_token and player_auth is not player:
        return {"message": "Not the moderator or the player"}, 403
    if not game.is_voting_phase():
        return {"message": "Not a voting phase"}, 400
    game.unvote(player)
    return "", 204


@api_bp.get("/reference/roles")
@validate()  # type: ignore[misc]
def roles_list() -> list[models.ObjectReferenceModel]:
    """Get the list of roles."""
    return [
        models.ObjectReferenceModel(name=name, description=role.__doc__)
        for name, role in normal.ROLES.items()
    ]


@api_bp.get("/reference/combined-roles")
@validate()  # type: ignore[misc]
def combined_roles_list() -> list[models.ObjectReferenceModel]:
    """Get the list of combined roles."""
    return [
        models.ObjectReferenceModel(name=name, description=role.__doc__)
        for name, role in normal.COMBINED_ROLES.items()
    ]


@api_bp.get("/reference/modifiers")
@validate()  # type: ignore[misc]
def modifiers_list() -> list[models.ObjectReferenceModel]:
    """Get the list of modifiers."""
    return [
        models.ObjectReferenceModel(name=name, description=role.__doc__)
        for name, role in normal.MODIFIERS.items()
    ]


@api_bp.get("/reference/alignments")
@validate()  # type: ignore[misc]
def alignments_list() -> list[models.ObjectReferenceModel]:
    """Get the list of alignments."""
    return [
        models.ObjectReferenceModel(name=name, description=role.__doc__)
        for name, role in normal.ALIGNMENTS.items()
    ]
