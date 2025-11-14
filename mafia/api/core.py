"""
Shared API code. Includes the 'database' (if you can call it that) and
authorization functions. Also includes a derived Game class that adds extra
fields for API use.
"""

from werkzeug.datastructures import Headers
from secrets import token_urlsafe
from typing import Any
from itertools import count

from mafia.core import Game as BaseGame
from mafia.core import Player, Chat, Visit
from mafia.normal import Resolver

class Game(BaseGame):
    def __init__(self, *args: Any, mod_token: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if mod_token is None:
            mod_token = token_urlsafe(16)
        self.mod_token = mod_token
        self.chats["global"] = Chat()
        self.queued_visits: list[Visit] = []

    def advance_phase(self) -> tuple[int, Any]:
        result = super().advance_phase()
        self.queued_visits.clear()
        return result

resolver = Resolver()

def get_permissions(game: Game, headers: Headers) -> tuple[str | None, Player | None]:
    mod_token: str | None = headers.get("Authorization-Mod-Token")
    player_name: str | None = headers.get("Authorization-Player-Name")
    player: Player | None = next((p for p in game.players if p.name == player_name), None)
    return mod_token, player

games: dict[int, Game] = {}
game_count = count(0)