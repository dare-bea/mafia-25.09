from typing import Callable
import mafia as m
import examples
from pprint import pprint


class PrintResolver(examples.Resolver):
    def resolve_visit(self, game: m.Game, visit: m.Visit) -> int:
        resolved_visits = set(
            v for v in game.visits if v.status is m.VisitStatus.PENDING
        ) - {visit}

        result = super().resolve_visit(game, visit)

        print(visit)
        resolved_visits -= set(v for v in game.visits if v.status is m.VisitStatus.PENDING)
        for v in resolved_visits:
            print(f"    {v}")
        return result

    def resolve_cycles(self, game: m.Game) -> bool:
        resolved_visits = set(v for v in game.visits if v.status is m.VisitStatus.PENDING)
        successfully_resolved = super().resolve_cycles(game)
        resolved_visits -= set(v for v in game.visits if v.status is m.VisitStatus.PENDING)
        print("Cycle detected, resolving...")
        for v in resolved_visits:
            print(f"    {v}")
        return successfully_resolved


def test_catastrophic_rule() -> None:
    r = PrintResolver()

    cop = examples.Cop()
    jailkeeper = examples.Jailkeeper()
    roleblocker = examples.Roleblocker()
    town = examples.Town()
    mafia = examples.Mafia()

    game = m.Game(1, m.Phase.NIGHT)
    alice = m.Player("Alice", cop, town, game=game)
    bob = m.Player("Bob", jailkeeper, town, game=game)
    eve = m.Player("Eve", roleblocker, mafia, game=game)

    for player in game.players:
        print(f"{player}: {player.role_name}")
        print(f"  Actions: {player.actions}")
        print(f"  Passives: {player.passives}")
        print(f"  Shared Actions: {player.shared_actions}")
        print()

    r.add_passives(game)

    game.visits.append(r.make_visit(game, eve, (alice,), m.AbilityType.SHARED_ACTION, 0))
    game.visits.append(r.make_visit(game, bob, (eve,), m.AbilityType.ACTION, 0))
    game.visits.append(r.make_visit(game, eve, (bob,), m.AbilityType.ACTION, 0))
    game.visits.append(r.make_visit(game, eve, (alice,), m.AbilityType.ACTION, 0))
    game.visits.append(r.make_visit(game, alice, (eve,), m.AbilityType.ACTION, 0))

    r.resolve_game(game)
    print()

    pprint(game)

    assert game.visits[4].status != m.VisitStatus.FAILURE and all(
        v.status == m.VisitStatus.FAILURE for v in game.visits[:4]
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
    alice = m.Player("Alice", xshot_cop, town, game=game)
    bob = m.Player("Bob", xshot_bulletproof, town, game=game)
    eve = m.Player("Eve", vanilla, mafia, game=game)

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
        game.visits.append(r.make_visit(game, alice, (bob,), m.AbilityType.ACTION, 0))
    else:
        print(f"{alice.name} cannot use {alice.actions[0].id} on {bob.name}.")
        raise AssertionError("Expected check to succeed.")
    game.visits.append(r.make_visit(game, eve, (bob,), m.AbilityType.SHARED_ACTION, 0))
    r.resolve_game(game)
    assert bob.is_alive, "Bob is dead, expected Bulletproof to protect."
    print()

    game.phase, game.day_no = m.Phase.NIGHT, 2
    if alice.actions[0].check(game, alice, (eve,)):
        print(f"{alice.name} is using {alice.actions[0].id} on {eve.name}.")
        game.visits.append(r.make_visit(game, alice, (eve,), m.AbilityType.ACTION, 0))
        raise AssertionError("Expected check to fail.")
    else:
        print(f"{alice.name} cannot use {alice.actions[0].id} on {eve.name}.")
    game.visits.append(r.make_visit(game, eve, (bob,), m.AbilityType.SHARED_ACTION, 0))
    r.resolve_game(game)
    print()
    pprint(game)

    assert not bob.is_alive, "Bob is alive, expected 1-Shot Bulletproof to be used."


def test_protection() -> None:
    r = PrintResolver()

    town = examples.Town()
    mafia = examples.Mafia()

    game = m.Game(1, m.Phase.NIGHT)
    alice = m.Player("Alice", examples.Doctor(), town, game=game)
    bob = m.Player("Bob", examples.Vanilla(), town, game=game)
    eve = m.Player("Eve", examples.Vanilla(), mafia, game=game)

    for player in game.players:
        print(f"{player}: {player.role_name}")
        print(f"  Actions: {player.actions}")
        print(f"  Passives: {player.passives}")
        print(f"  Shared Actions: {player.shared_actions}")
        print()

    r.add_passives(game)
    game.visits.append(r.make_visit(game, alice, (bob,), m.AbilityType.ACTION, 0))
    game.visits.append(r.make_visit(game, eve, (bob,), m.AbilityType.SHARED_ACTION, 0))

    r.resolve_game(game)
    print()
    pprint(game)

    assert bob.is_alive, "Bob is dead."


def test_xshot_macho() -> None:
    r = PrintResolver()

    town = examples.Town()
    mafia = examples.Mafia()

    game = m.Game(1, m.Phase.NIGHT)
    alice = m.Player("Alice", examples.Doctor(), town, game=game)
    bob = m.Player("Bob", examples.XShot(1)(examples.Macho)(), town, game=game)
    carol = m.Player("Carol", examples.XShot(1)(examples.Macho)(), town, game=game)
    eve = m.Player("Eve", examples.Vanilla(), mafia, game=game)

    for player in game.players:
        print(f"{player}: {player.role_name}")
        print(f"  Actions: {player.actions}")
        print(f"  Passives: {player.passives}")
        print(f"  Shared Actions: {player.shared_actions}")
        print()

    r.add_passives(game)
    game.visits.append(r.make_visit(game, alice, (bob,), m.AbilityType.ACTION, 0))
    game.visits.append(r.make_visit(game, alice, (carol,), m.AbilityType.ACTION, 0))
    game.visits.append(r.make_visit(game, alice, (carol,), m.AbilityType.ACTION, 0))
    game.visits.append(r.make_visit(game, eve, (bob,), m.AbilityType.SHARED_ACTION, 0))
    game.visits.append(r.make_visit(game, eve, (carol,), m.AbilityType.SHARED_ACTION, 0))

    r.resolve_game(game)
    print()
    pprint(game)

    assert not bob.is_alive, "Bob is alive."
    assert carol.is_alive, "Carol is dead."


def test_tracker_roleblocker() -> None:
    r = PrintResolver()

    town = examples.Town()
    mafia = examples.Mafia()

    game = m.Game(1, m.Phase.NIGHT)
    alice = m.Player("Alice", examples.Roleblocker(), town, game=game)
    bob = m.Player("Bob", examples.Tracker(), town, game=game)
    eve = m.Player("Eve", examples.Vanilla(), mafia, game=game)

    for player in game.players:
        print(f"{player}: {player.role_name}")
        print(f"  Actions: {player.actions}")
        print(f"  Passives: {player.passives}")
        print(f"  Shared Actions: {player.shared_actions}")
        print()

    r.add_passives(game)
    game.visits.append(r.make_visit(game, alice, (eve,), m.AbilityType.ACTION, 0))
    game.visits.append(r.make_visit(game, bob, (eve,), m.AbilityType.ACTION, 0))
    game.visits.append(r.make_visit(game, eve, (bob,), m.AbilityType.SHARED_ACTION, 0))

    r.resolve_game(game)
    print()
    pprint(game)

    print(bob.private_messages)
    assert bob.private_messages[0].content == "Eve did not target anyone."


def test_juggernaut() -> None:
    r = PrintResolver()

    town = examples.Town()
    mafia = examples.Mafia()

    game = m.Game(1, m.Phase.NIGHT)
    alice = m.Player("Alice", examples.Roleblocker(), town, game=game)
    bob = m.Player("Bob", examples.Vanilla(), town, game=game)
    eve = m.Player("Eve", examples.Juggernaut(), mafia, game=game)

    for player in game.players:
        print(f"{player}: {player.role_name}")
        print(f"  Actions: {player.actions}")
        print(f"  Passives: {player.passives}")
        print(f"  Shared Actions: {player.shared_actions}")
        print()

    r.add_passives(game)
    game.visits.append(r.make_visit(game, alice, (eve,), m.AbilityType.ACTION, 0))
    game.visits.append(r.make_visit(game, eve, (eve,), m.AbilityType.ACTION, 0))
    game.visits.append(r.make_visit(game, eve, (bob,), m.AbilityType.SHARED_ACTION, 0))

    r.resolve_game(game)
    print()
    pprint(game)

    assert not bob.is_alive, "Factional Kill was roleblocked, expected Juggernaut to force kill."


# DO TESTS #

TESTS: dict[str, Callable[[], None]] = {
    "test_catastrophic_rule": test_catastrophic_rule,
    "test_xshot_role": test_xshot_role,
    "test_protection": test_protection,
    "test_xshot_macho": test_xshot_macho,
    "test_tracker_roleblocker": test_tracker_roleblocker,
    "test_juggernaut": test_juggernaut,
}


def main() -> None:
    from os import makedirs
    from sys import stderr, argv
    from contextlib import redirect_stdout
    from pathlib import Path
    from traceback import print_exception

    successes: int = 0
    DIR = Path(__file__).parent
    makedirs(DIR / "test_results", exist_ok=True)
    for test_name, test_func in TESTS.items():
        print(f"## TESTING: {test_name}() ##")
        try:
            with open(DIR / "test_results" / f"{test_name}.log", "w") as f:
                with redirect_stdout(f):
                    test_func()
        except Exception as e:
            with open(DIR / "test_results" / f"{test_name}.log", "r") as f:
                print(f.read())
            with open(DIR / "test_results" / f"{test_name}.log", "a") as f:
                print_exception(e, file=f)
            print_exception(e)
            print(f"## TEST {test_name} FAILED ##")
        else:
            with open(DIR / "test_results" / f"{test_name}.log", "r") as f:
                print(f.read())
            print(f"## TEST {test_name} PASSED ##")
            successes += 1
        print()

    print(f"{successes}/{len(TESTS)} tests succeeded! ({successes / len(TESTS):.1%})")
    print()

    if "--no-mypy" in argv or "-M" in argv:
        return

    try:
        import mypy.api
    except ImportError:
        print("Could not find module 'mypy.api'. Skipping type-checking...")
    else:
        for x in range(10, 14):
            print(f"Type-checking Python 3.{x}:")
            result = mypy.api.run(["--python-version", f"3.{x}", "--strict", "--pretty", str(DIR)])
            if result[0]:
                print(result[0].rstrip())

            if result[1]:
                print(result[1].rstrip(), file=stderr)


if __name__ == "__main__":
    main()
