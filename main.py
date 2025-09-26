from functools import partial
from itertools import product, repeat
from random import choice, shuffle
import tkinter as tk
from tkinter import ttk

import mafia as m
import examples as ex
from tests import PrintResolver

NOT_SELECTED = -1

def select_action(player: m.Player) -> None:
    idx = player_vars[player][0].get()
    action = player.actions[idx] if idx < len(player.actions) else player.shared_actions[idx - len(player.actions)]
    print(f"Selected action {action} for {player.name}")
    for col, radios in enumerate(player_target_radios[player]):
        for target, radio in radios.items():
            radio.configure(state=tk.DISABLED, text="D")
            for ts in product(game.players, repeat=action.target_count):
                if ts[col] is not target:
                    continue
                if action.check(game, player, ts):
                    radio.configure(state=tk.NORMAL, text="E")
    if (all(player_vars[player][1][idx].get() != NOT_SELECTED for idx in range(action.target_count))
        and action.check(
            game, player,
            tuple(game.players[player_vars[player][1][idx].get()] for idx in range(action.target_count)))):
        player_submit_buttons[player].config(state=tk.NORMAL)
    else:
        player_submit_buttons[player].config(state=tk.DISABLED)

def select_target(player: m.Player, col: int) -> None:
    idx = player_vars[player][0].get()
    action = player.actions[idx] if idx < len(player.actions) else player.shared_actions[idx - len(player.actions)]
    target = game.players[player_vars[player][1][col].get()]
    print(f"Selected target {target} for {player.name} on {action}")
    for c, radios in enumerate(player_target_radios[player]):
        for p, radio in radios.items():
            radio.configure(state=tk.DISABLED, text="D")
            if c >= action.target_count:
                continue
            for ts in product(game.players, repeat=action.target_count):
                if ts[c] is not p:
                    continue
                if any(
                    c != n and ts[n] is not game.players[player_vars[player][1][n].get()]
                    for n in range(len(player_target_radios[player]))
                    if player_vars[player][1][n].get() != NOT_SELECTED
                ):
                    continue
                if action.check(game, player, ts):
                    radio.configure(state=tk.NORMAL, text="E")
                    break
    if (all(player_vars[player][1][idx].get() != NOT_SELECTED for idx in range(action.target_count))
        and action.check(
            game, player,
            tuple(game.players[player_vars[player][1][idx].get()] for idx in range(action.target_count)))):
        player_submit_buttons[player].config(state=tk.NORMAL)
    else:
        player_submit_buttons[player].config(state=tk.DISABLED)

def submit_action(player: m.Player) -> None:
    action_idx = player_vars[player][0].get()
    action, action_type = (player.actions[action_idx], m.AbilityType.ACTION) if action_idx < len(player.actions) else (player.shared_actions[action_idx - len(player.actions)], m.AbilityType.SHARED_ACTION)
    targets = tuple(game.players[player_vars[player][1][idx].get()] for idx in range(action.target_count))
    if not action.check(game, player, targets):
        print(f"Action {action} for {player.name} with targets {targets} is invalid")
        return 
    perform_action(player, action, targets, action_type)
    print(f"Submitted action {action} for {player.name} with targets {targets}")
    if action_type is m.AbilityType.ACTION:
        return
    # Update other players' used by if shared action
    for p in game.players:
        if action in player_used_by_labels[p]:
            player_used_by_labels[p][action].config(text=player.name)

def clear_selection(player: m.Player) -> None:
    for radio in player_action_radios[player]:
        radio.config(state=tk.NORMAL)
    for radios in player_target_radios[player]:
        for radio in radios.values():
            radio.config(state=tk.DISABLED, text="D")
    player_submit_buttons[player].config(state=tk.DISABLED)
    for idx in player_vars[player][1]:
        idx.set(NOT_SELECTED)
    player_vars[player][0].set(NOT_SELECTED)
    print(f"Cleared selection for {player.name}")

def submit_chat(player: m.Player) -> None:
    message = player_chat_messages[player].get()
    if not message:
        return
    game.chats["global"].send(player, message)
    player_chat_messages[player].set("")
    print(f"Submitted chat message {message} for {player.name}")
    for p in game.players:
        

game = m.Game()
r = PrintResolver()

town = ex.Town()
mafia = ex.Mafia()

# Uses NewD3 setup
# - A1: Mafia Goon, Mafia Roleblocker vs. Town Cop, Town Doctor, 5x Town Vanilla
# - A2: Mafia Goon, Mafia Roleblocker vs. Town Jailkeeper, Town Tracker, 5x Town Vanilla
# - A3: Mafia Goon, Mafia Roleblocker vs. Town Mason, Town Mason, 5x Town Vanilla
# - B1: Mafia Goon, Mafia Rolecop vs. Town Tracker, Town Friendly Neighbor, 5x Town Vanilla
# - B2: Mafia Goon, Mafia Rolecop vs. Town Jailkeeper, Town Friendly Neighbor, 5x Town Vanilla
# - B3: Mafia Goon, Mafia Rolecop vs. Town Tracker, Town Doctor, 5x Town Vanilla
# - C1: Mafia Goon, Mafia Goon vs. Town Cop, 6x Town Vanilla
# - C2: Mafia Goon, Mafia Goon vs. Town Jailkeeper, 6x Town Vanilla
# - C3: Mafia Goon, Mafia Goon vs. Town Mason, Town Mason, 5x Town Vanilla

setup: list[tuple[m.Alignment, type[m.Role]]] = choice(
    [
        [(mafia, ex.Roleblocker), (town, ex.Cop), (town, ex.Doctor)],
        [(mafia, ex.Roleblocker), (town, ex.Jailkeeper), (town, ex.Tracker)],
        [(mafia, ex.Roleblocker), (town, ex.Mason), (town, ex.Mason)],
        [(mafia, ex.Rolecop), (town, ex.Tracker), (town, ex.Friendly_Neighbor)],
        [(mafia, ex.Rolecop), (town, ex.Jailkeeper), (town, ex.Friendly_Neighbor)],
        [(mafia, ex.Rolecop), (town, ex.Tracker), (town, ex.Doctor)],
        [(mafia, ex.Vanilla), (town, ex.Cop)],
        [(mafia, ex.Vanilla), (town, ex.Jailkeeper)],
        [(mafia, ex.Vanilla), (town, ex.Mason), (town, ex.Mason)],
    ]
)

setup.append((mafia, ex.Vanilla))
setup.extend(repeat((town, ex.Vanilla), 9 - len(setup)))

shuffle(setup)

players = [
    "Alice",
    "Bob",
    "Carol",
    "David",
    "Eve",
    "Frank",
    "Grace",
    "Heidi",
    "Ivan",
]

game.chats["global"] = m.Chat()
for (alignment, role), name in zip(setup, players):
    player = m.Player(name, role(), alignment, game=game)
    game.chats["global"].participants.add(player)

game.phase, game.day_no = m.Phase.NIGHT, 1

root = tk.Tk()
root.title("Mafia Game")

queued_actions: dict[tuple[m.Player, m.Ability], tuple[m.Player, ...]] = {}
def perform_action(player: m.Player, action: m.Ability, targets: tuple[m.Player, ...], ability_type: m.AbilityType):
    if ability_type is m.AbilityType.SHARED_ACTION:
        removed_keys: list[tuple[m.Player, m.Ability]] = []
        for k in queued_actions:
            if k[1] is action:
                removed_keys.append(k)
        for k in removed_keys:
            del queued_actions[k]
    queued_actions[player, action] = targets

notebook = ttk.Notebook(root)
player_vars: dict[m.Player, tuple[tk.IntVar, list[tk.IntVar]]] = {}
player_action_radios: dict[m.Player, list[ttk.Radiobutton]] = {}
player_target_radios: dict[m.Player, list[dict[m.Player, ttk.Radiobutton]]] = {}
player_submit_buttons: dict[m.Player, ttk.Button] = {}
player_used_by_labels: dict[m.Player, dict[m.Ability, ttk.Label]] = {}
player_chat_messages: dict[m.Player, tk.StringVar] = {}
for player in game.players:
    player_action_radios[player] = []
    player_target_radios[player] = []
    player_used_by_labels[player] = {}

    tabs = ttk.Notebook(notebook)
    frame = ttk.Frame(tabs)
    tabs.add(frame, text="Actions")

    label = ttk.Label(frame, text=f"{player.name} - {player.role_name}")
    label.grid(row=0, column=0, padx=0, pady=10, columnspan=3)

    actions = ttk.Labelframe(frame, text="Actions")
    actions.grid(row=1, column=0, padx=10, pady=10, sticky="nswe")
    action_idx = tk.IntVar(actions, value=NOT_SELECTED)

    if player.actions or player.shared_actions:
        ttk.Label(actions, text="Action").grid(row=0, column=0, padx=5, pady=5)
        ttk.Label(actions, text="# Targets").grid(row=0, column=1, padx=5, pady=5)
        if player.shared_actions:
            ttk.Label(actions, text="Used by").grid(row=0, column=2, padx=5, pady=5)
        ttk.Label(actions, text="Perform").grid(row=0, column=3, padx=5, pady=5)
        for row, action in enumerate(player.actions, 0):
            ttk.Label(actions, text=action.id).grid(row=row+1, column=0, padx=5, pady=5)
            ttk.Label(actions, text=f"{action.target_count}").grid(row=row+1, column=1, padx=5, pady=5)
            radio = ttk.Radiobutton(actions, value=row, variable=action_idx, command=partial(select_action, player))
            radio.grid(row=row+1, column=3, padx=5, pady=5)
            player_action_radios[player].append(radio)
        for row, action in enumerate(player.shared_actions, len(player.actions)):
            ttk.Label(actions, text=action.id).grid(row=row+1, column=0, padx=5, pady=5)
            ttk.Label(actions, text=f"{action.target_count}").grid(row=row+1, column=1, padx=5, pady=5)
            used_by = next((p for p, a in queued_actions if a is not action), None)
            label = ttk.Label(actions, text=used_by.name if used_by is not None else "N/A")
            label.grid(row=row+1, column=2, padx=5, pady=5)
            player_used_by_labels[player][action] = label
            radio = ttk.Radiobutton(actions, value=row, variable=action_idx, command=partial(select_action, player))
            radio.grid(row=row+1, column=3, padx=5, pady=5)
            player_action_radios[player].append(radio)
    else:
        ttk.Label(actions, text="No actions available").grid(row=0, column=0, padx=5, pady=5)

    targets = ttk.Labelframe(frame, text="Targets")
    targets.grid(row=1, column=1, padx=10, pady=10, sticky="nswe")
    target_idxs = [
        tk.IntVar(targets, value=NOT_SELECTED)
        for _ in range(max((a.target_count for a in player.actions + player.shared_actions), default=0))
    ]
    ttk.Label(targets, text="Player").grid(row=0, column=0, padx=5, pady=5)
    ttk.Label(targets, text="Role").grid(row=0, column=1, padx=5, pady=5)
    cols = len(target_idxs)
    for col in range(cols):
        player_target_radios[player].append({})
        ttk.Label(targets, text=f"Target {col+1}" if cols > 1 else "Target").grid(row=0, column=col+2, padx=5, pady=5)
    for row, target in enumerate(game.players, 0):
        ttk.Label(targets, text=target.name).grid(row=row+1, column=0, padx=5, pady=5)
        if player is target:
            ttk.Label(targets, text="You!").grid(row=row+1, column=1, padx=5, pady=5)
        elif target in player.known_players:
            ttk.Label(targets, text=f"{target.role_name}").grid(row=row+1, column=1, padx=5, pady=5)
        for col, target_idx in enumerate(target_idxs, 0):
            radio = ttk.Radiobutton(targets, value=row, variable=target_idx, command=partial(select_target, player, col), state=tk.DISABLED, text="D")
            radio.grid(row=row+1, column=col+2, padx=5, pady=5)
            player_target_radios[player][col][target] = radio

    panel = ttk.Labelframe(frame, text="Submit")
    panel.grid(row=1, column=2, padx=10, pady=10, sticky="nswe")
    
    submit_button = ttk.Button(panel, text="Submit Action", command=partial(submit_action, player), state=tk.DISABLED)
    submit_button.grid(row=0, column=0, padx=10, pady=10)
    clear_button = ttk.Button(panel, text="Clear Selection", command=partial(clear_selection, player))
    clear_button.grid(row=1, column=0, padx=10, pady=10)
    
    player_submit_buttons[player] = submit_button

    player_vars[player] = (action_idx, target_idxs)

    for id, chat in game.chats.items():
        if player in chat.participants:
            frame = ttk.Frame(tabs)
            if id.startswith("faction:"):
                tabs.add(frame, text=f"{id.removeprefix('faction:').title()} Chat")
            else:
                tabs.add(frame, text=f"{id.title()} Chat")
            chat_logs = ttk.LabelFrame(frame, text="Chat Log")
            chat_logs.grid(row=0, column=0, padx=10, pady=10, sticky="nswe", columnspan=2)
            for row, message in enumerate(chat):
                ttk.Label(chat_logs, text=f"{message.sender}").grid(row=row, column=0, padx=5, pady=5)
                ttk.Label(chat_logs, text=f"{message.content}").grid(row=row, column=1, padx=5, pady=5)
            player_chat_messages[player] = tk.StringVar(frame, value="")
            chat_input = ttk.Entry(frame, textvariable=player_chat_messages[player])
            chat_input.grid(row=1, column=0, padx=10, pady=10, sticky="nswe")
    notebook.add(tabs, text=player.name)
            

notebook.grid(row=0, column=0, padx=10, pady=10)
root.mainloop()
