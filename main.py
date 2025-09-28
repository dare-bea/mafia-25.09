from random import choice, shuffle
import tkinter as tk
from tkinter import ttk

import mafia as m
import examples as ex
from tests import PrintResolver

class MafiaApp:
    def __init__(self, game: m.Game) -> None:
        self.root = tk.Tk()
        self.root.title("Mafia Game Setup")

        self.game = game

        self.setup_ui()
        self.root.mainloop()

    def setup_ui(self) -> None:
        self.window_nb = ttk.Notebook(self.root)
        self.window_nb.pack(expand=True, fill='both')

        main_tab = ttk.Frame(self.window_nb)
        self.window_nb.add(main_tab, text="Game")
        self.main_tab = MainWindow(main_tab, self.game)

        self.player_tabs: dict[m.Player, PlayerWindow] = {}
        for player in self.game.players:
            tab = ttk.Frame(self.window_nb)
            self.window_nb.add(tab, text=player.name)
            self.player_tabs[player] = PlayerWindow(tab, game, player)

    def destroy(self) -> None:
        self.root.destroy()

    def __del__(self) -> None:
        try:
            self.destroy()
        except tk.TclError:
            pass

class MainWindow:
    def __init__(self, parent: tk.Misc, game: m.Game) -> None:
        self.parent = parent
        self.game = game
        self.setup_ui()

    def setup_ui(self) -> None:
        self.info_label = ttk.Label(self.parent, text="Mafia Game")
        self.info_label.pack(padx=10, pady=10)

        self.players_frame = ttk.Labelframe(self.parent, text="Players")
        self.players_frame.pack(padx=10, pady=10, fill='both', expand=False)

        self.player_labels: dict[m.Player, tuple[ttk.Label, ttk.Label]] = {}
        for row, player in enumerate(game.players):
            name_label = ttk.Label(self.players_frame, text=player.name)
            role_label = ttk.Label(self.players_frame, text=player.role_name)

            name_label.grid(row=row, column=0, padx=5, pady=5)
            role_label.grid(row=row, column=1, padx=5, pady=5)

            self.player_labels[player] = (name_label, role_label)
        if not self.player_labels:
            label = ttk.Label(self.players_frame, text="No players in the game!")
            label.grid(row=0, column=0, pady=5)
            self.players_frame.columnconfigure(0, weight=1)
        else:
            self.players_frame.columnconfigure(0, weight=1)
            self.players_frame.columnconfigure(1, weight=1)
    
    def destroy(self) -> None:
        for widget in self.parent.winfo_children():
            widget.destroy()
    
    def __del__(self) -> None:
        try:
            self.destroy()
        except tk.TclError:
            pass

class PlayerWindow:
    def __init__(self, parent: tk.Misc, game: m.Game, player: m.Player) -> None:
        self.parent = parent
        self.player = player
        self.game = game
        self.setup_ui()
    
    def setup_ui(self) -> None:
        self.info_label = ttk.Label(self.parent, text=f"Player: {self.player.name}\nRole: {self.player.role.id}")
        self.info_label.grid(row=0, column=0, padx=10, pady=10, sticky='nswe', columnspan=2)

        self.actions_frame = ttk.Labelframe(self.parent, text="Actions")
        self.actions_frame.grid(row=1, column=0, padx=10, pady=10, sticky='nswe')

        self.action_labels: dict[m.Ability, ttk.Label] = {}
        for action in self.player.actions:
            label = ttk.Label(self.actions_frame, text=action.id)
            label.pack(pady=5, expand=True)
            self.action_labels[action] = label
        for action in self.player.shared_actions:
            label = ttk.Label(self.actions_frame, text=f"{action.id} (shared)")
            label.pack(pady=5, expand=True)
            self.action_labels[action] = label
        if not self.action_labels:
            label = ttk.Label(self.actions_frame, text="You have no actions!")
            label.pack(pady=5, expand=True)
        
        self.passives_frame = ttk.Labelframe(self.parent, text="Passives")
        self.passives_frame.grid(row=1, column=1, padx=10, pady=10, sticky='nswe')

        self.passive_labels: dict[m.Ability, ttk.Label] = {}
        for passive in self.player.passives:
            label = ttk.Label(self.passives_frame, text=passive.id)
            label.pack(pady=5, expand=True)
            self.passive_labels[passive] = label
        if not self.passive_labels:
            label = ttk.Label(self.passives_frame, text="You have no passives!")
            label.pack(pady=5, expand=True)

        self.targets_frame = ttk.Labelframe(self.parent, text="Targets")
        self.targets_frame.grid(row=2, column=0, padx=10, pady=10, sticky='nswe', columnspan=2)

        self.target_labels: dict[m.Player, tuple[ttk.Label, ttk.Label]] = {}
        for row, target in enumerate(game.players):
            label = ttk.Label(self.targets_frame, text=target.name)
            role_label = ttk.Label(self.targets_frame, text=target.role_name)
            
            label.grid(row=row, column=0, pady=5, padx=5)
            role_label.grid(row=row, column=1, pady=5, padx=5)
            self.target_labels[target] = (label, role_label)
        self.targets_frame.columnconfigure(0, weight=1)
        self.targets_frame.columnconfigure(1, weight=1)

        self.parent.columnconfigure(0, weight=1)
        self.parent.columnconfigure(1, weight=1)

    def destroy(self) -> None:
        for widget in self.parent.winfo_children():
            widget.destroy()
    
    def __del__(self) -> None:
        try:
            self.destroy()
        except tk.TclError:
            pass

if __name__ == "__main__":
    game = m.Game()
    town = ex.Town()
    mafia = ex.Mafia()

    role_list: list[tuple[m.Alignment, m.Role]] = [
        (town, ex.Vanilla()),
        (town, ex.Vanilla()),
        (town, ex.Vanilla()),
        (town, ex.Vanilla()),
        (town, ex.Vanilla()),
        (town, ex.Vanilla()),
        (town, ex.Cop()),
        (mafia, ex.Vanilla()),
        (mafia, ex.Vanilla()),
    ]
    shuffle(role_list)

    for name in ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace", "Heidi", "Ivan"]:
        alignment, role = role_list.pop()
        player = m.Player(name, role, alignment)
        game.add_player(player)
    
    app = MafiaApp(game)
    app.root.mainloop()