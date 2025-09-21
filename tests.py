import mafia as m
import examples
from pprint import pprint

class PrintResolver(examples.Resolver):
    def resolve_visit(self, game: m.Game, visit: m.Visit) -> int:
        resolved_visits = set(v for v in game.visits if v.status is m.VisitStatus.PENDING) - {visit}
        
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

def test_catastrophic_rule():
    r = PrintResolver()
    
    cop = examples.Cop()
    jailkeeper = examples.Jailkeeper()
    roleblocker = examples.Roleblocker()
    town = examples.Town()
    mafia = examples.Mafia()
    
    game = m.Game()
    alice = m.Player('Alice', cop, town, game=game)
    bob = m.Player('Bob', jailkeeper, town, game=game)
    eve = m.Player('Eve', roleblocker, mafia, game=game)
    
    for player in game.players:
        print(f'{player}: {player.role_name}')
        print(f'  Actions: {player.actions}')
        print(f'  Passives: {player.passives}')
        print(f'  Shared Actions: {player.shared_actions}')
        print()
    
    game.phase = m.Phase.NIGHT
    for player in game.players:
        for ability in player.passives:
            if ability.check(game, player):
                visit = m.Visit(actor=player, ability=ability, ability_type=m.AbilityType.PASSIVE)
                if ability.immediate:
                    r.resolve_visit(game, visit)
                else:
                    game.visits.append(visit)
    
    game.visits.append(m.Visit(actor=eve, targets=(alice,),
                               ability=eve.shared_actions[0],
                               ability_type=m.AbilityType.SHARED_ACTION))
    game.visits.append(m.Visit(actor=bob, targets=(eve,),
                               ability=bob.actions[0],
                               ability_type=m.AbilityType.ACTION))
    game.visits.append(m.Visit(actor=eve, targets=(bob,),
                               ability=eve.actions[0],
                               ability_type=m.AbilityType.ACTION))
    game.visits.append(m.Visit(actor=eve, targets=(alice,),
                               ability=eve.actions[0],
                               ability_type=m.AbilityType.ACTION))
    game.visits.append(m.Visit(actor=alice, targets=(eve,),
                               ability=alice.actions[0],
                               ability_type=m.AbilityType.ACTION))
    
    r.resolve_game(game)
    print()
    
    pprint(game)

    assert game.visits[4].status != m.VisitStatus.FAILURE and all(
        v.status == m.VisitStatus.FAILURE for v in game.visits[:4]
    )

def test_xshot_role():
    r = PrintResolver()

    vanilla = examples.Vanilla()
    xshot = examples.XShot(1)
    xshot_cop = xshot(examples.Cop)()
    xshot_bulletproof = xshot(examples.Bulletproof)()
    town = examples.Town()
    mafia = examples.Mafia()

    game = m.Game()
    alice = m.Player('Alice', xshot_cop, town, game=game)
    bob = m.Player('Bob', xshot_bulletproof, town, game=game)
    eve = m.Player('Eve', vanilla, mafia, game=game)

    for player in game.players:
        print(f'{player}: {player.role_name}')
        print(f'  Actions: {player.actions}')
        print(f'  Passives: {player.passives}')
        print(f'  Shared Actions: {player.shared_actions}')
        print()

    game.phase, game.day_no = m.Phase.NIGHT, 1
    for player in game.players:
        for ability in player.passives:
            if ability.check(game, player):
                visit = m.Visit(actor=player, ability=ability, ability_type=m.AbilityType.PASSIVE)
                if ability.immediate:
                    r.resolve_visit(game, visit)
                else:
                    game.visits.append(visit)

    if alice.actions[0].check(game, alice, (bob,)):
        print(f"{alice.name} is using {alice.actions[0].id} on {bob.name}.")
        game.visits.append(m.Visit(actor=alice, targets=(bob,),
                                   ability=alice.actions[0],
                                   ability_type=m.AbilityType.ACTION))
    else:
        print(f"{alice.name} cannot use {alice.actions[0].id} on {bob.name}.")
        raise AssertionError("Expected check to succeed.")
    game.visits.append(m.Visit(actor=eve, targets=(bob,),
                               ability=eve.shared_actions[0],
                               ability_type=m.AbilityType.SHARED_ACTION))
    r.resolve_game(game)
    assert bob.is_alive, "Bob is dead, expected Bulletproof to protect."
    print()

    game.phase, game.day_no = m.Phase.NIGHT, 2
    if alice.actions[0].check(game, alice, (eve,)):
        print(f"{alice.name} is using {alice.actions[0].id} on {eve.name}.")
        game.visits.append(m.Visit(actor=alice, targets=(eve,),
                                   ability=alice.actions[0],
                                   ability_type=m.AbilityType.ACTION))
        raise AssertionError("Expected check to fail.")
    else:
        print(f"{alice.name} cannot use {alice.actions[0].id} on {eve.name}.")
    game.visits.append(m.Visit(actor=eve, targets=(bob,),
                               ability=eve.shared_actions[0],
                               ability_type=m.AbilityType.SHARED_ACTION))
    r.resolve_game(game)
    assert not bob.is_alive, "Bob is alive, expected 1-Shot Bulletproof to make Bulletproof fail."
    print()

    pprint(game)

def test_protection():
    r = PrintResolver()

    town = examples.Town()
    mafia = examples.Mafia()

    game = m.Game()
    alice = m.Player('Alice', examples.Doctor(), town, game=game)
    bob = m.Player('Bob', examples.Vanilla(), town, game=game)
    eve = m.Player('Eve', examples.Vanilla(), mafia, game=game)

    for player in game.players:
        print(f'{player}: {player.role_name}')
        print(f'  Actions: {player.actions}')
        print(f'  Passives: {player.passives}')
        print(f'  Shared Actions: {player.shared_actions}')
        print()

    game.visits.append(m.Visit(alice, (bob,),
                               ability=alice.actions[0],
                               ability_type=m.AbilityType.ACTION))
    game.visits.append(m.Visit(eve, (bob,),
                               ability=eve.shared_actions[0],
                               ability_type=m.AbilityType.SHARED_ACTION))

    r.resolve_game(game)
    assert bob.is_alive, "Bob is dead."

TESTS = [
    test_catastrophic_rule,
    test_xshot_role,
    test_protection
]

def main():
    from os import makedirs
    from contextlib import redirect_stdout, redirect_stderr
    from pathlib import Path
    from traceback import print_exception
    
    DIR = Path(__file__).parent
    makedirs(DIR / 'test_results', exist_ok=True)
    for test in TESTS:
        test_name = test.__name__
        print(f'## TESTING: {test_name}() ##')
        try: 
            with open(DIR / 'test_results' / f'{test_name}.log', 'w') as f:
                with redirect_stdout(f):
                    test()
        except Exception as e:
            with open(DIR / 'test_results' / f'{test_name}.log', 'r') as f:
                print(f.read())
            with open(DIR / 'test_results' / f'{test_name}.log', 'a') as f:
                print_exception(e, file=f)
            print_exception(e)
            print(f'## TEST {test_name} FAILED ##')
        else:
            with open(DIR / 'test_results' / f'{test_name}.log', 'r') as f:
                print(f.read())
            print(f'## TEST {test_name} PASSED ##')
        print()

if __name__ == '__main__':
    main()
