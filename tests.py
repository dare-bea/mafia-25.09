from sys import stdout
from typing import Callable
from pprint import pprint
from mafia import core
from mafia.core import AbilityType as AT
from mafia.core import VisitStatus as VS
from mafia import normal
from mafia.api.v1 import api_bp
from flask import Flask

class PrintResolver(normal.Resolver):
    def resolve_visit(self, game: core.Game, visit: core.Visit) -> int:
        resolved_visits = set(v for v in game.visits if v.status is VS.PENDING) - {visit}

        result = super().resolve_visit(game, visit)

        print(visit)
        resolved_visits -= set(v for v in game.visits if v.status is VS.PENDING)
        for v in resolved_visits:
            print(f"    {v}")
        return result

    def resolve_cycles(self, game: core.Game) -> bool:
        resolved_visits = set(v for v in game.visits if v.status is VS.PENDING)
        successfully_resolved = super().resolve_cycles(game)
        resolved_visits -= set(v for v in game.visits if v.status is VS.PENDING)
        print("Cycle detected, resolving...")
        for v in resolved_visits:
            print(f"    {v}")
        return successfully_resolved

    def print_players(self, game: core.Game) -> None:
        for player in game.players:
            print(f"{player}: {player.role_name}")
            print(f"  Actions: {player.actions}")
            print(f"  Passives: {player.passives}")
            print(f"  Shared Actions: {player.shared_actions}")
            print()


def test_catastrophic_rule() -> None:
    r = PrintResolver()

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

    for player in game.players:
        print(f"{player}: {player.role_name}")
        print(f"  Actions: {player.actions}")
        print(f"  Passives: {player.passives}")
        print(f"  Shared Actions: {player.shared_actions}")
        print()

    r.add_passives(game)

    game.visits.append(r.make_visit(game, eve, (alice,), AT.SHARED_ACTION, 0, {"factional"}))
    game.visits.append(r.make_visit(game, bob, (eve,), AT.ACTION, 0))
    game.visits.append(r.make_visit(game, eve, (bob,), AT.ACTION, 0))
    game.visits.append(r.make_visit(game, eve, (alice,), AT.ACTION, 0))
    game.visits.append(r.make_visit(game, alice, (eve,), AT.ACTION, 0))

    r.resolve_game(game)
    print()

    pprint(game)

    assert game.visits[4].status != VS.FAILURE and all(
        v.status == VS.FAILURE for v in game.visits[:4]
    )


def test_xshot_role() -> None:
    r = PrintResolver()

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

    for player in game.players:
        print(f"{player}: {player.role_name}")
        print(f"  Actions: {player.actions}")
        print(f"  Passives: {player.passives}")
        print(f"  Shared Actions: {player.shared_actions}")
        print()

    game.phase, game.day_no = core.Phase.NIGHT, 1
    r.add_passives(game)

    if alice.actions[0].check(game, alice, (bob,)):
        print(f"{alice.name} is using {alice.actions[0].id} on {bob.name}.")
        game.visits.append(r.make_visit(game, alice, (bob,), AT.ACTION, 0))
    else:
        print(f"{alice.name} cannot use {alice.actions[0].id} on {bob.name}.")
        raise AssertionError("Expected check to succeed.")
    game.visits.append(r.make_visit(game, eve, (bob,), AT.SHARED_ACTION, 0, {"factional"}))
    r.resolve_game(game)
    assert bob.is_alive, "Bob is dead, expected Bulletproof to protect."
    print()

    game.phase, game.day_no = core.Phase.NIGHT, 2
    if alice.actions[0].check(game, alice, (eve,)):
        print(f"{alice.name} is using {alice.actions[0].id} on {eve.name}.")
        game.visits.append(r.make_visit(game, alice, (eve,), AT.ACTION, 0))
        raise AssertionError("Expected check to fail.")
    else:
        print(f"{alice.name} cannot use {alice.actions[0].id} on {eve.name}.")
    game.visits.append(r.make_visit(game, eve, (bob,), AT.SHARED_ACTION, 0, {"factional"}))
    r.resolve_game(game)
    print()
    pprint(game)

    assert not bob.is_alive, "Bob is alive, expected 1-Shot Bulletproof to be used."


def test_protection() -> None:
    r = PrintResolver()

    town = normal.Town()
    mafia = normal.Mafia()

    game = core.Game(start_phase=core.Phase.NIGHT)
    alice = core.Player("Alice", normal.Doctor(), town)
    bob = core.Player("Bob", normal.Vanilla(), town)
    eve = core.Player("Eve", normal.Vanilla(), mafia)

    game.add_player(alice, bob, eve)

    for player in game.players:
        print(f"{player}: {player.role_name}")
        print(f"  Actions: {player.actions}")
        print(f"  Passives: {player.passives}")
        print(f"  Shared Actions: {player.shared_actions}")
        print()

    r.add_passives(game)
    game.visits.append(r.make_visit(game, alice, (bob,), AT.ACTION, 0))
    game.visits.append(r.make_visit(game, eve, (bob,), AT.SHARED_ACTION, 0, {"factional"}))

    r.resolve_game(game)
    print()
    pprint(game)

    assert bob.is_alive, "Bob is dead."


def test_xshot_macho() -> None:
    r = PrintResolver()

    town = normal.Town()
    mafia = normal.Mafia()

    game = core.Game(start_phase=core.Phase.NIGHT)
    alice = core.Player("Alice", normal.Doctor(), town)
    bob = core.Player("Bob", normal.XShot(1)(normal.Macho)(), town)
    carol = core.Player("Carol", normal.XShot(1)(normal.Macho)(), town)
    eve = core.Player("Eve", normal.Vanilla(), mafia)

    game.add_player(alice, bob, carol, eve)

    for player in game.players:
        print(f"{player}: {player.role_name}")
        print(f"  Actions: {player.actions}")
        print(f"  Passives: {player.passives}")
        print(f"  Shared Actions: {player.shared_actions}")
        print()

    r.add_passives(game)
    game.visits.append(r.make_visit(game, alice, (bob,), AT.ACTION, 0))
    game.visits.append(r.make_visit(game, alice, (carol,), AT.ACTION, 0))
    game.visits.append(r.make_visit(game, alice, (carol,), AT.ACTION, 0))
    game.visits.append(r.make_visit(game, eve, (bob,), AT.SHARED_ACTION, 0, {"factional"}))
    game.visits.append(r.make_visit(game, eve, (carol,), AT.SHARED_ACTION, 0, {"factional"}))

    r.resolve_game(game)
    print()
    pprint(game)

    assert not bob.is_alive, "Bob is alive."
    assert carol.is_alive, "Carol is dead."


def test_tracker_roleblocker() -> None:
    r = PrintResolver()

    town = normal.Town()
    mafia = normal.Mafia()

    game = core.Game(start_phase=core.Phase.NIGHT)
    alice = core.Player("Alice", normal.Roleblocker(), town)
    bob = core.Player("Bob", normal.Tracker(), town)
    eve = core.Player("Eve", normal.Vanilla(), mafia)

    game.add_player(alice, bob, eve)

    for player in game.players:
        print(f"{player}: {player.role_name}")
        print(f"  Actions: {player.actions}")
        print(f"  Passives: {player.passives}")
        print(f"  Shared Actions: {player.shared_actions}")
        print()

    r.add_passives(game)
    game.visits.append(r.make_visit(game, alice, (eve,), AT.ACTION, 0))
    game.visits.append(r.make_visit(game, bob, (eve,), AT.ACTION, 0))
    game.visits.append(r.make_visit(game, eve, (bob,), AT.SHARED_ACTION, 0, {"factional"}))

    r.resolve_game(game)
    print()
    pprint(game)

    print(bob.private_messages)
    assert bob.private_messages[0].content == "Eve did not target anyone."


def test_juggernaut() -> None:
    r = PrintResolver()

    town = normal.Town()
    mafia = normal.Mafia()

    game = core.Game(start_phase=core.Phase.NIGHT)
    alice = core.Player("Alice", normal.Roleblocker(), town)
    bob = core.Player("Bob", normal.Vanilla(), town)
    eve = core.Player("Eve", normal.Juggernaut(), mafia)

    game.add_player(alice, bob, eve)

    for player in game.players:
        print(f"{player}: {player.role_name}")
        print(f"  Actions: {player.actions}")
        print(f"  Passives: {player.passives}")
        print(f"  Shared Actions: {player.shared_actions}")
        print()

    r.add_passives(game)
    game.visits.append(r.make_visit(game, alice, (eve,), AT.ACTION, 0))
    game.visits.append(r.make_visit(game, eve, (eve,), AT.ACTION, 0))
    game.visits.append(r.make_visit(game, eve, (bob,), AT.SHARED_ACTION, 0, {"factional"}))

    r.resolve_game(game)
    print()
    pprint(game)

    assert not bob.is_alive, "Factional Kill was roleblocked, expected Juggernaut to force kill."


def test_investigative_fail() -> None:
    r = PrintResolver()
    town = normal.Town()
    mafia = normal.Mafia()
    game = core.Game(start_phase=core.Phase.NIGHT)

    alice = core.Player("Alice", normal.Roleblocker(), town)
    bob = core.Player("Bob", normal.Cop(), town)
    eve = core.Player("Eve", normal.Vanilla(), mafia)

    game.add_player(alice, bob, eve)

    r.print_players(game)
    r.add_passives(game)
    game.visits.append(r.make_visit(game, alice, (bob,), AT.ACTION, 0))
    game.visits.append(r.make_visit(game, bob, (eve,), AT.ACTION, 0))
    r.resolve_game(game)
    print()
    pprint(game)
    print(bob.private_messages)

    assert (
        bob.private_messages[0].content == "Your ability failed, and you did not recieve a result."
    ), "Bob's Cop did not fail."


def test_ascetic() -> None:
    r = PrintResolver()
    town = normal.Town()
    mafia = normal.Mafia()
    game = core.Game(start_phase=core.Phase.NIGHT)

    alice = core.Player("Alice", normal.Ascetic(), town)
    bob = core.Player("Bob", normal.Doctor(), town)
    eve = core.Player("Eve", normal.Vanilla(), mafia)

    game.add_player(alice, bob, eve)

    r.print_players(game)
    r.add_passives(game)
    game.visits.append(r.make_visit(game, bob, (alice,), AT.ACTION, 0))
    game.visits.append(r.make_visit(game, eve, (alice,), AT.SHARED_ACTION, 0, {"factional"}))
    r.resolve_game(game)
    print()
    pprint(game)

    assert not alice.is_alive, "Alice is alive, expected Ascetic to prevent protection."


def test_detective() -> None:
    r = PrintResolver()
    town = normal.Town()
    mafia = normal.Mafia()
    game = core.Game(start_phase=core.Phase.NIGHT)

    alice = core.Player("Alice", normal.Detective(), town)
    bob = core.Player("Bob", normal.Vanilla(), town)
    eve = core.Player("Eve", normal.Vanilla(), mafia)

    game.add_player(alice, bob, eve)

    r.print_players(game)
    r.add_passives(game)
    game.visits.append(r.make_visit(game, eve, (bob,), AT.SHARED_ACTION, 0, {"factional"}))
    r.resolve_game(game)
    print()

    game.phase, game.day_no = core.Phase.NIGHT, 2
    game.visits.append(r.make_visit(game, alice, (eve,), AT.ACTION, 0))
    r.resolve_game(game)
    print()
    pprint(game)
    print(alice.private_messages)

    assert alice.private_messages[0].content == "Eve has tried to kill someone!", (
        "Detective did not detect kill."
    )


def test_jack_of_all_trades() -> None:
    r = PrintResolver()
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

    r.print_players(game)
    r.add_passives(game)
    game.visits.append(r.make_visit(game, alice, (bob,), AT.ACTION, 1))
    game.visits.append(r.make_visit(game, eve, (bob,), AT.SHARED_ACTION, 0, {"factional"}))
    r.resolve_game(game)
    print()
    pprint(game)

    assert bob.is_alive, "Bob is dead, expected Doctor to protect."
    assert alice.actions[0].check(game, alice, (bob,)), "Cop is not usable."
    assert not alice.actions[1].check(game, alice, (bob,)), "Doctor is still usable."


def test_hider() -> None:
    r = PrintResolver()
    town = normal.Town()
    mafia = normal.Mafia()
    game = core.Game(start_phase=core.Phase.NIGHT)

    alice = core.Player("Alice", normal.Hider(), town)
    bob = core.Player("Bob", normal.Vanilla(), town)
    carol = core.Player("Carol", normal.Vigilante(), town)
    eve = core.Player("Eve", normal.Vanilla(), mafia)

    game.add_player(alice, bob, carol, eve)

    r.print_players(game)
    r.add_passives(game)
    game.visits.append(r.make_visit(game, alice, (bob,), AT.ACTION, 0))
    game.visits.append(r.make_visit(game, carol, (alice,), AT.ACTION, 0))
    game.visits.append(r.make_visit(game, eve, (bob,), AT.SHARED_ACTION, 0, {"factional"}))
    r.resolve_game(game)
    print()
    pprint(game)

    assert "Vigilante" not in alice.death_causes, "Expected Hider to protect from direct attacks."
    assert not bob.is_alive, "Bob is alive, expected Mafia to kill."
    assert "Hider" in alice.death_causes, "Expected Hider to lifelink with Bob."


def test_traffic_analyst() -> None:
    r = PrintResolver()
    town = normal.Town()
    mafia = normal.Mafia()
    game = core.Game(start_phase=core.Phase.NIGHT)

    alice = core.Player("Alice", normal.Traffic_Analyst(), town)
    bob = core.Player("Bob", normal.Mason(), town)
    carol = core.Player("Carol", normal.Mason(), town)
    dave = core.Player("Dave", normal.Messenger(), town)
    eve = core.Player("Eve", normal.Vanilla(), mafia)

    game.add_player(alice, bob, carol, dave, eve)

    r.print_players(game)
    r.add_passives(game)
    game.visits.append(r.make_visit(game, alice, (bob,), AT.ACTION, 0))
    r.resolve_game(game)

    game.phase, game.day_no = core.Phase.NIGHT, 2
    game.visits.append(r.make_visit(game, alice, (dave,), AT.ACTION, 0))
    r.resolve_game(game)

    game.phase, game.day_no = core.Phase.NIGHT, 3
    game.visits.append(r.make_visit(game, alice, (eve,), AT.ACTION, 0))
    r.resolve_game(game)
    print()
    pprint(game)

    print(alice.private_messages)
    assert (
        alice.private_messages[0].content == "Bob can communicate with other players privately!"
    ), "Bob can't communicate privately."
    assert (
        alice.private_messages[1].content == "Dave can communicate with other players privately!"
    ), "Dave can't communicate privately."
    assert (
        alice.private_messages[2].content == "Eve cannot communicate with other players privately."
    ), "Eve can communicate privately."


def test_universal_backup() -> None:
    r = PrintResolver()
    town = normal.Town()
    mafia = normal.Mafia()
    game = core.Game(start_phase=core.Phase.NIGHT)

    alice = core.Player("Alice", normal.Universal_Backup(), town)
    bob = core.Player("Bob", normal.Vigilante(), town)
    carol = core.Player("Carol", normal.Cop(), town)
    dave = core.Player("Dave", normal.Doctor(), mafia)
    eve = core.Player("Eve", normal.Vanilla(), mafia)

    game.add_player(alice, bob, carol, dave, eve)

    r.print_players(game)
    r.add_passives(game)
    game.visits.append(r.make_visit(game, bob, (carol,), AT.ACTION, 0))
    game.visits.append(r.make_visit(game, eve, (dave,), AT.SHARED_ACTION, 0, {"factional"}))
    r.resolve_game(game)
    game.phase, game.day_no = core.Phase.DAY, 2
    r.add_passives(game)
    print()
    pprint(game)
    assert not carol.is_alive, "Carol is alive, expected Vigilante to kill."
    assert not dave.is_alive, "Dave is alive, expected Mafia to kill."
    assert alice.actions[0].id == "Cop", "Alice erroneously did not gain Cop."
    assert alice.actions[0].id != "Doctor", "Alice erroneously gained Doctor."


def test_activated() -> None:
    r = PrintResolver()
    town = normal.Town()
    mafia = normal.Mafia()
    game = core.Game(start_phase=core.Phase.NIGHT)
    activated = normal.Activated()

    alice = core.Player("Alice", activated(normal.Bulletproof)(), town)
    bob = core.Player("Bob", activated(normal.Bulletproof)(), town)
    eve = core.Player("Eve", normal.Vanilla(), mafia)

    game.add_player(alice, bob, eve)

    r.print_players(game)
    r.add_passives(game)
    game.visits.append(r.make_visit(game, alice, (alice,), AT.ACTION, 0))
    game.visits.append(r.make_visit(game, eve, (alice,), AT.SHARED_ACTION, 0, {"factional"}))
    game.visits.append(r.make_visit(game, eve, (bob,), AT.SHARED_ACTION, 0, {"factional"}))
    r.resolve_game(game)
    print()
    pprint(game)

    assert alice.is_alive, "Alice is dead, expected Bulletproof to protect."
    assert not bob.is_alive, "Bob is alive, expected Bulletproof to not be activated."


def test_ninja() -> None:
    r = PrintResolver()
    town = normal.Town()
    mafia = normal.Mafia()
    game = core.Game(start_phase=core.Phase.NIGHT)

    alice = core.Player("Alice", normal.Watcher(), town)
    bob = core.Player("Bob", normal.Vanilla(), town)
    eve = core.Player("Eve", normal.Ninja(), mafia)

    game.add_player(alice, bob, eve)

    r.print_players(game)
    r.add_passives(game)
    game.visits.append(r.make_visit(game, eve, (eve,), AT.ACTION, 0))
    game.visits.append(r.make_visit(game, eve, (bob,), AT.SHARED_ACTION, 0, {"factional"}))
    game.visits.append(r.make_visit(game, alice, (bob,), AT.ACTION, 0))
    r.resolve_game(game)
    print()
    pprint(game)

    print(alice.private_messages)
    assert alice.private_messages[0].content == "Bob was not targeted by anyone.", (
        "Watcher erroneously detected Ninja."
    )


def test_personal() -> None:
    r = PrintResolver()
    town = normal.Town()
    mafia = normal.Mafia()
    game = core.Game(start_phase=core.Phase.NIGHT)
    personal = normal.Personal()

    alice = core.Player("Alice", personal(normal.Watcher)(), town)
    bob = core.Player("Bob", normal.Vanilla(), town)
    eve = core.Player("Eve", normal.Vanilla(), mafia)

    game.add_player(alice, bob, eve)

    r.print_players(game)
    r.add_passives(game)
    game.visits.append(r.make_visit(game, eve, (bob,), AT.SHARED_ACTION, 0, {"factional"}))
    game.visits.append(r.make_visit(game, alice, (bob,), AT.ACTION, 0))
    r.resolve_game(game)
    print()
    pprint(game)

    print(alice.private_messages)
    assert alice.private_messages[0].content == "Bob was not targeted by anyone.", (
        "Watcher erroneously detected factional kill."
    )


def test_combine() -> None:
    r = PrintResolver()
    town = normal.Town()
    mafia = normal.Mafia()
    game = core.Game(start_phase=core.Phase.NIGHT)
    combined = core.Role.combine(normal.Bulletproof, normal.Cop)

    alice = core.Player("Alice", combined(), town)
    eve = core.Player("Eve", normal.Vanilla(), mafia)

    game.add_player(alice, eve)

    r.print_players(game)
    r.add_passives(game)
    game.visits.append(r.make_visit(game, eve, (alice,), AT.SHARED_ACTION, 0, {"factional"}))
    game.visits.append(r.make_visit(game, alice, (eve,), AT.ACTION, 0))
    r.resolve_game(game)
    print()
    pprint(game)

    assert alice.is_alive, "Alice is dead, expected Bulletproof to protect."
    assert alice.private_messages[0].content == "Eve is not aligned with the Town!.", (
        "Cop erroneously detected Town."
    )

def test_api_v1() -> None:
    app = Flask(__name__)
    app.register_blueprint(api_bp)
    with app.test_client() as client:
        response = client.post(
            "/api/v1/games",
            json={
                "players": ["Alice", "Bob", "Eve"],
                "roles": [
                    {
                        "role": {
                            "type": "role",
                            "id": "Vanilla"
                        },
                        "alignment": "Town"
                    },
                    {
                        "role": {
                            "type": "combined_role",
                            "id": "Jack of All Trades",
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
                    {
                        "role": {
                            "type": "modifier",
                            "id": "X-Shot",
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
                ],
                "shuffle_roles": False,
            }
        )
        if response.status_code != 201:
            print(response.status_code, response.json, "\n")
            raise AssertionError("Expected 201 Created")
        elif response.json is None:
            raise AssertionError("Expected JSON response")
        else:
            print(response.status_code, response.json, "\n")
            game_id = response.json["id"]
            mod_token = response.json["mod_token"]

    with app.test_client() as client:
        response = client.get(
            f"/api/v1/games/{game_id}",
            headers={"Authorization-Mod-Token": mod_token}
        )
        if response.status_code != 200:
            print(response.status_code, response.json, "\n")
            raise AssertionError("Expected 200 OK")
        elif response.json is None:
            raise AssertionError("Expected JSON response")
        else:
            print(response.status_code, response.json, "\n")
            assert response.json["players"][0]["name"] == "Alice"
            assert response.json["players"][0]["role_name"] == "Vanilla Townie"

    with app.test_client() as client:
        response = client.post(
            f"/api/v1/games/{game_id}/chats/global",
            json={"content": "Hello, world!"},
            headers={"Authorization-Player-Name": "Alice"},
        )
        print(response.status_code, response.json, "\n")
        assert response.status_code == 204, "Expected 204 No Content"
        assert response.json is None, "Expected no JSON response"

    with app.test_client() as client:
        response = client.get(f"/api/v1/games/{game_id}/chats/global/messages")
        print(response.status_code, response.json, "\n")
        assert response.status_code == 200, "Expected 200 OK"
        assert response.json is not None, "Expected JSON response"
        assert response.json["messages"][0]["content"] == "Hello, world!", "Expected message to be sent"
        assert response.json["messages"][0]["author"] == "Alice", "Expected message to be sent by Alice"

    with app.test_client() as client:
        response = client.get(
            f"/api/v1/games/{game_id}/chats/faction:Mafia", 
            headers={"Authorization-Player-Name": "Alice"}
        )
        print(response.status_code, response.json, "\n")
        assert response.status_code == 404, "Expected 404 Not Found"
        assert response.json is not None, "Expected JSON response"
        assert response.json["message"] == "Chat not found", "Expected 'Chat not found'"

    with app.test_client() as client:
        response = client.get(
            f"/api/v1/games/{game_id}/chats/faction:Mafia/messages",
            headers={"Authorization-Player-Name": "Eve"}
        )
        print(response.status_code, response.json, "\n")
        assert response.status_code == 200, "Expected 200 OK"
        assert response.json is not None, "Expected JSON response"
        assert response.json["messages"][0]["content"] == "Eve is a Mafia 1-Shot Juggernaut.", "Expected message to be sent"
        assert response.json["messages"][0]["author"] == "Mafia", "Expected message to be sent by Mafia"

    with app.test_client() as client:
        response = client.post(
            f"/api/v1/games/{game_id}/players/Bob/abilities",
            json={
                "actions": {
                    "Doctor": {
                        "targets": ["Alice"],
                    },
                }
            },
            headers={"Authorization-Player-Name": "Bob"}
        )
        print(response.status_code, response.json, "\n")
        assert response.status_code == 400, "Expected 400 Bad Request"
        assert response.json is not None, "Expected JSON response"
        assert response.json["message"] == "Check failed for 'Doctor': Alice", "Expected 'Check failed for 'Doctor': Alice'"

    with app.test_client() as client:
        response = client.patch(
            f"/api/v1/games/{game_id}",
            json={"actions": ["next_phase"]},
            headers={"Authorization-Mod-Token": mod_token}
        )
        print(response.status_code, response.json, "\n")
        assert response.status_code == 204, "Expected 204 No Content"
        assert response.json is None, "Expected no JSON response"

    with app.test_client() as client:
        response = client.post(
            f"/api/v1/games/{game_id}/players/Bob/abilities",
            json={
                "actions": {
                    "Doctor": {
                        "targets": ["Alice"]
                    },
                }
            },
            headers={"Authorization-Player-Name": "Bob"}
        )
        print(response.status_code, response.json, "\n")
        assert response.status_code == 204, "Expected 204 No Content"
        assert response.json is None, "Expected no JSON response"

    with app.test_client() as client:
        response = client.post(
            f"/api/v1/games/{game_id}/players/Eve/abilities",
            json={
                "shared_actions": {
                    "Mafia Factional Kill": {
                        "targets": ["Alice"]
                    },
                }
            },
            headers={"Authorization-Player-Name": "Eve"}
        )
        print(response.status_code, response.json, "\n")
        assert response.status_code == 204, "Expected 204 No Content"
        assert response.json is None, "Expected no JSON response"

    with app.test_client() as client:
        response = client.patch(
            f"/api/v1/games/{game_id}",
            json={"actions": ["resolve"]},
            headers={"Authorization-Mod-Token": mod_token}
        )
        print(response.status_code, response.json, "\n")
        assert response.status_code == 204, "Expected 204 No Content"
        assert response.json is None, "Expected no JSON response"

    with app.test_client() as client:
        response = client.get(f"/api/v1/games/{game_id}")
        print(response.status_code, response.json, "\n")
        assert response.status_code == 200, "Expected 200 OK"
        assert response.json is not None, "Expected JSON response"
        assert response.json["players"][0]["is_alive"], "Expected Alice to be alive"
        assert response.json["players"][1]["is_alive"], "Expected Bob to be alive"
        assert response.json["players"][2]["is_alive"], "Expected Eve to be alive"
        assert response.json["phase"] == core.Phase.NIGHT.value, "Expected phase to be NIGHT"

    with app.test_client() as client:
        response = client.post(
            f"/api/v1/games/{game_id}/players/Eve/abilities",
            json={
                "actions": {
                    "Juggernaut": {
                        "targets": ["Eve"]
                    },
                },
                "shared_actions": {
                    "Mafia Factional Kill": {
                        "targets": ["Bob"]
                    }
                }
            },
            headers={"Authorization-Player-Name": "Eve"}
        )
        print(response.status_code, response.json, "\n")
        assert response.status_code == 204, "Expected 204 No Content"
        assert response.json is None, "Expected no JSON response"

    with app.test_client() as client:
        response = client.post(
            f"/api/v1/games/{game_id}/players/Bob/abilities",
            json={
                "actions": {
                    "Doctor": {
                        "targets": ["Alice"]
                    },
                }
            },
            headers={"Authorization-Player-Name": "Bob"}
        )
        print(response.status_code, response.json, "\n")
        assert response.status_code == 400, "Expected 400 Bad Request"
        assert response.json is not None, "Expected JSON response"
        assert response.json["message"] == "Check failed for 'Doctor': Alice", "Expected 'Check failed for 'Doctor': Alice'"

def test_voting() -> None:
    r = PrintResolver()
    town = normal.Town()
    mafia = normal.Mafia()
    game = core.Game(start_phase=core.Phase.DAY)

    alice = core.Player("Alice", normal.Vanilla(), town)
    bob = core.Player("Bob", normal.Vanilla(), town)
    eve = core.Player("Eve", normal.Vanilla(), mafia)

    game.add_player(alice, bob, eve)

    r.print_players(game)
    r.add_passives(game)

    assert r.vote_ongoing(game), "Vote is not ongoing"
    game.vote(alice, eve)
    assert r.vote_ongoing(game), "Vote is not ongoing before hammer"
    
    game.vote(bob, eve)
    assert not r.vote_ongoing(game), "Vote is still ongoing after hammer"
    pprint(elim := r.resolve_vote(game))
    assert elim is eve, "Vote did not resolve to Eve"
    assert not eve.is_alive, "Eve is alive, expected to be killed"
    assert eve.death_causes == ["Vote"], "Eve's death cause is not Vote"
    assert game.time == (1, core.Phase.NIGHT), "Game did not advance to night"
    assert not r.vote_ongoing(game), "Vote is ongoing during night"

# DO TESTS #

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
    "voting": test_voting
}

def main() -> int:
    from os import makedirs
    from sys import stderr, argv
    from contextlib import redirect_stdout
    from pathlib import Path
    from traceback import print_exception

    verbose = "--verbose" in argv or "-v" in argv
    mypy_abort_if_error = "--mypy-abort" in argv or "-ma" in argv
    mypy_verbose = "--mypy-verbose" in argv or "-mv" in argv
    use_mypy = "--mypy" in argv or "-m" in argv or mypy_abort_if_error or mypy_verbose
    mypy_verbose = mypy_verbose or verbose
    if "--all" in argv or "-a" in argv:
        verbose = True
        use_mypy = True
        mypy_verbose = True
    if "-mav" in argv or "-mva" in argv or "--mypy-abort-verbose" in argv or "--mypy-verbose-abort" in argv:
        use_mypy = True
        mypy_verbose = True
        mypy_abort_if_error = True

    successes: int = 0
    failed_tests: list[str] = []
    DIR = Path(__file__).parent
    makedirs(DIR / "results", exist_ok=True)
    for test_name, test_func in TESTS.items():
        if verbose:
            print(f"## TESTING: {test_name}() ##")
        try:
            with open(DIR / "results" / f"{test_name}.log", "w") as f:
                with redirect_stdout(f):
                    test_func()
        except Exception as e:
            if verbose:
                with open(DIR / "results" / f"{test_name}.log", "r") as f:
                    print(f.read())
                print_exception(e)
            with open(DIR / "results" / f"{test_name}.log", "a") as f:
                print_exception(e, file=f)
            print(f"## TEST {test_name} FAILED ##")
            failed_tests.append(test_name)
        else:
            if verbose:
                with open(DIR / "results" / f"{test_name}.log", "r") as f:
                    print(f.read())
            print(f"## TEST {test_name} PASSED ##")
            successes += 1
        if verbose:
            print()

    print(f"{successes}/{len(TESTS)} tests succeeded! ({successes / len(TESTS):.1%})")
    if failed_tests:
        print("Failed tests:", file=stderr)
        for test_name in failed_tests:
            print(f"    {test_name}", file=stderr)
    print()

    if use_mypy:
        try:
            import mypy.api
        except ImportError:
            print("Could not find module 'mypy.api'. Skipping type-checking...")
        else:
            for x in range(11, 15):
                print(f"Type-checking Python 3.{x}:")
                result = mypy.api.run(
                    ["--python-version", f"3.{x}", "--strict", "--pretty", str(DIR)] if mypy_verbose else
                    ["--python-version", f"3.{x}", "--strict", "--no-pretty", str(DIR)]
                )
                if result[0]:
                    print(result[0].rstrip(), file=stdout)
    
                if result[1]:
                    print(result[1].rstrip(), file=stderr)

                if result[2] and mypy_abort_if_error:
                    print("Type-checking failed.")
                    return 1

    if successes != len(TESTS):
        return 1
    return 0

if __name__ == "__main__":
    exit(main())
