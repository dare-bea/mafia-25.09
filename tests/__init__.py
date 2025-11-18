"""Tests for the mafia package."""

from pathlib import Path
from sys import path

path.append(str(Path(__file__).parent.parent))

import logging
from collections.abc import Callable
from logging import getLogger
from pathlib import Path
from pprint import pformat

from flask import Flask

from mafia import _status as status
from mafia import core, normal
from mafia.api import api_bp
from mafia.core import AbilityType, VisitStatus
from mafia.normal import LoggingResolver

logger = getLogger(__name__)
logger.setLevel(logging.INFO)


def test_catastrophic_rule() -> None:
    r = LoggingResolver(logger)

    cop = normal.Cop()
    jailkeeper = normal.Jailkeeper()
    roleblocker = normal.Roleblocker()
    town = normal.Town()
    mafia = normal.Mafia()

    game = core.Game(start_phase=core.Phase.NIGHT)
    alice = core.Player("Alice", cop, town)
    bob = core.Player("Bob", jailkeeper, town)
    eve = core.Player("Eve", roleblocker, mafia)

    game.add_player(alice, bob, eve)

    r.log_players(game)

    r.add_passives(game)

    game.visits.append(
        r.make_visit(game, eve, (alice,), AbilityType.SHARED_ACTION, 0, {"factional"}),
    )
    game.visits.append(r.make_visit(game, bob, (eve,), AbilityType.ACTION, 0))
    game.visits.append(r.make_visit(game, eve, (bob,), AbilityType.ACTION, 0))
    game.visits.append(r.make_visit(game, eve, (alice,), AbilityType.ACTION, 0))
    game.visits.append(r.make_visit(game, alice, (eve,), AbilityType.ACTION, 0))

    r.resolve_game(game)

    r.logger.info(pformat(game))

    assert game.visits[4].status != VisitStatus.FAILURE
    assert all(v.status == VisitStatus.FAILURE for v in game.visits[:4])


def test_xshot_role() -> None:
    r = LoggingResolver(logger)

    vanilla = normal.Vanilla()
    xshot = normal.XShot(1)
    xshot_cop = xshot(normal.Cop)()
    xshot_bulletproof = xshot(normal.Bulletproof)()
    town = normal.Town()
    mafia = normal.Mafia()

    game = core.Game()
    alice = core.Player("Alice", xshot_cop, town)
    bob = core.Player("Bob", xshot_bulletproof, town)
    eve = core.Player("Eve", vanilla, mafia)

    game.add_player(alice, bob, eve)

    r.log_players(game)

    game.phase, game.day_no = core.Phase.NIGHT, 1
    r.add_passives(game)

    if alice.actions[0].check(game, alice, (bob,)):
        r.logger.info("%s is using %s on %s.", alice.name, alice.actions[0].id, bob.name)
        game.visits.append(r.make_visit(game, alice, (bob,), AbilityType.ACTION, 0))
    else:
        r.logger.info(
            "%s cannot use %s on %s.", alice.name, alice.actions[0].id, bob.name
        )
        msg = "Expected check to succeed."
        raise AssertionError(msg)
    game.visits.append(
        r.make_visit(game, eve, (bob,), AbilityType.SHARED_ACTION, 0, {"factional"}),
    )
    r.resolve_game(game)
    assert bob.is_alive, "Bob is dead, expected Bulletproof to protect."

    game.phase, game.day_no = core.Phase.NIGHT, 2
    if alice.actions[0].check(game, alice, (eve,)):
        r.logger.info("%s is using %s on %s.", alice.name, alice.actions[0].id, eve.name)
        game.visits.append(r.make_visit(game, alice, (eve,), AbilityType.ACTION, 0))
        msg = "Expected check to fail."
        raise AssertionError(msg)
    r.logger.info("%s is using %s on %s.", alice.name, alice.actions[0].id, bob.name)
    game.visits.append(
        r.make_visit(game, eve, (bob,), AbilityType.SHARED_ACTION, 0, {"factional"}),
    )
    r.resolve_game(game)

    r.logger.info(pformat(game))

    assert not bob.is_alive, "Bob is alive, expected 1-Shot Bulletproof to be used."


def test_protection() -> None:
    r = LoggingResolver(logger)

    town = normal.Town()
    mafia = normal.Mafia()

    game = core.Game(start_phase=core.Phase.NIGHT)
    alice = core.Player("Alice", normal.Doctor(), town)
    bob = core.Player("Bob", normal.Vanilla(), town)
    eve = core.Player("Eve", normal.Vanilla(), mafia)

    game.add_player(alice, bob, eve)

    r.log_players(game)

    r.add_passives(game)
    game.visits.append(r.make_visit(game, alice, (bob,), AbilityType.ACTION, 0))
    game.visits.append(
        r.make_visit(game, eve, (bob,), AbilityType.SHARED_ACTION, 0, {"factional"}),
    )

    r.resolve_game(game)

    r.logger.info(pformat(game))

    assert bob.is_alive, "Bob is dead."


def test_xshot_macho() -> None:
    r = LoggingResolver(logger)

    town = normal.Town()
    mafia = normal.Mafia()

    game = core.Game(start_phase=core.Phase.NIGHT)
    alice = core.Player("Alice", normal.Doctor(), town)
    bob = core.Player("Bob", normal.XShot(1)(normal.Macho)(), town)
    carol = core.Player("Carol", normal.XShot(1)(normal.Macho)(), town)
    eve = core.Player("Eve", normal.Vanilla(), mafia)

    game.add_player(alice, bob, carol, eve)

    r.log_players(game)

    r.add_passives(game)
    game.visits.append(r.make_visit(game, alice, (bob,), AbilityType.ACTION, 0))
    game.visits.append(r.make_visit(game, alice, (carol,), AbilityType.ACTION, 0))
    game.visits.append(r.make_visit(game, alice, (carol,), AbilityType.ACTION, 0))
    game.visits.append(
        r.make_visit(game, eve, (bob,), AbilityType.SHARED_ACTION, 0, {"factional"}),
    )
    game.visits.append(
        r.make_visit(game, eve, (carol,), AbilityType.SHARED_ACTION, 0, {"factional"}),
    )

    r.resolve_game(game)

    r.logger.info(pformat(game))

    assert not bob.is_alive, "Bob is alive."
    assert carol.is_alive, "Carol is dead."


def test_tracker_roleblocker() -> None:
    r = LoggingResolver(logger)

    town = normal.Town()
    mafia = normal.Mafia()

    game = core.Game(start_phase=core.Phase.NIGHT)
    alice = core.Player("Alice", normal.Roleblocker(), town)
    bob = core.Player("Bob", normal.Tracker(), town)
    eve = core.Player("Eve", normal.Vanilla(), mafia)

    game.add_player(alice, bob, eve)

    r.log_players(game)

    r.add_passives(game)
    game.visits.append(r.make_visit(game, alice, (eve,), AbilityType.ACTION, 0))
    game.visits.append(r.make_visit(game, bob, (eve,), AbilityType.ACTION, 0))
    game.visits.append(
        r.make_visit(game, eve, (bob,), AbilityType.SHARED_ACTION, 0, {"factional"}),
    )

    r.resolve_game(game)

    r.logger.info(pformat(game))

    r.logger.info(bob.private_messages)
    assert bob.private_messages[0].content == "Eve did not target anyone."


def test_juggernaut() -> None:
    r = LoggingResolver(logger)

    town = normal.Town()
    mafia = normal.Mafia()

    game = core.Game(start_phase=core.Phase.NIGHT)
    alice = core.Player("Alice", normal.Roleblocker(), town)
    bob = core.Player("Bob", normal.Vanilla(), town)
    eve = core.Player("Eve", normal.Juggernaut(), mafia)

    game.add_player(alice, bob, eve)

    r.log_players(game)

    r.add_passives(game)
    game.visits.append(r.make_visit(game, alice, (eve,), AbilityType.ACTION, 0))
    game.visits.append(r.make_visit(game, eve, (eve,), AbilityType.ACTION, 0))
    game.visits.append(
        r.make_visit(game, eve, (bob,), AbilityType.SHARED_ACTION, 0, {"factional"}),
    )

    r.resolve_game(game)

    r.logger.info(pformat(game))

    assert not bob.is_alive, (
        "Factional Kill was roleblocked, expected Juggernaut to force kill."
    )


def test_investigative_fail() -> None:
    r = LoggingResolver(logger)
    town = normal.Town()
    mafia = normal.Mafia()
    game = core.Game(start_phase=core.Phase.NIGHT)

    alice = core.Player("Alice", normal.Roleblocker(), town)
    bob = core.Player("Bob", normal.Cop(), town)
    eve = core.Player("Eve", normal.Vanilla(), mafia)

    game.add_player(alice, bob, eve)

    r.log_players(game)
    r.add_passives(game)
    game.visits.append(r.make_visit(game, alice, (bob,), AbilityType.ACTION, 0))
    game.visits.append(r.make_visit(game, bob, (eve,), AbilityType.ACTION, 0))
    r.resolve_game(game)

    r.logger.info(pformat(game))
    r.logger.info(bob.private_messages)

    assert (
        bob.private_messages[0].content
        == "Your ability failed, and you did not recieve a result."
    ), "Bob's Cop did not fail."


def test_ascetic() -> None:
    r = LoggingResolver(logger)
    town = normal.Town()
    mafia = normal.Mafia()
    game = core.Game(start_phase=core.Phase.NIGHT)

    alice = core.Player("Alice", normal.Ascetic(), town)
    bob = core.Player("Bob", normal.Doctor(), town)
    eve = core.Player("Eve", normal.Vanilla(), mafia)

    game.add_player(alice, bob, eve)

    r.log_players(game)
    r.add_passives(game)
    game.visits.append(r.make_visit(game, bob, (alice,), AbilityType.ACTION, 0))
    game.visits.append(
        r.make_visit(game, eve, (alice,), AbilityType.SHARED_ACTION, 0, {"factional"}),
    )
    r.resolve_game(game)

    r.logger.info(pformat(game))

    assert not alice.is_alive, "Alice is alive, expected Ascetic to prevent protection."


def test_detective() -> None:
    r = LoggingResolver(logger)
    town = normal.Town()
    mafia = normal.Mafia()
    game = core.Game(start_phase=core.Phase.NIGHT)

    alice = core.Player("Alice", normal.Detective(), town)
    bob = core.Player("Bob", normal.Vanilla(), town)
    eve = core.Player("Eve", normal.Vanilla(), mafia)

    game.add_player(alice, bob, eve)

    r.log_players(game)
    r.add_passives(game)
    game.visits.append(
        r.make_visit(game, eve, (bob,), AbilityType.SHARED_ACTION, 0, {"factional"}),
    )
    r.resolve_game(game)

    game.phase, game.day_no = core.Phase.NIGHT, 2
    game.visits.append(r.make_visit(game, alice, (eve,), AbilityType.ACTION, 0))
    r.resolve_game(game)

    r.logger.info(pformat(game))
    r.logger.info(alice.private_messages)

    assert alice.private_messages[0].content == "Eve has tried to kill someone!", (
        "Detective did not detect kill."
    )


def test_jack_of_all_trades() -> None:
    r = LoggingResolver(logger)
    town = normal.Town()
    mafia = normal.Mafia()
    game = core.Game(start_phase=core.Phase.NIGHT)

    joat = normal.Jack_of_All_Trades(
        normal.Cop,
        normal.Doctor,
    )

    alice = core.Player("Alice", joat(), town)
    bob = core.Player("Bob", normal.Vanilla(), town)
    eve = core.Player("Eve", normal.Vanilla(), mafia)

    game.add_player(alice, bob, eve)

    r.log_players(game)
    r.add_passives(game)
    game.visits.append(r.make_visit(game, alice, (bob,), AbilityType.ACTION, 1))
    game.visits.append(
        r.make_visit(game, eve, (bob,), AbilityType.SHARED_ACTION, 0, {"factional"}),
    )
    r.resolve_game(game)

    r.logger.info(pformat(game))

    assert bob.is_alive, "Bob is dead, expected Doctor to protect."
    assert alice.actions[0].check(game, alice, (bob,)), "Cop is not usable."
    assert not alice.actions[1].check(game, alice, (bob,)), "Doctor is still usable."


def test_hider() -> None:
    r = LoggingResolver(logger)
    town = normal.Town()
    mafia = normal.Mafia()
    game = core.Game(start_phase=core.Phase.NIGHT)

    alice = core.Player("Alice", normal.Hider(), town)
    bob = core.Player("Bob", normal.Vanilla(), town)
    carol = core.Player("Carol", normal.Vigilante(), town)
    eve = core.Player("Eve", normal.Vanilla(), mafia)

    game.add_player(alice, bob, carol, eve)

    r.log_players(game)
    r.add_passives(game)
    game.visits.append(r.make_visit(game, alice, (bob,), AbilityType.ACTION, 0))
    game.visits.append(r.make_visit(game, carol, (alice,), AbilityType.ACTION, 0))
    game.visits.append(
        r.make_visit(game, eve, (bob,), AbilityType.SHARED_ACTION, 0, {"factional"}),
    )
    r.resolve_game(game)

    r.logger.info(pformat(game))

    assert "Vigilante" not in alice.death_causes, (
        "Expected Hider to protect from direct attacks."
    )
    assert not bob.is_alive, "Bob is alive, expected Mafia to kill."
    assert "Hider" in alice.death_causes, "Expected Hider to lifelink with Bob."


def test_traffic_analyst() -> None:
    r = LoggingResolver(logger)
    town = normal.Town()
    mafia = normal.Mafia()
    game = core.Game(start_phase=core.Phase.NIGHT)

    alice = core.Player("Alice", normal.Traffic_Analyst(), town)
    bob = core.Player("Bob", normal.Mason(), town)
    carol = core.Player("Carol", normal.Mason(), town)
    dave = core.Player("Dave", normal.Messenger(), town)
    eve = core.Player("Eve", normal.Vanilla(), mafia)

    game.add_player(alice, bob, carol, dave, eve)

    r.log_players(game)
    r.add_passives(game)
    game.visits.append(r.make_visit(game, alice, (bob,), AbilityType.ACTION, 0))
    r.resolve_game(game)

    game.phase, game.day_no = core.Phase.NIGHT, 2
    game.visits.append(r.make_visit(game, alice, (dave,), AbilityType.ACTION, 0))
    r.resolve_game(game)

    game.phase, game.day_no = core.Phase.NIGHT, 3
    game.visits.append(r.make_visit(game, alice, (eve,), AbilityType.ACTION, 0))
    r.resolve_game(game)

    r.logger.info(pformat(game))

    r.logger.info(alice.private_messages)
    assert (
        alice.private_messages[0].content
        == "Bob can communicate with other players privately!"
    ), "Bob can't communicate privately."
    assert (
        alice.private_messages[1].content
        == "Dave can communicate with other players privately!"
    ), "Dave can't communicate privately."
    assert (
        alice.private_messages[2].content
        == "Eve cannot communicate with other players privately."
    ), "Eve can communicate privately."


def test_universal_backup() -> None:
    r = LoggingResolver(logger)
    town = normal.Town()
    mafia = normal.Mafia()
    game = core.Game(start_phase=core.Phase.NIGHT)

    alice = core.Player("Alice", normal.Universal_Backup(), town)
    bob = core.Player("Bob", normal.Vigilante(), town)
    carol = core.Player("Carol", normal.Cop(), town)
    dave = core.Player("Dave", normal.Doctor(), mafia)
    eve = core.Player("Eve", normal.Vanilla(), mafia)

    game.add_player(alice, bob, carol, dave, eve)

    r.log_players(game)
    r.add_passives(game)
    game.visits.append(r.make_visit(game, bob, (carol,), AbilityType.ACTION, 0))
    game.visits.append(
        r.make_visit(game, eve, (dave,), AbilityType.SHARED_ACTION, 0, {"factional"}),
    )
    r.resolve_game(game)
    game.phase, game.day_no = core.Phase.DAY, 2
    r.add_passives(game)

    r.logger.info(pformat(game))
    assert not carol.is_alive, "Carol is alive, expected Vigilante to kill."
    assert not dave.is_alive, "Dave is alive, expected Mafia to kill."
    assert alice.actions[0].id == "Cop", "Alice erroneously did not gain Cop."
    assert alice.actions[0].id != "Doctor", "Alice erroneously gained Doctor."


def test_activated() -> None:
    r = LoggingResolver(logger)
    town = normal.Town()
    mafia = normal.Mafia()
    game = core.Game(start_phase=core.Phase.NIGHT)
    activated = normal.Activated()

    alice = core.Player("Alice", activated(normal.Bulletproof)(), town)
    bob = core.Player("Bob", activated(normal.Bulletproof)(), town)
    eve = core.Player("Eve", normal.Vanilla(), mafia)

    game.add_player(alice, bob, eve)

    r.log_players(game)
    r.add_passives(game)
    game.visits.append(r.make_visit(game, alice, (alice,), AbilityType.ACTION, 0))
    game.visits.append(
        r.make_visit(game, eve, (alice,), AbilityType.SHARED_ACTION, 0, {"factional"}),
    )
    game.visits.append(
        r.make_visit(game, eve, (bob,), AbilityType.SHARED_ACTION, 0, {"factional"}),
    )
    r.resolve_game(game)

    r.logger.info(pformat(game))

    assert alice.is_alive, "Alice is dead, expected Bulletproof to protect."
    assert not bob.is_alive, "Bob is alive, expected Bulletproof to not be activated."


def test_ninja() -> None:
    r = LoggingResolver(logger)
    town = normal.Town()
    mafia = normal.Mafia()
    game = core.Game(start_phase=core.Phase.NIGHT)

    alice = core.Player("Alice", normal.Watcher(), town)
    bob = core.Player("Bob", normal.Vanilla(), town)
    eve = core.Player("Eve", normal.Ninja(), mafia)

    game.add_player(alice, bob, eve)

    r.log_players(game)
    r.add_passives(game)
    game.visits.append(r.make_visit(game, eve, (eve,), AbilityType.ACTION, 0))
    game.visits.append(
        r.make_visit(game, eve, (bob,), AbilityType.SHARED_ACTION, 0, {"factional"}),
    )
    game.visits.append(r.make_visit(game, alice, (bob,), AbilityType.ACTION, 0))
    r.resolve_game(game)

    r.logger.info(pformat(game))

    r.logger.info(alice.private_messages)
    assert alice.private_messages[0].content == "Bob was not targeted by anyone.", (
        "Watcher erroneously detected Ninja."
    )


def test_personal() -> None:
    r = LoggingResolver(logger)
    town = normal.Town()
    mafia = normal.Mafia()
    game = core.Game(start_phase=core.Phase.NIGHT)
    personal = normal.Personal()

    alice = core.Player("Alice", personal(normal.Watcher)(), town)
    bob = core.Player("Bob", normal.Vanilla(), town)
    eve = core.Player("Eve", normal.Vanilla(), mafia)

    game.add_player(alice, bob, eve)

    r.log_players(game)
    r.add_passives(game)
    game.visits.append(
        r.make_visit(game, eve, (bob,), AbilityType.SHARED_ACTION, 0, {"factional"}),
    )
    game.visits.append(r.make_visit(game, alice, (bob,), AbilityType.ACTION, 0))
    r.resolve_game(game)

    r.logger.info(pformat(game))

    r.logger.info(alice.private_messages)
    assert alice.private_messages[0].content == "Bob was not targeted by anyone.", (
        "Watcher erroneously detected factional kill."
    )


def test_combine() -> None:
    r = LoggingResolver(logger)
    town = normal.Town()
    mafia = normal.Mafia()
    game = core.Game(start_phase=core.Phase.NIGHT)
    combined = core.Role.combine(normal.Bulletproof, normal.Cop)

    alice = core.Player("Alice", combined(), town)
    eve = core.Player("Eve", normal.Vanilla(), mafia)

    game.add_player(alice, eve)

    r.log_players(game)
    r.add_passives(game)
    game.visits.append(
        r.make_visit(game, eve, (alice,), AbilityType.SHARED_ACTION, 0, {"factional"}),
    )
    game.visits.append(r.make_visit(game, alice, (eve,), AbilityType.ACTION, 0))
    r.resolve_game(game)

    r.logger.info(pformat(game))

    assert alice.is_alive, "Alice is dead, expected Bulletproof to protect."
    assert alice.private_messages[0].content == "Eve is not aligned with the Town!.", (
        "Cop erroneously detected Town."
    )


def test_api_v1() -> None:  # noqa: PLR0915
    r = LoggingResolver(logger)
    app = Flask(__name__)
    app.register_blueprint(api_bp)
    with app.test_client() as client:
        response = client.post(
            "/api/v1/games",
            json={
                "players": ["Alice", "Bob", "Eve"],
                "roles": [
                    {
                        "role": {"type": "role", "id": "Vanilla"},
                        "alignment": "Town",
                    },
                    {
                        "role": {
                            "type": "combined_role",
                            "id": "Jack of All Trades",
                            "roles": [
                                {"type": "role", "id": "Doctor"},
                                {"type": "role", "id": "Cop"},
                            ],
                        },
                        "alignment": "Town",
                    },
                    {
                        "role": {
                            "type": "modifier",
                            "id": "X-Shot",
                            "params": {"max_uses": 1},
                            "role": {"type": "role", "id": "Juggernaut"},
                        },
                        "alignment": "Mafia",
                    },
                ],
                "shuffle_roles": False,
            },
        )
        if response.status_code != status.HTTP_201_CREATED:
            r.logger.info("%s %s\n", response.status_code, response.json)
            msg = "Expected 201 Created"
            raise AssertionError(msg)
        if response.json is None:
            msg = "Expected JSON response"
            raise AssertionError(msg)
        r.logger.info("%s %s\n", response.status_code, response.json)
        game_id = response.json["id"]
        mod_token = response.json["mod_token"]

    with app.test_client() as client:
        response = client.get(
            f"/api/v1/games/{game_id}",
            headers={"Authorization-Mod-Token": mod_token},
        )
        if response.status_code != status.HTTP_200_OK:
            r.logger.info("%s %s\n", response.status_code, response.json)
            msg = "Expected 200 OK"
            raise AssertionError(msg)
        assert response.json is not None, "Expected JSON response"
        r.logger.info("%s %s\n", response.status_code, response.json)
        assert response.json["players"][0]["name"] == "Alice"
        assert response.json["players"][0]["role_name"] == "Vanilla Townie"

    with app.test_client() as client:
        response = client.post(
            f"/api/v1/games/{game_id}/chats/global",
            json={"content": "Hello, world!"},
            headers={"Authorization-Player-Name": "Alice"},
        )
        r.logger.info("%s %s\n", response.status_code, response.json)
        assert response.status_code == status.HTTP_204_NO_CONTENT, (
            "Expected 204 No Content"
        )
        assert response.json is None, "Expected no JSON response"

    with app.test_client() as client:
        response = client.get(f"/api/v1/games/{game_id}/chats/global/messages")
        r.logger.info("%s %s\n", response.status_code, response.json)
        assert response.status_code == status.HTTP_200_OK, "Expected 200 OK"
        assert response.json is not None, "Expected JSON response"
        assert response.json["messages"][0]["content"] == "Hello, world!", (
            "Expected message to be sent"
        )
        assert response.json["messages"][0]["author"] == "Alice", (
            "Expected message to be sent by Alice"
        )

    with app.test_client() as client:
        response = client.get(
            f"/api/v1/games/{game_id}/chats/faction:Mafia",
            headers={"Authorization-Player-Name": "Alice"},
        )
        r.logger.info("%s %s\n", response.status_code, response.json)
        assert response.status_code == status.HTTP_404_NOT_FOUND, "Expected 404 Not Found"
        assert response.json is not None, "Expected JSON response"
        assert response.json["message"] == "Chat not found", "Expected 'Chat not found'"

    with app.test_client() as client:
        response = client.get(
            f"/api/v1/games/{game_id}/chats/faction:Mafia/messages",
            headers={"Authorization-Player-Name": "Eve"},
        )
        r.logger.info("%s %s\n", response.status_code, response.json)
        assert response.status_code == status.HTTP_200_OK, "Expected 200 OK"
        assert response.json is not None, "Expected JSON response"
        assert (
            response.json["messages"][0]["content"] == "Eve is a Mafia 1-Shot Juggernaut."
        ), "Expected message to be sent"
        assert response.json["messages"][0]["author"] == "Mafia", (
            "Expected message to be sent by Mafia"
        )

    with app.test_client() as client:
        response = client.post(
            f"/api/v1/games/{game_id}/players/Bob/abilities",
            json={
                "actions": {
                    "Doctor": {
                        "targets": ["Alice"],
                    },
                },
            },
            headers={"Authorization-Player-Name": "Bob"},
        )
        r.logger.info("%s %s\n", response.status_code, response.json)
        assert response.status_code == status.HTTP_400_BAD_REQUEST, (
            "Expected 400 Bad Request"
        )
        assert response.json is not None, "Expected JSON response"
        assert response.json["message"] == "Check failed for 'Doctor': Alice", (
            "Expected 'Check failed for 'Doctor': Alice'"
        )

    with app.test_client() as client:
        response = client.patch(
            f"/api/v1/games/{game_id}",
            json={"actions": ["next_phase"]},
            headers={"Authorization-Mod-Token": mod_token},
        )
        r.logger.info("%s %s\n", response.status_code, response.json)
        assert response.status_code == status.HTTP_204_NO_CONTENT, (
            "Expected 204 No Content"
        )
        assert response.json is None, "Expected no JSON response"

    with app.test_client() as client:
        response = client.post(
            f"/api/v1/games/{game_id}/players/Bob/abilities",
            json={
                "actions": {
                    "Doctor": {"targets": ["Alice"]},
                },
            },
            headers={"Authorization-Player-Name": "Bob"},
        )
        r.logger.info("%s %s\n", response.status_code, response.json)
        assert response.status_code == status.HTTP_204_NO_CONTENT, (
            "Expected 204 No Content"
        )
        assert response.json is None, "Expected no JSON response"

    with app.test_client() as client:
        response = client.post(
            f"/api/v1/games/{game_id}/players/Eve/abilities",
            json={
                "shared_actions": {
                    "Mafia Factional Kill": {"targets": ["Alice"]},
                },
            },
            headers={"Authorization-Player-Name": "Eve"},
        )
        r.logger.info("%s %s\n", response.status_code, response.json)
        assert response.status_code == status.HTTP_204_NO_CONTENT, (
            "Expected 204 No Content"
        )
        assert response.json is None, "Expected no JSON response"

    with app.test_client() as client:
        response = client.patch(
            f"/api/v1/games/{game_id}",
            json={"actions": ["resolve"]},
            headers={"Authorization-Mod-Token": mod_token},
        )
        r.logger.info("%s %s\n", response.status_code, response.json)
        assert response.status_code == status.HTTP_204_NO_CONTENT, (
            "Expected 204 No Content"
        )
        assert response.json is None, "Expected no JSON response"

    with app.test_client() as client:
        response = client.get(f"/api/v1/games/{game_id}")
        r.logger.info("%s %s\n", response.status_code, response.json)
        assert response.status_code == status.HTTP_200_OK, "Expected 200 OK"
        assert response.json is not None, "Expected JSON response"
        assert response.json["players"][0]["is_alive"], "Expected Alice to be alive"
        assert response.json["players"][1]["is_alive"], "Expected Bob to be alive"
        assert response.json["players"][2]["is_alive"], "Expected Eve to be alive"
        assert response.json["phase"] == core.Phase.NIGHT.value, (
            "Expected phase to be NIGHT"
        )

    with app.test_client() as client:
        response = client.post(
            f"/api/v1/games/{game_id}/players/Eve/abilities",
            json={
                "actions": {
                    "Juggernaut": {"targets": ["Eve"]},
                },
                "shared_actions": {"Mafia Factional Kill": {"targets": ["Bob"]}},
            },
            headers={"Authorization-Player-Name": "Eve"},
        )
        r.logger.info("%s %s\n", response.status_code, response.json)
        assert response.status_code == status.HTTP_204_NO_CONTENT, (
            "Expected 204 No Content"
        )
        assert response.json is None, "Expected no JSON response"

    with app.test_client() as client:
        response = client.post(
            f"/api/v1/games/{game_id}/players/Bob/abilities",
            json={
                "actions": {
                    "Doctor": {"targets": ["Alice"]},
                },
            },
            headers={"Authorization-Player-Name": "Bob"},
        )
        r.logger.info("%s %s\n", response.status_code, response.json)
        assert response.status_code == status.HTTP_400_BAD_REQUEST, (
            "Expected 400 Bad Request"
        )
        assert response.json is not None, "Expected JSON response"
        assert response.json["message"] == "Check failed for 'Doctor': Alice", (
            "Expected 'Check failed for 'Doctor': Alice'"
        )


def test_voting() -> None:
    r = LoggingResolver(logger)
    town = normal.Town()
    mafia = normal.Mafia()
    game = core.Game(start_phase=core.Phase.DAY)

    alice = core.Player("Alice", normal.Vanilla(), town)
    bob = core.Player("Bob", normal.Vanilla(), town)
    eve = core.Player("Eve", normal.Vanilla(), mafia)

    game.add_player(alice, bob, eve)

    r.log_players(game)
    r.add_passives(game)

    r.logger.info("%s", game.time)

    assert r.vote_ongoing(game), "Vote is not ongoing"
    game.vote(alice, eve)
    assert r.vote_ongoing(game), "Vote is not ongoing before hammer"

    game.vote(bob, eve)
    assert not r.vote_ongoing(game), "Vote is still ongoing after hammer"
    r.logger.info(pformat(elim := r.resolve_vote(game)))
    assert elim is eve, "Vote did not resolve to Eve"
    assert not eve.is_alive, "Eve is alive, expected to be killed"
    assert eve.death_causes == ["Vote"], "Eve's death cause is not Vote"
    assert game.time == (1, core.Phase.NIGHT), "Game did not advance to night"
    assert not r.vote_ongoing(game), "Vote is ongoing during night"


TESTS: dict[str, Callable[[], None]] = {
    "catastrophic_rule": test_catastrophic_rule,
    "xshot_role": test_xshot_role,
    "protection": test_protection,
    "xshot_macho": test_xshot_macho,
    "tracker_roleblocker": test_tracker_roleblocker,
    "juggernaut": test_juggernaut,
    "investigative_fail": test_investigative_fail,
    "ascetic": test_ascetic,
    "detective": test_detective,
    "jack_of_all_trades": test_jack_of_all_trades,
    "hider": test_hider,
    "traffic_analyst": test_traffic_analyst,
    "universal_backup": test_universal_backup,
    "activated": test_activated,
    "ninja": test_ninja,
    "personal": test_personal,
    "combine": test_combine,
    "api_v1": test_api_v1,
    "voting": test_voting,
}
