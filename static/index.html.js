function newGame() {
    // POST request to /api/v0/games
    fetch(
        "/api/v0/games",
        {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                "players": ["Alice", "Bob", "Charlie", "David", "Eve", "Frank", "Grace", "Heidi", "Ivan"],
                "roles": [
                    {"role": "Gunsmith", "alignment": "Town"},
                    {"role": "Doctor", "alignment": "Town"},
                    {"role": "Cop", "alignment": "Town"},
                    {"role": "Rolestopper", "alignment": "Town"},
                    {"role": "Bulletproof", "alignment": "Town"},
                    {"role": "Vanilla", "alignment": "Town"},
                    {"role": "Vanilla", "alignment": "Serial Killer"},
                    {"role": "Roleblocker", "alignment": "Mafia"},
                    {"role": "Vanilla", "alignment": "Mafia"},
                ],
                "start_phase": "DAY"
            })
        }
    )
    .then(response => {
        if (!response.ok)
            return response.json().then(data => {
                const message = `${response.status} ${response.statusText}: ${data.message}`
                alert(message);
                console.error(message);
            })
        else
            return response.json().then(data => {
                console.log(data);
                // url = /game/<game_id>?modtkn=<mod_token>
                game_id = encodeURIComponent(data["game_id"]);
                // URL encode the mod token, just in case
                mod_token = encodeURIComponent(data["mod_token"]);
                window.location.href = `/games/${game_id}/mod?modtoken=${mod_token}`;
            });
    })
}