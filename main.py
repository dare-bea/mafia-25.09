import mafia as m
import examples as ex
from tests import PrintResolver
from itertools import repeat
from random import choice, shuffle
import tkinter as tk
from tkinter import ttk


def submit_action(
    player: m.Player,
    actions_list: tk.Listbox,
    targets_list: tk.Listbox,
) -> None:
    action_idx = actions_list.curselection()
    target_idx = targets_list.curselection()
    action = player.actions[action_idx[0]] if action_idx else None
    target = game.players[target_idx[0]] if target_idx else None

    if action is None or target is None:
        print("Please select both an action and a target.")
        return
    if not action.check(player, target, game):
        print("Invalid action or target selection.")
        return
    print(f"Player {player.name} submitted action {action} targeting {target}.")


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

for (alignment, role), name in zip(setup, players):
    m.Player(name, role(), alignment, game=game)

game.phase, game.day_no = m.Phase.DAY, 1

root = tk.Tk()
root.title("Mafia Game")

notebook = ttk.Notebook(root)

for player in game.players:
    frame = ttk.Frame(notebook)
    notebook.add(frame, text=player.name)

    label = ttk.Label(frame, text=f"{player.name} - {m.role_name(player.role, player.alignment)}")
    label.grid(row=0, column=0, padx=10, pady=10, columnspan=3)

    actions = ttk.Label(frame, text="Actions")
    actions.grid(row=1, column=0, padx=10, pady=10)
    actions_list = tk.Listbox(frame, height=max(3, len(player.actions)))
    actions_list.insert(tk.END, *(action.id for action in player.actions))
    actions_list.grid(row=2, column=0, padx=10, pady=10)

    targets = ttk.Label(frame, text="Targets")
    targets.grid(row=1, column=1, padx=10, pady=10)
    targets_list = tk.Listbox(frame, height=len(game.players))
    targets_list.insert(tk.END, *(p.name for p in game.players))
    targets_list.grid(row=2, column=1, padx=10, pady=10)

    submit_button = ttk.Button(
        frame,
        text="Submit Action",
        command=lambda: submit_action(player, actions_list, targets_list),
    )
    submit_button.grid(row=0, column=2, padx=10, pady=10)


notebook.grid(row=0, column=0, padx=10, pady=10)
root.mainloop()
