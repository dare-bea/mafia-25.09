import tkinter as tk
from tkinter import ttk

from random import choice, shuffle
from itertools import product
from typing import Generic, TypeVar

import mafia as m
import examples as ex
from tests import PrintResolver

T = TypeVar("T")
class ObjectVar(tk.Variable, Generic[T]):
    """A Tkinter variable that can store any Python object."""
    def __init__(self, master: tk.Misc | None = None, value: T = None, name: str | None = None) -> None:
        super().__init__(master, value=value, name=name)
        self._value: T = value
    
    def set(self, value: T) -> None:
        self._value = value
        super().set(str(value))  # store a string just for Tkinter sync

    def get(self) -> T:
        return self._value

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
            label = ttk.Label(self.players_frame,
                              text="No players in the game!")
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

    def __init__(self, parent: tk.Misc, game: m.Game,
                 player: m.Player) -> None:
        self.parent = parent
        self.player = player
        self.game = game

        self.selected_action = ObjectVar[tuple[m.Ability, m.AbilityType] | None]()
        self.selected_targets: list[ObjectVar[m.Player | None]] = []
        self.valid_targets: tuple[tuple[m.Player, ...], ...] = ()

        self.selected_action.trace_add('write', self.update_action)

        self.setup_ui()

    def setup_ui(self) -> None:
        self.info_label = ttk.Label(
            self.parent,
            text=f"Player: {self.player.name}\nRole: {self.player.role_name}")
        self.info_label.grid(row=0,
                             column=0,
                             padx=10,
                             pady=10,
                             sticky='nswe',
                             columnspan=2)

        self.actions_frame = ttk.Labelframe(self.parent, text="Actions")
        self.actions_frame.grid(row=1,
                                column=0,
                                padx=10,
                                pady=10,
                                sticky='nswe')

        self.action_radios: dict[m.Ability, ttk.Radiobutton] = {}
        for action in self.player.actions:
            label = ttk.Radiobutton(self.actions_frame,
                                    text=action.id,
                                    value=(action,
                                           m.AbilityType.SHARED_ACTION),
                                    variable=self.selected_action)
            label.pack(pady=5, expand=True)
            self.action_radios[action] = label
            label.config(command=self.update_action)
        for action in self.player.shared_actions:
            label = ttk.Radiobutton(self.actions_frame,
                                    text=f"{action.id} (shared)",
                                    value=(action,
                                           m.AbilityType.SHARED_ACTION),
                                    variable=self.selected_action)
            label.pack(pady=5, expand=True)
            self.action_radios[action] = label
            label.config(command=self.update_action)
        if not self.action_radios:
            label = ttk.Label(self.actions_frame, text="You have no actions!")
            label.pack(pady=5, expand=True)

        self.passives_frame = ttk.Labelframe(self.parent, text="Passives")
        self.passives_frame.grid(row=1,
                                 column=1,
                                 padx=10,
                                 pady=10,
                                 sticky='nswe')

        self.passive_labels: dict[m.Ability, ttk.Label] = {}
        for passive in self.player.passives:
            label = ttk.Label(self.passives_frame, text=passive.id)
            label.pack(pady=5, expand=True)
            self.passive_labels[passive] = label
        if not self.passive_labels:
            label = ttk.Label(self.passives_frame,
                              text="You have no passives!")
            label.pack(pady=5, expand=True)

        self.targets_frame = ttk.Labelframe(self.parent, text="Targets")
        self.targets_frame.grid(row=2,
                                column=0,
                                padx=10,
                                pady=10,
                                sticky='nswe',
                                columnspan=2)

        self.target_labels: dict[m.Player, tuple[ttk.Label, ttk.Label, dict[int, ttk.Radiobutton]]] = {}
        for row, target in enumerate(game.players):
            label = ttk.Label(self.targets_frame, text=target.name)
            role_label = ttk.Label(self.targets_frame, text=target.role_name)

            label.grid(row=row, column=0, pady=5, padx=5)
            role_label.grid(row=row, column=1, pady=5, padx=5)
            self.target_labels[target] = (label, role_label, {})
        self.targets_frame.columnconfigure(0, weight=1)
        self.targets_frame.columnconfigure(1, weight=1)

        self.parent.columnconfigure(0, weight=1)
        self.parent.columnconfigure(1, weight=1)

    def update_action(self) -> None:
        for row, player in enumerate(self.game.players):
            radios = self.target_labels[player][2]
            for radio in radios.values():
                radio.destroy()
            radios.clear()
        
        selected_action = self.selected_action.get()
        if selected_action is None:
            return
        action, action_type = selected_action
        target_count = action.target_count
        self.selected_targets = [
            ObjectVar() for _ in
            range(target_count)
        ]
        for target in self.selected_targets:
            target.trace_add('write', self.update_targets)

        self.valid_targets = tuple(
            targets
            for targets in product(self.game.players, repeat=target_count)
            if action.check(self.game, self.player, targets)
        )

        print(action)
        for row, player in enumerate(self.game.players):
            radios = self.target_labels[player][2]
            for column in range(target_count):
                radio = ttk.Radiobutton(self.targets_frame,
                                       text="Select",
                                       value=player,
                                       variable=self.selected_targets[column],
                                       state=tk.DISABLED)
                radio.grid(row=row, column=column + 2, pady=5, padx=5)
                radios[column] = radio
                print(row, column)
        
        self.update_targets()

    def update_targets(self) -> None:
        selected_action = self.selected_action.get()
        if selected_action is None:
            return
        action, action_type = selected_action
        target_count = action.target_count
        
        for row, (player, (label, role_label, radios)) in enumerate(self.target_labels.items()):
            for column in range(target_count):
                for targets in (ts for ts in self.valid_targets if ts[column] is player):
                    radios[column].config(state=tk.NORMAL)
                    break
                    
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

    for name in [
            "Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace",
            "Heidi", "Ivan"
    ]:
        alignment, role = role_list.pop()
        player = m.Player(name, role, alignment)
        game.add_player(player)

    app = MafiaApp(game)
    app.root.mainloop()
