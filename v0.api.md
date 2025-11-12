# Game API Version 0

## Authorization

Headers:
* Authorization-Player-Name
* Authorization-Mod-Token

## Error Responses (4xx)

Response Body:
* `message`: `string`

### Example Response

```json
{
    "message": "Game does not exist."
}
```

## GET /api/v0/games

Get a list of games.

Authorization: None

Response Body:
* `games`: `object[]`
    * `game_id`: `int`
    * `players`: `string[]`
    * `phase`: `PHASE`
    * `day_no`: `int`

Status Codes:
* 200 OK

### Example Reponse

**200 OK**

```json
{
    "games": [
        {
            "game_id": 0,
            "players": ["Alice", "Bob", "Eve"],
            "phase": "DAY",
            "day_no": 1
        }
    ]
}
```

## POST /api/v0/games

Create a new game.

Authorization: None

Request Body:
* `players`: `string[]`
* `roles`: `object[]`
    * `role`: `string`
    * `alignment`: `string`
* `start_day`: `int` (default: `1`)
* `start_phase`: `PHASE` (default: `"DAY"`)
* `shuffle_roles`: `bool` (default: `true`)

Response Body:
* `game_id`: `int`
* `mod_token`: `string`

Status Codes:
* 201 Created
* 400 Bad Request
* 415 Unsupported Media Type

### Example Request

```json
{
    "start_day": 1,
    "start_phase": "DAY",
    "players": ["Alice", "Bob", "Eve"],
    "roles": [
        {"alignment": "Town", "role": "Vanilla"},
        {"alignment": "Town", "role": "Cop"},
        {"alignment": "Mafia", "role": "Vanilla"}
    ],
    "shuffle_roles": True
}
```

### Example Response

**201 Created**

```json
{
    "game_id": 0,
    "mod_token": "ABC123"
}
```

## GET /api/v0/games/{game_id}

Get game overview.

Authorization: None (Moderators/Players get extra information)

Response Body:
* `game_id`: `int`
* `day_no`: `int`
* `phase`: `PHASE`
* `players`: `object[]`
    * `name`: `string`
    * `is_alive`: `bool`
    * `role_name`: `string?`
    * `role`: `string?`
    * `alignment`: `string?`
* `chats`: `object[]`
    * `id`: `string`
    * `message_count`: `int`

Status Codes:
* 200 OK
* 404 Not Found

### Example Response (Unauthorized)

**200 OK**

```json
{
    "game_id": 0,
    "day_no": 1,
    "phase": "NIGHT",
    "players": [
        {
            "name": "Alice",
            "is_alive": true
        },
        {
            "name": "Bob",
            "is_alive": false,
            "role_name": "Town Cop",
            "role": "Cop",
            "alignment": "Town"
        },
        {
            "name": "Eve",
            "is_alive": true
        }
    ],
    "chats": [
        {
            "id": "global",
            "message_count": 12
        }
    ]
}
```

### Example Moderator Response 

**200 OK**

```json
{
    "game_id": 0,
    "day_no": 1,
    "phase": "NIGHT",
    "players": [
        {
            "name": "Alice",
            "is_alive": true,
            "role_name": "Vanilla Town",
            "role": "Vanilla",
            "alignment": "Town"
        },
        {
            "name": "Bob",
            "is_alive": false,
            "role_name": "Town Cop",
            "role": "Cop",
            "alignment": "Town"
        },
        {
            "name": "Eve",
            "is_alive": true,
            "role_name": "Mafia Goon",
            "role": "Vanilla",
            "alignment": "Mafia"
        }
    ],
    "chats": [
        {
            "id": "global",
            "message_count": 12
        },
        {
            "id": "faction:Mafia",
            "message_count": 2
        }
    ]
}
```

## PUT /api/v0/games/{game_id}

Update game data.

Authorization: Moderator

Request Body:
* `day_no`: `int` (default: `1`)
* `phase`: `PHASE` (default: `"DAY"`)

Status Codes:
* 204 No Content
* 400 Bad Request
* 401 Unauthorized
* 403 Forbidden
* 404 Not Found
* 415 Unsupported Media Type

### Example Request
```json
{
   "phase": "NIGHT"
}
```

### Example Response
**204 No Content**

## PATCH /api/v0/games/{game_id}

Update game data.

Authorization: Moderator

Request Body:
* `actions`: An array containing any number of the following strings:
    * `"resolve"` - Resolve the game.
    * `"next_phase"` - Will advance game phase/day.

Status Codes:
* 204 No Content
* 400 Bad Request
* 401 Unauthorized
* 403 Forbidden
* 404 Not Found
* 415 Unsupported Media Type

### Example Request

```json
{
    "actions": [
        "dequeue",
        "resolve",
        "next_phase"
    ]
}
```

### Example Response

**204 No Content**

---

## GET /api/v0/games/{game_id}/players

Get an array of players.

Returns `"players"` field from using `GET /api/v0/games/{game_id}`.

## GET /api/v0/games/{game_id}/players/{player_name}

Get player-specific information.

Authorization: Player (Self), Moderator

Response Body:
* `name`: `string`
* `is_alive`: `bool`
* `role_name`: `string`
* `role`: `object`
    * `id`: `string`
    * `actions`: `string[]`
    * `passives`: `string[]`
    * `shared_actions`: `string[]`
* `alignment`: `object`
    * `id`: `string`
    * `actions`: `string[]`
    * `passives`: `string[]`
    * `shared_actions`: `string[]`
* `known_players`: `object[]`
    * `name`: `string`
    * `is_alive`: `bool`
    * `role_name`: `string`
    * `role`: `string`
    * `alignment`: `string`
* `private_messages`: `object`
    * `message_count`: `int`

Status Codes:
* 200 OK
* 401 Unauthorized
* 403 Forbidden
* 404 Not Found

### Example Response

**200 OK**

```json
{
    "name": "Eve",
    "is_alive": true,
    "role_name": "Mafia Roleblocker",
    "role": {
        "id": "Roleblocker",
        "actions": ["Roleblocker"],
        "passives": [],
        "shared_actions": []
    },
    "alignment": {
        "id": "Mafia",
        "actions": [],
        "passives": [],
        "shared_actions": ["Mafia Factional Kill"]
    },
    "known_players": [
        {
            "name": "Carol",
            "is_alive": true,
            "role_name": "Mafia Goon",
            "role": "Vanilla",
            "alignment": "Mafia"
        }
    ]
}
```

## GET /api/v0/games/{game_id}/players/{player_name}/abilities

Get a list of abilities a player has.

Authorization: Player (Self), Moderator

Response Body:
* `actions`: `object[]`
    * `id`: `string`
    * `owner`: `string`
    * `phase`: `PHASE | null`
    * `immediate`: `bool`
    * `target_count`: `int`
    * `targets`: `string[][]` &mdash; list of valid targets
    * `queued`: `string[] | null` &mdash; the queued targets of the action
* `shared_actions`: `object[]`
    * `id`: `string`
    * `owner`: `string`
    * `used_by`: `string | null` &mdash; who is currently queuing the action
    * `phase`: `PHASE | null`
    * `immediate`: `bool`
    * `target_count`: `int`
    * `targets`: `string[][]` &mdash; list of valid targets
    * `queued`: `string[] | null` &mdash; the queued targets of the action
* `passives`: `object[]`
    * `id`: `string`
    * `phase`: `PHASE | null`
    * `immediate`: `bool`
    * `queued`: `bool` &mdash; is this passive being used this phase

Status Codes:
* 200 OK
* 401 Unauthorized
* 403 Forbidden
* 404 Not Found

### Example Response
```json
{
    "actions": [
        {
            "id": "Roleblocker",
            "phase": "NIGHT",
            "immediate": false,
            "target_count": 1,
            "targets": [["Alice"], ["Bob"]],
            "queued": null
        }
    ],
    "shared_actions": [
        {
            "id": "Mafia Factional Kill",
            "phase": "NIGHT",
            "immediate": false,
            "target_count": 1,
            "targets": [["Alice"], ["Bob"]]
            "queued": ["Alice"]
        }
    ]
    "passives": []
}
```

## POST /api/v0/games/{game_id}/players/{player_name}/abilities

Queue an action.

Authorization: Player (Self), Moderator

Request Body:
* `actions`: `object?`
    * (Action Id): `string[]` &mdash; Action targets
* `shared_actions`: `object?`
    * (Action Id): `string[]` &mdash; Action targets

Status Codes:
* 204 No Content
* 400 Bad Request
* 401 Unauthorized
* 403 Forbidden
* 404 Not Found
* 415 Unsupported Media Type

### Example Request

```json
{
    "shared_actions": {
        "Mafia Factional Kill": ["Alice"]
    }
}
```

### Example Response

**204 No Content**

## GET /api/v0/games/{game_id}/players/{player_name}/messages

Get a player's private messages (zero-indexed).

Authorization: Player (Self), Moderator

URL Parameters:
* `start`: `int` (default: `0`)
* `limit`: `int` (default: `25`)

Response Body:
* `total_messages`: `int`
* `messages`: `object[]`
    * `author`: `string`
    * `timestamp`: `int`
    * `content`: `string`

Status Codes:
* 200 OK
* 401 Unauthorized
* 403 Forbidden
* 404 Not Found &mdash; unlike with private chats, all players have private messages, even if they don't use it, so we do not return 404 if unauthorized.

### Example Response

**200 OK**

```json
{
    "total_messages": 1,
    "messages": [
        {
            "author": "Cop",
            "timestamp": 12,
            "content": "Eve is not aligned with the Town!"
        }
    ]
}
```

## POST /api/v0/games/{game_id}/players/{player_name}/messages

Send a private message to a player.

Authorization: Player (Self), Moderator

Request Body:
* `content`: `string`

Status Codes:
* 204 No Content
* 400 Bad Request
* 401 Unauthorized
* 403 Forbidden
* 404 Not Found
* 415 Unsupported Media Type

### Example Request

```json
{
    "content": "Hello!"
}
```

### Example Response

**204 No Content**

## GET /api/v0/games/{game_id}/chats

Get an array of chats.

Returns `"chats"` field from using `GET /api/v0/games/{game_id}`.

## GET /api/v0/games/{game_id}/chats/{chat_id}

Get a chat's data.

Authorization: None (Public Chats), Player (Read Perms), Moderator

Response Body:
* `chat_id`: `string`
* `read_perms`: `string[]`
* `write_perms`: `string[]`
* `total_messages`: `int`

Status Codes:
* 200 OK
* 404 Not Found &mdash; Returned in place of 401 or 403 for those without read permissions.

### Example Response

**200 OK**

```json
{
    "chat_id": "faction:Mafia",
    "read_perms": ["Carol", "Eve"],
    "write_perms": ["Carol", "Eve"],
    "total_messages": 1
}
```

## GET /api/v0/games/{game_id}/chats/{chat_id}/messages

Get chat messages (zero-indexed).

Authorization: None (Public Chats), Player (Read Perms), Moderator

URL Parameters:
* `start`: `int` (default: `0`)
* `limit`: `int` (default: `25`)

Response Body:
* `chat_id`: `string`
* `total_messages`: `int`
* `messages`: `object[]`
    * `author`: `string`
    * `timestamp`: `int`
    * `content`: `string`

Status Codes:
* 200 OK
* 404 Not Found &mdash; Returned in place of 401 or 403 for those without read permissions.

### Example Request

`?start=0&limit=25`

### Example Response

**200 OK**

```json
{
    "chat_id": "faction:Mafia",
    "total_messages": 1,
    "messages": [
        {
            "author": "Eve",
            "timestamp": 0,
            "content": "Hello!"
        }
    ]
}
```

## POST /api/v0/games/{game_id}/chats/{chat_id}

See `POST /api/v0/games/{game_id}/chats/{chat_id}/messages`

## POST /api/v0/games/{game_id}/chats/{chat_id}/messages

Send a chat message. Message is attributed to the authorized sender.

Authorization: Player (Write Perms), Moderator

Request Body:
* `content`: `string`

Status Codes:
* 204 No Content
* 400 Bad Request
* 401 Unauthorized
* 403 Forbidden
* 404 Not Found &mdash; Returned in place of 401 or 403 for those without read permissions.
* 415 Unsupported Media Type

### Example Request

```json
{
    "content": "Hello!"
}
```

### Example Response

**204 No Content**
