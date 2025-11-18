"""Shared API code.

Includes a 'database' of sorts and authorization functions.
Also includes a derived Game class that adds extra fields for API use.
"""

from itertools import count
from secrets import token_urlsafe
from typing import Any

from werkzeug.datastructures import Headers

from mafia.core import Player, Visit
from mafia.normal import Game as BaseGame
from mafia.normal import Resolver


class Game(BaseGame):
    """A game of Mafia with extra fields for API use."""

    def __init__(self, *args: Any, mod_token: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if mod_token is None:
            mod_token = token_urlsafe(16)
        self.mod_token = mod_token
        self.queued_visits: list[Visit] = []

    def advance_phase(self) -> tuple[int, Any]:
        result = super().advance_phase()
        self.queued_visits.clear()
        return result


resolver = Resolver()


def get_permissions(game: Game, headers: Headers) -> tuple[str | None, Player | None]:
    """Get the moderator token and player from the headers."""
    mod_token: str | None = headers.get("Authorization-Mod-Token")
    player_name: str | None = headers.get("Authorization-Player-Name")
    player: Player | None = next((p for p in game.players if p.name == player_name), None)
    return mod_token, player


games: dict[int, Game] = {}
game_count = count(0)
