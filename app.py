import re
from typing import Any, Callable, ParamSpec
from itertools import count
import random

from flask import Flask, redirect, render_template, url_for, abort, render_template_string, request
import markdown as md
import nh3
from markupsafe import Markup

import mafia as m
import examples as ex

def slugify(obj: Any) -> str:
    return re.sub(r"\s", "-", str(obj))

def role(player: m.Player) -> Markup:
    return Markup(render_template_string(
        "<span class=\"role_name Alignment-{{ player.alignment |e|s }}\">"
        "{{ player.role_name |e}}</span>",
        player=player
    ))

P = ParamSpec("P")
def safe_function(func: Callable[P, Any]) -> Callable[P, Markup]:
    def inner(*args: P.args, **kwargs: P.kwargs) -> Markup:
        return Markup(func(*args, **kwargs))
    return inner

clean = safe_function(nh3.clean)

app = Flask(__name__)

app.jinja_env.filters.update(dict(
    s = slugify,
    slugify = slugify,
    md = md.markdown,
    markdown = md.markdown,
    role = role,
    clean = clean,
))

# API ENDPOINTS #
# TODO: Design API endpoints.

# WEBSITE ENDPOINTS #

@app.route('/')
def index() -> ...:
    return render_template('index.html')

def create_sample_game() -> int:
    town = ex.Town()
    mafia = ex.Mafia()

    id = len(games)
    game = m.Game(id, m.Phase.NIGHT)
    games[next(next_game_id)] = game
    game.add_player(m.Player("Alice", ex.Gunsmith(), town))
    game.add_player(m.Player("Bob", ex.Doctor(), town))
    game.add_player(m.Player("Carol", ex.Vigilante(), town))
    game.add_player(m.Player("Dave", ex.Mason(), town))
    game.add_player(m.Player("Eve", ex.Mason(), town))
    game.add_player(m.Player("Frank", ex.Vanilla(), town))
    game.add_player(m.Player("Grace", ex.Vanilla(), mafia))
    game.add_player(m.Player("Heidi", ex.Roleblocker(), mafia))
    return id

@app.route('/new')
def new() -> ...:
    id = create_sample_game()
    return redirect(url_for('mod_page', id=id))

@app.route('/game/<int:id>/player/<string:name>')
def player_page(id: int, name: str) -> ...:
    if id >= len(games):
        abort(404)

    player = next((p for p in games[id].players if p.name == name), None)
    if player is None:
        abort(404)
    return render_template('game.player.html', player=player, game=games[id], id=id)


@app.route('/game/<int:id>/mod')
def mod_page(id: int) -> ...:
    if id >= len(games):
        abort(404)

    return render_template('game.html', game=games[id], id=id, mod=True)
    

@app.route('/game/<int:id>/mod/player/<string:name>')
def mod_player_page(id: int, name: str) -> ...:
    if id >= len(games):
        abort(404)

    player = next((p for p in games[id].players if p.name == name), None)
    if player is None:
        abort(404)
    return render_template('game.player.html', player=player, game=games[id], id=id, mod=True)

games: dict[int, m.Game] = {}
next_game_id = count(0)

create_sample_game()