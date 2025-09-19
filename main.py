import mafia as m
import examples
from pprint import pprint

class PrintResolver(examples.Resolver):
    def resolve_visit(self, game: m.Game, visit: m.Visit) -> m.VisitStatus:
        resolved_visits = set(v for v in game.visits if v.status is m.VisitStatus.PENDING) - {visit}
        
        result = super().resolve_visit(game, visit)

        print(visit)
        resolved_visits -= set(v for v in game.visits if v.status is m.VisitStatus.PENDING)
        for v in resolved_visits:
            print(f"  ( {v} )")
        return result

r = PrintResolver()

vanilla = examples.Vanilla()
cop = examples.Cop()
bulletproof = examples.Bulletproof()
town = examples.Town()
mafia = examples.Mafia()

game = m.Game()
m.Player('Alice', vanilla, town, game=game)
m.Player('Bob', vanilla, town, game=game)
m.Player('Charlie', cop, town, game=game)
m.Player('David', bulletproof, town, game=game)
m.Player('Eve', vanilla, mafia, game=game)

for player in game.players:
    print(f'{player}: {examples.full_role_name(player.role, player.alignment)}')
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

game.visits.append(m.Visit(actor=game.players[2], targets=(game.players[4],), ability=game.players[2].actions[0], ability_type=m.AbilityType.ACTION))
game.visits.append(m.Visit(actor=game.players[4], targets=(game.players[3],), ability=game.players[4].shared_actions[0], ability_type=m.AbilityType.SHARED_ACTION))

r.resolve_game(game)
print()

pprint(game)