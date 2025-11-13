from sys import stdout
from typing import Callable
import mafia as m
from mafia import AbilityType as AT
from mafia import VisitStatus as VS
import examples
from pprint import pprint


class PrintResolver(examples.Resolver):
    def resolve_visit(self, game: m.Game, visit: m.Visit) -> int:
        resolved_visits = set(v for v in game.visits if v.status is VS.PENDING) - {visit}

        result = super().resolve_visit(game, visit)

        print(visit)
        resolved_visits -= set(v for v in game.visits if v.status is VS.PENDING)
        for v in resolved_visits:
            print(f"    {v}")
        return result

    def resolve_cycles(self, game: m.Game) -> bool:
        resolved_visits = set(v for v in game.visits if v.status is VS.PENDING)
        successfully_resolved = super().resolve_cycles(game)
        resolved_visits -= set(v for v in game.visits if v.status is VS.PENDING)
        print("Cycle detected, resolving...")
        for v in resolved_visits:
            print(f"    {v}")
        return successfully_resolved

    def print_players(self, game: m.Game) -> None:
        for player in game.players:
            print(f"{player}: {player.role_name}")
            print(f"  Actions: {player.actions}")
            print(f"  Passives: {player.passives}")
            print(f"  Shared Actions: {player.shared_actions}")
            print()


def test_catastrophic_rule() -> None:
    r = PrintResolver()

    cop = examples.Cop()
    jailkeeper = examples.Jailkeeper()
    roleblocker = examples.Roleblocker()
    town = examples.Town()
    mafia = examples.Mafia()

    game = m.Game(start_phase=m.Phase.NIGHT)
    alice = m.Player("Alice", cop, town)
    bob = m.Player("Bob", jailkeeper, town)
    eve = m.Player("Eve", roleblocker, mafia)

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

    vanilla = examples.Vanilla()
    xshot = examples.XShot(1)
    xshot_cop = xshot(examples.Cop)()
    xshot_bulletproof = xshot(examples.Bulletproof)()
    town = examples.Town()
    mafia = examples.Mafia()

    game = m.Game()
    alice = m.Player("Alice", xshot_cop, town)
    bob = m.Player("Bob", xshot_bulletproof, town)
    eve = m.Player("Eve", vanilla, mafia)

    game.add_player(alice, bob, eve)

    for player in game.players:
        print(f"{player}: {player.role_name}")
        print(f"  Actions: {player.actions}")
        print(f"  Passives: {player.passives}")
        print(f"  Shared Actions: {player.shared_actions}")
        print()

    game.phase, game.day_no = m.Phase.NIGHT, 1
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

    game.phase, game.day_no = m.Phase.NIGHT, 2
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

    town = examples.Town()
    mafia = examples.Mafia()

    game = m.Game(start_phase=m.Phase.NIGHT)
    alice = m.Player("Alice", examples.Doctor(), town)
    bob = m.Player("Bob", examples.Vanilla(), town)
    eve = m.Player("Eve", examples.Vanilla(), mafia)

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

    town = examples.Town()
    mafia = examples.Mafia()

    game = m.Game(start_phase=m.Phase.NIGHT)
    alice = m.Player("Alice", examples.Doctor(), town)
    bob = m.Player("Bob", examples.XShot(1)(examples.Macho)(), town)
    carol = m.Player("Carol", examples.XShot(1)(examples.Macho)(), town)
    eve = m.Player("Eve", examples.Vanilla(), mafia)

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

    town = examples.Town()
    mafia = examples.Mafia()

    game = m.Game(start_phase=m.Phase.NIGHT)
    alice = m.Player("Alice", examples.Roleblocker(), town)
    bob = m.Player("Bob", examples.Tracker(), town)
    eve = m.Player("Eve", examples.Vanilla(), mafia)

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

    town = examples.Town()
    mafia = examples.Mafia()

    game = m.Game(start_phase=m.Phase.NIGHT)
    alice = m.Player("Alice", examples.Roleblocker(), town)
    bob = m.Player("Bob", examples.Vanilla(), town)
    eve = m.Player("Eve", examples.Juggernaut(), mafia)

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
    town = examples.Town()
    mafia = examples.Mafia()
    game = m.Game(start_phase=m.Phase.NIGHT)

    alice = m.Player("Alice", examples.Roleblocker(), town)
    bob = m.Player("Bob", examples.Cop(), town)
    eve = m.Player("Eve", examples.Vanilla(), mafia)

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
    town = examples.Town()
    mafia = examples.Mafia()
    game = m.Game(start_phase=m.Phase.NIGHT)

    alice = m.Player("Alice", examples.Ascetic(), town)
    bob = m.Player("Bob", examples.Doctor(), town)
    eve = m.Player("Eve", examples.Vanilla(), mafia)

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
    town = examples.Town()
    mafia = examples.Mafia()
    game = m.Game(start_phase=m.Phase.NIGHT)

    alice = m.Player("Alice", examples.Detective(), town)
    bob = m.Player("Bob", examples.Vanilla(), town)
    eve = m.Player("Eve", examples.Vanilla(), mafia)

    game.add_player(alice, bob, eve)

    r.print_players(game)
    r.add_passives(game)
    game.visits.append(r.make_visit(game, eve, (bob,), AT.SHARED_ACTION, 0, {"factional"}))
    r.resolve_game(game)
    print()

    game.phase, game.day_no = m.Phase.NIGHT, 2
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
    town = examples.Town()
    mafia = examples.Mafia()
    game = m.Game(start_phase=m.Phase.NIGHT)

    joat = examples.Jack_of_All_Trades(
        examples.Cop,
        examples.Doctor,
    )

    alice = m.Player("Alice", joat(), town)
    bob = m.Player("Bob", examples.Vanilla(), town)
    eve = m.Player("Eve", examples.Vanilla(), mafia)

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
    town = examples.Town()
    mafia = examples.Mafia()
    game = m.Game(start_phase=m.Phase.NIGHT)

    alice = m.Player("Alice", examples.Hider(), town)
    bob = m.Player("Bob", examples.Vanilla(), town)
    carol = m.Player("Carol", examples.Vigilante(), town)
    eve = m.Player("Eve", examples.Vanilla(), mafia)

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
    town = examples.Town()
    mafia = examples.Mafia()
    game = m.Game(start_phase=m.Phase.NIGHT)

    alice = m.Player("Alice", examples.Traffic_Analyst(), town)
    bob = m.Player("Bob", examples.Mason(), town)
    carol = m.Player("Carol", examples.Mason(), town)
    dave = m.Player("Dave", examples.Messenger(), town)
    eve = m.Player("Eve", examples.Vanilla(), mafia)

    game.add_player(alice, bob, carol, dave, eve)

    r.print_players(game)
    r.add_passives(game)
    game.visits.append(r.make_visit(game, alice, (bob,), AT.ACTION, 0))
    r.resolve_game(game)

    game.phase, game.day_no = m.Phase.NIGHT, 2
    game.visits.append(r.make_visit(game, alice, (dave,), AT.ACTION, 0))
    r.resolve_game(game)

    game.phase, game.day_no = m.Phase.NIGHT, 3
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
    town = examples.Town()
    mafia = examples.Mafia()
    game = m.Game(start_phase=m.Phase.NIGHT)

    alice = m.Player("Alice", examples.Universal_Backup(), town)
    bob = m.Player("Bob", examples.Vigilante(), town)
    carol = m.Player("Carol", examples.Cop(), town)
    dave = m.Player("Dave", examples.Doctor(), mafia)
    eve = m.Player("Eve", examples.Vanilla(), mafia)

    game.add_player(alice, bob, carol, dave, eve)

    r.print_players(game)
    r.add_passives(game)
    game.visits.append(r.make_visit(game, bob, (carol,), AT.ACTION, 0))
    game.visits.append(r.make_visit(game, eve, (dave,), AT.SHARED_ACTION, 0, {"factional"}))
    r.resolve_game(game)
    game.phase, game.day_no = m.Phase.DAY, 2
    r.add_passives(game)
    print()
    pprint(game)
    assert not carol.is_alive, "Carol is alive, expected Vigilante to kill."
    assert not dave.is_alive, "Dave is alive, expected Mafia to kill."
    assert alice.actions[0].id == "Cop", "Alice erroneously did not gain Cop."
    assert alice.actions[0].id != "Doctor", "Alice erroneously gained Doctor."


def test_activated() -> None:
    r = PrintResolver()
    town = examples.Town()
    mafia = examples.Mafia()
    game = m.Game(start_phase=m.Phase.NIGHT)
    activated = examples.Activated()

    alice = m.Player("Alice", activated(examples.Bulletproof)(), town)
    bob = m.Player("Bob", activated(examples.Bulletproof)(), town)
    eve = m.Player("Eve", examples.Vanilla(), mafia)

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
    town = examples.Town()
    mafia = examples.Mafia()
    game = m.Game(start_phase=m.Phase.NIGHT)

    alice = m.Player("Alice", examples.Watcher(), town)
    bob = m.Player("Bob", examples.Vanilla(), town)
    eve = m.Player("Eve", examples.Ninja(), mafia)

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
    town = examples.Town()
    mafia = examples.Mafia()
    game = m.Game(start_phase=m.Phase.NIGHT)
    personal = examples.Personal()

    alice = m.Player("Alice", personal(examples.Watcher)(), town)
    bob = m.Player("Bob", examples.Vanilla(), town)
    eve = m.Player("Eve", examples.Vanilla(), mafia)

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
    town = examples.Town()
    mafia = examples.Mafia()
    game = m.Game(start_phase=m.Phase.NIGHT)
    combined = m.Role.combine(examples.Bulletproof, examples.Cop)

    alice = m.Player("Alice", combined(), town)
    eve = m.Player("Eve", examples.Vanilla(), mafia)

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
    from api_v1 import api, games
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(api)
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
        assert response.json["phase"] == m.Phase.NIGHT.value, "Expected phase to be NIGHT"

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

# DO TESTS #

TESTS: dict[str, Callable[[], None]] = {
    "test_catastrophic_rule": test_catastrophic_rule,
    "test_xshot_role": test_xshot_role,
    "test_protection": test_protection,
    "test_xshot_macho": test_xshot_macho,
    "test_tracker_roleblocker": test_tracker_roleblocker,
    "test_juggernaut": test_juggernaut,
    "test_investigative_fail": test_investigative_fail,
    "test_ascetic": test_ascetic,
    "test_detective": test_detective,
    "test_jack_of_all_trades": test_jack_of_all_trades,
    "test_hider": test_hider,
    "test_traffic_analyst": test_traffic_analyst,
    "test_universal_backup": test_universal_backup,
    "test_activated": test_activated,
    "test_ninja": test_ninja,
    "test_personal": test_personal,
    "test_combine": test_combine,
    "test_api_v1": test_api_v1
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

    successes: int = 0
    failed_tests: list[str] = []
    DIR = Path(__file__).parent
    makedirs(DIR / "test_results", exist_ok=True)
    for test_name, test_func in TESTS.items():
        if verbose:
            print(f"## TESTING: {test_name}() ##")
        try:
            with open(DIR / "test_results" / f"{test_name}.log", "w") as f:
                with redirect_stdout(f):
                    test_func()
        except Exception as e:
            if verbose:
                with open(DIR / "test_results" / f"{test_name}.log", "r") as f:
                    print(f.read())
                print_exception(e)
            with open(DIR / "test_results" / f"{test_name}.log", "a") as f:
                print_exception(e, file=f)
            print(f"## TEST {test_name} FAILED ##")
            failed_tests.append(test_name)
        else:
            if verbose:
                with open(DIR / "test_results" / f"{test_name}.log", "r") as f:
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
