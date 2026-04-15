# EDD Integration Guide — Adding MARVIN Support

**Audience:** EDD development team (C# / .NET, Claude-assisted)
**Prerequisites:** Familiarity with the EDD codebase (Hermes, Void, Sphinx, Alexandria)
**MARVIN spec:** [phase4_mqtt.md](phase4_mqtt.md) — full protocol reference
**empnode spec:** `empnode/docs/mqtt-topics.md` — existing protocol for comparison

---

## 1. Overview

MARVIN is a tabletop LARP game controller that connects to the same MQTT broker as empnode nodes. It publishes game state and subscribes to configuration commands. EDD must be extended to:

1. **Subscribe** to `marvin/+/state/#` topics and route inbound messages to Hermes
2. **Dispatch** typed MARVIN messages through HermesService alongside existing empnode handlers
3. **Publish** configuration commands to `marvin/<id>/cmd/...` topics
4. **React** to MARVIN events in Sphinx puzzle logic (via IEventBus)
5. **Persist** MARVIN data in Alexandria — characters via existing `Character` table (RFID lookup), items via new `MarvinItem` table

MARVIN and empnode share a broker but use **completely separate topic namespaces**. They never communicate directly — EDD is the only bridge.

---

## 2. Architecture Comparison: empnode vs MARVIN

| Aspect | empnode | MARVIN |
|--------|--------|--------|
| **Topic namespace** | `empnode/` | `marvin/` |
| **Discovery** | MAC-based `empnode/discovery/request` / `assign/<mac>` | None — config-based, `node_id` from `marvinconfig.txt` |
| **Identity** | Assigned by EDD on first connect | Fixed in config (e.g. `marvin-001`) |
| **RFID format** | 10-char hex string (e.g. `"04A3B7C801"`) | 10-char hex string (e.g. `"00000003E9"`) in both JSON payloads and config files |
| **RFID actions** | `"detected"` / `"removed"` | `"detected"` (character/item) / `"unknown"` (unregistered tag) |
| **Heartbeat** | Every 10 s (firmware) / 5 s (sim) | Every 30 s |
| **Retained messages** | `state/dmx/<room>`, `state/status` | `state/items`, `state/table`, `state/config_version` |
| **Capabilities** | `["rfid", "dmx", "pixel"]` per node | Fixed (RFID + LED ring, no DMX) |
| **Commands EDD sends** | DMX set/fade/update/config, pixel set/fade, minigame start/abort | rfid/register, table/status, well/size, table/color/idle, game/color, sync/offer |
| **Node count** | Many (10+) | One per table (can be multiple tables) |

### Key Design Decisions

1. **No discovery flow.** MARVIN tables are pre-configured. EDD should register them via Alexandria (manual DB entry or admin UI) rather than expecting a discovery request.
2. **RFID as 10-char hex string.** MARVIN publishes RFID values as 10-char uppercase hex strings (e.g. `"00000003E9"`), matching EDD's existing format for empnode. Direct RFID lookups against the `Character` table work without conversion. Inbound command handlers also accept integer values as a defensive safeguard (converted to hex internally).
3. **Config sync.** MARVIN has its own config versioning system. On connect it publishes `state/config_version` (retained). EDD should respond with `cmd/sync/offer` to reconcile character/item lists.

---

## 3. MARVIN MQTT Protocol Reference

### 3.1 State Topics (MARVIN publishes, EDD subscribes)

| Topic | Retained | Payload | Trigger |
|-------|----------|---------|---------|
| `marvin/<id>/state/rfid` | No | `{"action":"detected","type":"character","name":"Aldric","rfid":"0000000004"}` | Character scans RFID |
| | | | `{"action":"detected","type":"item","name":"Staff","rfid":"000000000C"}` | Item scans RFID |
| | | `{"action":"unknown","rfid":"000001869F"}` | Unknown tag scanned |
| `marvin/<id>/state/items` | Yes | `{"action":"connected","changed":{...},"connected":[...],"well":{...}}` | Item connected |
| | | `{"action":"disconnected","changed":{...},"connected":[...],"well":{...}}` | Item disconnected |
| | | `{"action":"cleared","connected":[],"well":{...}}` | Round complete |
| | | `{"action":"overload","connected":[],"well":{...}}` | Overload event |
| `marvin/<id>/state/game` | No | `{"event":"failure","failures":1,"limit":3}` | Game input failure |
| | | `{"event":"success","elapsed_s":45.2}` | Game round won |
| `marvin/<id>/state/table` | Yes | `{"status":"active"}` | Table status change |
| `marvin/<id>/state/heartbeat` | No | `{"uptime":3600}` | Every 30 s |
| `marvin/<id>/state/config_version` | Yes | `{"version":42}` | On connect + every config write |
| `marvin/<id>/state/sync/push` | No | `{"version":42,"characters":[...],"items":[...]}` | When MARVIN version > EDD version |

### 3.2 Command Topics (EDD publishes, MARVIN subscribes)

| Topic | Payload | Effect |
|-------|---------|--------|
| `marvin/<id>/cmd/rfid/register` | `{"type":"character","name":"Sera","rfid":"000001869F","skills":["connect1"]}` | Register new character |
| | `{"type":"item","name":"Amulet","rfid":"00000015B3","skills":[],"level":2,"load":15,"function":"..."}` | Register new item |
| `marvin/<id>/cmd/table/status` | `{"status":"active"\|"broken"\|"off"\|"disabled"}` | Set table operational state |
| `marvin/<id>/cmd/well/size` | `{"size":100}` | Set power well capacity |
| `marvin/<id>/cmd/table/color/idle` | `{"color":[255,0,128]}` | Set idle LED colour |
| `marvin/<id>/cmd/game/color` | `{"game":"linegame"\|"runegame","color":[R,G,B]}` | Set game LED colour |
| `marvin/<id>/cmd/sync/offer` | `{"version":45,"characters":[...],"items":[...]}` | Offer config sync |

### 3.3 Sync Protocol

1. MARVIN connects (or reconnects) and publishes `state/config_version` (retained)
2. EDD sees the version and compares with its own
3. If EDD version > MARVIN version: EDD sends `cmd/sync/offer` with full character/item data
4. If MARVIN version > EDD version: MARVIN publishes `state/sync/push` with its data
5. If versions equal: no action

---

## 4. Implementation Steps

### Step 1: Create MARVIN Message Models

**Location:** `Edd.Shared/Models/Mqtt/`

Create new model classes alongside existing Void models:

```csharp
// MarvinRfidModel.cs
public class MarvinRfidModel
{
    public string Action { get; set; }   // "detected" | "unknown"
    public string? Type { get; set; }    // "character" | "item" (null when unknown)
    public string? Name { get; set; }    // human-readable name (null when unknown)
    public string Rfid { get; set; }     // 10-char uppercase hex string (e.g. "00000003E9")
}

// MarvinItemsModel.cs
public class MarvinItemsModel
{
    public string Action { get; set; }   // "connected" | "disconnected" | "cleared" | "overload"
    public MarvinItemRef? Changed { get; set; }
    public MarvinItemRef[] Connected { get; set; } = [];
    public MarvinWellState Well { get; set; }
}

public class MarvinItemRef
{
    public string Name { get; set; }
    public string Rfid { get; set; }
}

public class MarvinWellState
{
    public int Use { get; set; }
    public int Capacity { get; set; }
    public double Pct { get; set; }
}

// MarvinGameModel.cs
public class MarvinGameModel
{
    public string Event { get; set; }    // "failure" | "success"
    public int? Failures { get; set; }
    public int? Limit { get; set; }
    public double? ElapsedS { get; set; }
}

// MarvinTableModel.cs
public class MarvinTableModel
{
    public string Status { get; set; }   // "active" | "broken" | "off" | "disabled"
}

// MarvinHeartbeatModel.cs
public class MarvinHeartbeatModel
{
    public long Uptime { get; set; }     // seconds since MARVIN started
}

// MarvinConfigVersionModel.cs
public class MarvinConfigVersionModel
{
    public int Version { get; set; }
}

// MarvinSyncPushModel.cs
public class MarvinSyncPushModel
{
    public int Version { get; set; }
    public MarvinSyncCharacter[] Characters { get; set; } = [];
    public MarvinSyncItem[] Items { get; set; } = [];
}

public class MarvinSyncCharacter
{
    public string Rfid { get; set; }
    public string Name { get; set; }
    public string[] Skills { get; set; } = [];   // MARVIN shorthand tokens (see Step 6 skill mapping)
}

public class MarvinSyncItem
{
    public string Rfid { get; set; }
    public string Name { get; set; }
    public int Level { get; set; }
    public int Load { get; set; }
    public string Function { get; set; }
}
```

### Step 2: Extend QueueMessageRouter

**File:** `Edd.Shared/Models/QueueMessageRouter.cs`

Add MARVIN topic patterns to the static router. The router currently matches `empnode/...` prefixes — add `marvin/...` alongside:

```csharp
// New QueueType entries needed
// Add to QueueType enum: MarvinRfid, MarvinItems, MarvinGame, MarvinTable,
//                        MarvinHeartbeat, MarvinConfigVersion, MarvinSyncPush

// In QueueMessageRouter.Route():
if (topic.StartsWith("marvin/"))
{
    var parts = topic.Split('/');
    // parts: ["marvin", "<node-id>", "state", "<type>", ...]
    if (parts.Length >= 4 && parts[2] == "state")
    {
        var nodeId = parts[1];
        return parts[3] switch
        {
            "rfid"           => Deserialize<MarvinRfidModel>(nodeId, topic, payload, QueueType.MarvinRfid),
            "items"          => Deserialize<MarvinItemsModel>(nodeId, topic, payload, QueueType.MarvinItems),
            "game"           => Deserialize<MarvinGameModel>(nodeId, topic, payload, QueueType.MarvinGame),
            "table"          => Deserialize<MarvinTableModel>(nodeId, topic, payload, QueueType.MarvinTable),
            "heartbeat"      => Deserialize<MarvinHeartbeatModel>(nodeId, topic, payload, QueueType.MarvinHeartbeat),
            "config_version" => Deserialize<MarvinConfigVersionModel>(nodeId, topic, payload, QueueType.MarvinConfigVersion),
            "sync"           => parts.Length >= 5 && parts[4] == "push"
                                ? Deserialize<MarvinSyncPushModel>(nodeId, topic, payload, QueueType.MarvinSyncPush)
                                : null,
            _                => null
        };
    }
}
```

### Step 3: Extend EddWorker Subscriptions

**File:** `Edd.Core/Workers/EddWorker.cs`

In the startup sequence where VoidClient subscribes to empnode topics, add MARVIN subscriptions:

```csharp
// After existing empnode subscriptions:
await voidClient.SubscribeAsync("marvin/+/state/rfid");
await voidClient.SubscribeAsync("marvin/+/state/items");
await voidClient.SubscribeAsync("marvin/+/state/game");
await voidClient.SubscribeAsync("marvin/+/state/table");
await voidClient.SubscribeAsync("marvin/+/state/heartbeat");
await voidClient.SubscribeAsync("marvin/+/state/config_version");
await voidClient.SubscribeAsync("marvin/+/state/sync/push");
```

The existing `OnMessageReceived` wiring already passes all messages through `QueueMessageRouter.Route()`, so MARVIN messages will flow through the same channel as empnode messages.

### Step 4: Add MARVIN Handlers to HermesService

**File:** `Edd.Services.Hermes/HermesService.cs`

Extend the `DispatchAsync` pattern match:

```csharp
private Task DispatchAsync(IQueueElement element, CancellationToken ct) => element switch
{
    // Existing empnode handlers...
    QueueElement<VoidRequestModel>       e => HandleDiscoveryAsync(e.Payload, ct),
    QueueElement<VoidHeartbeatModel>     e => HandleHeartbeatAsync(e.NodeName, e.Payload, ct),
    // ...existing...

    // MARVIN handlers
    QueueElement<MarvinRfidModel>          e => HandleMarvinRfidAsync(e.NodeName, e.Payload, ct),
    QueueElement<MarvinItemsModel>         e => HandleMarvinItemsAsync(e.NodeName, e.Payload, ct),
    QueueElement<MarvinGameModel>          e => HandleMarvinGameAsync(e.NodeName, e.Payload, ct),
    QueueElement<MarvinTableModel>         e => HandleMarvinTableAsync(e.NodeName, e.Payload, ct),
    QueueElement<MarvinHeartbeatModel>     e => HandleMarvinHeartbeatAsync(e.NodeName, e.Payload, ct),
    QueueElement<MarvinConfigVersionModel> e => HandleMarvinConfigVersionAsync(e.NodeName, e.Payload, ct),
    QueueElement<MarvinSyncPushModel>      e => HandleMarvinSyncPushAsync(e.NodeName, e.Payload, ct),

    _                                        => HandleUnknownAsync(element.Topic, ct)
};
```

#### Handler Implementations

```csharp
private Task HandleMarvinRfidAsync(string nodeId, MarvinRfidModel model, CancellationToken ct)
{
    // Publish to EventBus — Sphinx puzzles can react to MARVIN RFID events
    var eventType = model.Action == "detected"
        ? $"marvin_rfid_{model.Type ?? "unknown"}"  // marvin_rfid_character, marvin_rfid_item, marvin_rfid_unknown
        : "marvin_rfid_unknown";

    eventBus.Publish(new BusEvent<MarvinRfidModel>
    {
        EventType = eventType,
        Source = nodeId,
        Payload = model
    });

    MessagesHandled.Add(1, new TagList { { "type", "marvin_rfid" } });
    return Task.CompletedTask;
}

private Task HandleMarvinItemsAsync(string nodeId, MarvinItemsModel model, CancellationToken ct)
{
    // State reconstruction: log + publish to EventBus
    eventBus.Publish(new BusEvent<MarvinItemsModel>
    {
        EventType = $"marvin_items_{model.Action}",  // marvin_items_connected, etc.
        Source = nodeId,
        Payload = model
    });

    MessagesHandled.Add(1, new TagList { { "type", "marvin_items" } });
    return Task.CompletedTask;
}

private Task HandleMarvinGameAsync(string nodeId, MarvinGameModel model, CancellationToken ct)
{
    eventBus.Publish(new BusEvent<MarvinGameModel>
    {
        EventType = $"marvin_game_{model.Event}",  // marvin_game_failure, marvin_game_success
        Source = nodeId,
        Payload = model
    });

    MessagesHandled.Add(1, new TagList { { "type", "marvin_game" } });
    return Task.CompletedTask;
}

private Task HandleMarvinTableAsync(string nodeId, MarvinTableModel model, CancellationToken ct)
{
    ravens.LogInformation("MARVIN table status from NodeId={NodeId}. Status={Status}",
        nodeId, model.Status);
    // Informational — could optionally update NodeRegistry or WorldState
    MessagesHandled.Add(1, new TagList { { "type", "marvin_table" } });
    return Task.CompletedTask;
}

private Task HandleMarvinHeartbeatAsync(string nodeId, MarvinHeartbeatModel model, CancellationToken ct)
{
    // Reuse the existing INodeRegistry if MARVIN tables are registered there
    // Otherwise just log
    ravens.LogDebug("MARVIN heartbeat from NodeId={NodeId} Uptime={Uptime}s", nodeId, model.Uptime);
    MessagesHandled.Add(1, new TagList { { "type", "marvin_heartbeat" } });
    return Task.CompletedTask;
}

private async Task HandleMarvinConfigVersionAsync(
    string nodeId, MarvinConfigVersionModel model, CancellationToken ct)
{
    ravens.LogInformation("MARVIN config version from NodeId={NodeId}. Version={Version}",
        nodeId, model.Version);

    // Compare with EDD's stored version (MarvinTableEntity.ConfigVersion)
    // If EDD has newer data, send sync/offer with characters + items

    MessagesHandled.Add(1, new TagList { { "type", "marvin_config_version" } });
}

private async Task HandleMarvinSyncPushAsync(
    string nodeId, MarvinSyncPushModel model, CancellationToken ct)
{
    ravens.LogInformation("MARVIN sync push from NodeId={NodeId}. Version={Version} Characters={C} Items={I}",
        nodeId, model.Version, model.Characters.Length, model.Items.Length);

    // Accept MARVIN's data as ground truth when MARVIN version > EDD version
    // Characters: resolve by RFID against Character table, link CharacterSkill entries
    // Items: store in MarvinItem table (see Step 6)
    // Update MarvinTableEntity.ConfigVersion

    MessagesHandled.Add(1, new TagList { { "type", "marvin_sync_push" } });
}
```

### Step 5: Add MARVIN Command Publishing to IHermesService

**File:** `Edd.Shared/Abstractions/IHermesService.cs`

```csharp
// Add to IHermesService interface:
Task SendMarvinRegisterAsync(string nodeId, MarvinRegisterCommand command, CancellationToken ct);
Task SendMarvinTableStatusAsync(string nodeId, MarvinTableStatusCommand command, CancellationToken ct);
Task SendMarvinWellSizeAsync(string nodeId, MarvinWellSizeCommand command, CancellationToken ct);
Task SendMarvinColorIdleAsync(string nodeId, MarvinColorCommand command, CancellationToken ct);
Task SendMarvinGameColorAsync(string nodeId, MarvinGameColorCommand command, CancellationToken ct);
Task SendMarvinSyncOfferAsync(string nodeId, MarvinSyncOfferCommand command, CancellationToken ct);
```

**File:** `Edd.Shared/Models/Mqtt/` — new command models:

```csharp
// MarvinRegisterCommand.cs
public class MarvinRegisterCommand
{
    public string Type { get; set; }     // "character" | "item"
    public string Name { get; set; }
    public string Rfid { get; set; }     // 10-char uppercase hex
    public int Level { get; set; } = 1;
    public string[]? Skills { get; set; }  // character only (MARVIN shorthand tokens)
    public int? Load { get; set; }         // item only
    public string? Function { get; set; }  // item only
}

// MarvinTableStatusCommand.cs
public class MarvinTableStatusCommand
{
    public string Status { get; set; }   // "active" | "broken" | "off" | "disabled"
}

// MarvinWellSizeCommand.cs
public class MarvinWellSizeCommand
{
    public int Size { get; set; }
}

// MarvinColorCommand.cs
public class MarvinColorCommand
{
    public int[] Color { get; set; }     // [R, G, B]
}

// MarvinGameColorCommand.cs
public class MarvinGameColorCommand
{
    public string Game { get; set; }     // "linegame" | "runegame"
    public int[] Color { get; set; }     // [R, G, B]
}

// MarvinSyncOfferCommand.cs
public class MarvinSyncOfferCommand
{
    public int Version { get; set; }
    public MarvinSyncCharacter[] Characters { get; set; } = [];
    public MarvinSyncItem[] Items { get; set; } = [];
}
```

**File:** `Edd.Services.Hermes/HermesService.cs` — command publisher implementations:

```csharp
public Task SendMarvinRegisterAsync(string nodeId, MarvinRegisterCommand cmd, CancellationToken ct)
    => PublishMarvinCommandAsync(nodeId, "rfid/register", cmd, ct);

public Task SendMarvinTableStatusAsync(string nodeId, MarvinTableStatusCommand cmd, CancellationToken ct)
    => PublishMarvinCommandAsync(nodeId, "table/status", cmd, ct);

public Task SendMarvinWellSizeAsync(string nodeId, MarvinWellSizeCommand cmd, CancellationToken ct)
    => PublishMarvinCommandAsync(nodeId, "well/size", cmd, ct);

public Task SendMarvinColorIdleAsync(string nodeId, MarvinColorCommand cmd, CancellationToken ct)
    => PublishMarvinCommandAsync(nodeId, "table/color/idle", cmd, ct);

public Task SendMarvinGameColorAsync(string nodeId, MarvinGameColorCommand cmd, CancellationToken ct)
    => PublishMarvinCommandAsync(nodeId, "game/color", cmd, ct);

public Task SendMarvinSyncOfferAsync(string nodeId, MarvinSyncOfferCommand cmd, CancellationToken ct)
    => PublishMarvinCommandAsync(nodeId, "sync/offer", cmd, ct);

private async Task PublishMarvinCommandAsync<T>(
    string nodeId, string commandType, T command, CancellationToken ct)
{
    // Note: MARVIN uses marvin/ prefix, not empnode/
    var topic = $"marvin/{nodeId}/cmd/{commandType}";
    var json = JsonSerializer.Serialize(command, JsonOptions);
    ravens.LogInformation("Publishing MARVIN {CommandType} to NodeId={NodeId}. Topic={Topic}",
        commandType, nodeId, topic);
    await voidClient.PublishAsync(topic, json, ct);
}
```

### Step 6: Alexandria Persistence — Characters, Items, and Table State

MARVIN characters and items need to be stored in Alexandria for the admin UI, Sphinx queries, and config sync. The approach differs per entity type:

- **Characters** → use the existing `Character` table (RFID lookup, same 10-char hex format)
- **Items** → new `MarvinItem` table (EDD's `Item` table has no RFID and is character-bound; MARVIN items are table-bound)
- **Table state** → new `MarvinTable` table (node status, config version, heartbeat)

#### 6.1 Skill Mapping

MARVIN uses shorthand skill tokens that map 1:1 to actual Emphebion skills in the Constructeurs category.

> **Unverified:** The skill name mapping below is based on best-effort matching and has not been verified against a live Nexus export. Confirm the exact EDD skill names with a Nexus data dump before implementing the mapping in EDD.

| MARVIN token | EDD skill name (Nexus) | Notes |
|---|---|---|
| `connect1` | Koppelen magisch construct niveau 1 | |
| `connect2` | Koppelen magisch construct niveau 2 | |
| `connect3` | Koppelen magisch construct niveau 3 | |
| `disconnectall` | Bron Vrijmaken | |
| `disconnect1item` | Ontkoppelen magisch construct niveau 1 | |
| `disconnect1item` | Ontkoppelen magisch construct niveau 2 | See note below |
| `disconnect1item` | Ontkoppelen magisch construct niveau 3 | |
| `wellsize` | Putgrootte bepalen | |
| `SL` | *(none)* | Game master override — MARVIN-only, not mapped to EDD |

**Note on `disconnect1item`:** MARVIN intentionally maps this single token to three EDD skills. In-game, a character with `disconnect1item` can disconnect any one item regardless of level — the three separate Ontkoppelen skills in EDD are the Nexus representation of this same ability across levels. When mapping EDD → MARVIN, any of the three Ontkoppelen skills should resolve to `disconnect1item`.

**Resolving skills at sync time:**

```csharp
// Skill mapping: MARVIN shorthand → EDD skill name(s)
// Store in configuration (appsettings.json or Alexandria) so it can be updated
// without code changes if Nexus skill names change.
private static readonly Dictionary<string, string[]> MarvinSkillMap = new()
{
    ["connect1"]       = ["Koppelen magisch construct niveau 1"],
    ["connect2"]       = ["Koppelen magisch construct niveau 2"],
    ["connect3"]       = ["Koppelen magisch construct niveau 3"],
    ["disconnectall"]  = ["Bron Vrijmaken"],
    ["disconnect1item"] = [
        "Ontkoppelen magisch construct niveau 1",
        "Ontkoppelen magisch construct niveau 2",
        "Ontkoppelen magisch construct niveau 3"
    ],
    ["wellsize"]       = ["Putgrootte bepalen"],
    // "SL" deliberately not mapped — GM override is MARVIN-internal
};
```

> **Known issue — Nexus dependency:** The skill mapping above assumes stable skill names in Nexus. If Nexus renames or restructures skills in the Constructeurs category, this mapping must be updated. Store the mapping in configuration (not hardcoded) so it can be adjusted without redeployment. This should be addressed in a future iteration by either: (a) using NexusId instead of skill names for the mapping, or (b) adding a MARVIN-specific skill alias field to Nexus.

#### 6.2 Character Persistence (Existing Tables)

When MARVIN publishes a character via `state/rfid` or `sync/push`, look up the `Character` table by RFID (exact 10-char hex match). The character already exists in Alexandria if it was imported from Nexus.

```csharp
// In HandleMarvinSyncPushAsync:
foreach (var c in model.Characters)
{
    // Look up existing character by RFID
    var characters = await alexandria.GetAsync<CharacterEntity>("Rfid = @Rfid", new { c.Rfid });
    var character = characters.FirstOrDefault();

    if (character == null)
    {
        ravens.LogWarning("MARVIN character RFID={Rfid} Name={Name} not found in Character table. "
            + "Register in Nexus first, or create a stub entry.", c.Rfid, c.Name);
        continue;
    }

    // Verify/update character-skill links for MARVIN-relevant skills
    foreach (var marvinSkill in c.Skills)
    {
        if (marvinSkill == "SL") continue; // GM override, not an EDD skill

        if (!MarvinSkillMap.TryGetValue(marvinSkill, out var eddSkillNames))
        {
            ravens.LogWarning("Unknown MARVIN skill token: {Skill}", marvinSkill);
            continue;
        }

        foreach (var skillName in eddSkillNames)
        {
            var skills = await alexandria.GetAsync<SkillEntity>("Name = @Name", new { Name = skillName });
            var skill = skills.FirstOrDefault();
            if (skill == null)
            {
                ravens.LogWarning("EDD skill '{SkillName}' not found — may need Nexus import or stub", skillName);
                continue;
            }
            // Ensure CharacterSkill link exists (INSERT OR IGNORE semantics)
            await alexandria.ImportAsync(new[] { new CharacterSkillEntity
            {
                CharacterId = character.Id,
                SkillId = skill.Id
            }});
        }
    }
}
```

If a MARVIN character's RFID is not found in the `Character` table, it means the character hasn't been imported from Nexus yet. Log a warning — the EDD admin can then either import from Nexus or manually create a stub `CharacterEntity`.

#### 6.3 Item Persistence (New MarvinItem Table)

EDD's existing `Item` table is character-bound (FK to Character, NOT NULL) with no RFID field. MARVIN items are table-bound physical objects with RFID tags. A new `MarvinItem` table models this correctly and is designed for future alignment with Nexus:

```sql
-- MarvinItem.sql — add to Alexandria.Tables/Tables/
CREATE TABLE IF NOT EXISTS MarvinItem
(
    Id          INTEGER PRIMARY KEY AUTOINCREMENT,
    TableNodeId TEXT    NOT NULL,                          -- e.g. "marvin-001"
    NexusId     TEXT,                                      -- NULL until Nexus adds MARVIN item support
    Rfid        TEXT    NOT NULL,                          -- 10-char uppercase hex
    Name        TEXT    NOT NULL,
    DisplayName TEXT,
    Level       INTEGER NOT NULL DEFAULT 1,
    Load        INTEGER NOT NULL DEFAULT 1,
    Function    TEXT    NOT NULL DEFAULT '',
    Connected   INTEGER NOT NULL DEFAULT 0,
    CreatedAt   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UpdatedAt   TEXT,
    UNIQUE(TableNodeId, Rfid)
);
```

```csharp
// MarvinItemEntity.cs
[Table("MarvinItem")]
public class MarvinItemEntity : BaseEntity
{
    public string TableNodeId { get; set; }
    public string? NexusId { get; set; }       // NULL until Nexus alignment
    public string Rfid { get; set; }           // 10-char uppercase hex
    public string Name { get; set; }
    public string? DisplayName { get; set; }
    public int Level { get; set; }
    public int Load { get; set; }
    public string Function { get; set; }
    public bool Connected { get; set; }
}
```

When Nexus eventually adds MARVIN item support, the `NexusId` field can be populated and the data can be migrated to the main `Item` table (adding `Rfid` to that table at that point). Until then, `MarvinItem` is self-contained.

#### 6.4 Table State Persistence

```sql
-- MarvinTable.sql — add to Alexandria.Tables/Tables/
CREATE TABLE IF NOT EXISTS MarvinTable
(
    Id            INTEGER PRIMARY KEY AUTOINCREMENT,
    NodeId        TEXT    NOT NULL UNIQUE,
    Status        TEXT    NOT NULL DEFAULT 'off',
    ConfigVersion INTEGER NOT NULL DEFAULT 0,
    WellCapacity  INTEGER NOT NULL DEFAULT 0,
    WellUse       INTEGER NOT NULL DEFAULT 0,
    LastHeartbeat TEXT,
    CreatedAt     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UpdatedAt     TEXT
);
```

```csharp
// MarvinTableEntity.cs
[Table("MarvinTable")]
public class MarvinTableEntity : BaseEntity
{
    public string NodeId { get; set; }
    public string Status { get; set; }
    public int ConfigVersion { get; set; }
    public int WellCapacity { get; set; }
    public int WellUse { get; set; }
    public DateTime? LastHeartbeat { get; set; }
}
```

#### 6.5 Sync Flow

When a `sync/push` arrives from MARVIN (version > EDD's stored version):

1. **Characters:** For each character in the push, look up by RFID in `Character` table. Verify/create `CharacterSkill` links using the skill mapping. Log warnings for unresolved RFIDs or skills.
2. **Items:** Delete + re-insert into `MarvinItem` for this `TableNodeId`.
3. **Table:** Update `MarvinTableEntity.ConfigVersion`.

```csharp
private async Task HandleMarvinSyncPushAsync(string nodeId, MarvinSyncPushModel model, CancellationToken ct)
{
    await alexandria.ExecuteInTransactionAsync(async () =>
    {
        // 1. Characters — resolve against existing Character table
        foreach (var c in model.Characters)
            await ResolveMarvinCharacterAsync(nodeId, c);

        // 2. Items — replace in MarvinItem table
        await alexandria.DeleteWhereAsync<MarvinItemEntity>("TableNodeId = @NodeId", new { NodeId = nodeId });
        foreach (var item in model.Items)
        {
            await alexandria.UpsertAsync(new MarvinItemEntity
            {
                TableNodeId = nodeId,
                Rfid = item.Rfid,
                Name = item.Name,
                DisplayName = item.DisplayName,
                Level = item.Level,
                Load = item.Load,
                Function = item.Function,
            });
        }

        // 3. Update table config version
        var tables = await alexandria.GetAsync<MarvinTableEntity>("NodeId = @NodeId", new { NodeId = nodeId });
        var table = tables.FirstOrDefault();
        if (table != null)
        {
            table.ConfigVersion = model.Version;
            await alexandria.UpsertAsync(table);
        }
    });
}
```

Add the two `.sql` files to `Alexandria.Tables/Tables/` and execute them in `AlexandriaService.StartAsync()`.

### Step 7: Wire Sphinx Puzzle Subscriptions

MARVIN events become available on the IEventBus with `marvin_*` event types. Sphinx puzzles can subscribe:

```json
{
  "name": "marvin_table_overload_reaction",
  "inputs": [
    {
      "type": "marvin_items_overload",
      "node_filter": "marvin-001"
    }
  ],
  "outputs": [
    {
      "type": "mqtt_command",
      "node_id": "empnode-entrance-001",
      "command": "dmx/set",
      "payload": { "room": "entrance", "effect": "thunder", "params": { "color": [255, 0, 0] } }
    }
  ]
}
```

This allows MARVIN game events to trigger empnode lighting effects — the core bridge purpose of EDD.

---

## 5. Use Cases

### UC-1: Character Registration via Admin UI

1. Admin enters character name, RFID tag hex ID, and skills in the EDD Blazor UI
2. EDD calls `SendMarvinRegisterAsync("marvin-001", new MarvinRegisterCommand { Type = "character", ... })`
3. MARVIN receives `cmd/rfid/register`, writes to `characterconfig.txt`, reloads, bumps version
4. MARVIN publishes `state/config_version` (retained) with new version
5. EDD receives updated version, confirms sync is current

### UC-2: Item Registration and Scan Lifecycle

1. EDD registers new item: `cmd/rfid/register` with `type: "item"`, `rfid`, `level`, `load`, `function`
2. MARVIN writes to `itemconfig.txt`, reloads, bumps version
3. Character scans item tag on MARVIN table
4. MARVIN publishes `state/rfid` with `action: "detected"`, `type: "item"`, `name`, `rfid`
5. If skill check passes, MARVIN starts a game (S9)
6. On success, MARVIN publishes `state/items` with `action: "connected"`
7. EDD can react: trigger lighting effects on empnode nodes, update world state

### UC-3: Table Status Control

1. Operator clicks "Disable table" in EDD admin UI
2. EDD publishes `cmd/table/status` with `{"status": "disabled"}`
3. MARVIN sets status, writes to `tableconfig.txt`, publishes `state/table` (retained)
4. LEDs go dark, RFID scanning blocked
5. Operator later re-enables: `{"status": "active"}`

### UC-4: Config Sync on Reconnect

1. MARVIN loses network, then reconnects
2. MARVIN publishes `state/config_version` (retained) — e.g. version 5
3. EDD has version 8 (admin registered characters while MARVIN was offline)
4. EDD sends `cmd/sync/offer` with version 8 + full character/item lists
5. MARVIN accepts (8 > 5), overwrites local config, reloads, sets version to 8

### UC-5: MARVIN-Triggered Room Lighting

1. Character overloads the MARVIN table (too many items)
2. MARVIN publishes `state/items` with `action: "overload"`
3. EDD's Sphinx service has a puzzle subscribed to `marvin_items_overload`
4. Puzzle fires output: `dmx/set` on all entrance empnodes with thunder effect
5. Room lights flash red for dramatic effect

### UC-6: Game Event Monitoring

1. Character starts a game on MARVIN (line/rune)
2. On failure: `state/game` with `{"event": "failure", "failures": 1, "limit": 3}`
3. On success: `state/game` with `{"event": "success", "elapsed_s": 42.5}`
4. EDD dashboard can display live game state
5. Sphinx can use success/failure to gate other puzzles

---

## 6. Misuse Scenarios and Defensive Handling

### M-1: Unknown RFID Tag

**Scenario:** Someone scans unregistered tag
**MARVIN behaviour:** Publishes `state/rfid` with `action: "unknown"`, `rfid: "<hex>"`
**EDD response:** Log for operator visibility. Optionally present in admin UI as "register this tag?" prompt.

### M-2: Duplicate Registration

**Scenario:** EDD sends `cmd/rfid/register` for an RFID that already exists
**MARVIN behaviour:** Updates the existing entry (name, skills, etc.) instead of creating a duplicate. Bumps config version.
**EDD response:** This is safe. No special handling needed — just be aware it's an update, not an error.

### M-3: Invalid Table Status

**Scenario:** EDD sends `cmd/table/status` with `{"status": "exploding"}`
**MARVIN behaviour:** Logs warning, ignores command. No state change.
**EDD defence:** Validate status value before sending. Only `active`, `broken`, `off`, `disabled` are accepted. Reject (or don't send) `overload` — that status is set internally by MARVIN.

### M-4: Invalid Well Size

**Scenario:** EDD sends `cmd/well/size` with `{"size": -10}` or `{"size": "abc"}`
**MARVIN behaviour:** Logs warning, ignores command.
**EDD defence:** Validate `size > 0` and `typeof(size) == int` before publishing. Reasonable range: 1-1000.

### M-5: Invalid Colour Value

**Scenario:** EDD sends `cmd/table/color/idle` with `{"color": [255]}` (wrong length) or `{"color": "red"}` (wrong type)
**MARVIN behaviour:** Logs warning, ignores command.
**EDD defence:** Validate `color` is array of exactly 3 integers, each 0-255.

### M-6: Malformed JSON

**Scenario:** EDD publishes garbage on a MARVIN cmd topic
**MARVIN behaviour:** Logs parse error, does not crash. Game loop continues.
**EDD defence:** Always serialize via `JsonSerializer` — never hand-craft JSON strings.

### M-7: Wrong Topic Prefix

**Scenario:** EDD accidentally publishes to `empnode/marvin-001/cmd/...` instead of `marvin/marvin-001/cmd/...`
**MARVIN behaviour:** Never receives it (subscribed only to `marvin/<id>/cmd/#`).
**EDD defence:** Ensure `PublishMarvinCommandAsync` uses `marvin/` prefix, not `empnode/`.

### M-8: Sync Version Conflict

**Scenario:** MARVIN and EDD both make changes simultaneously, creating divergent config
**MARVIN behaviour:** Strictly version-based — higher version wins. If EDD sends sync offer with lower version, MARVIN pushes its data back.
**EDD defence:** Always compare versions before sending sync offer. If MARVIN pushes, accept its data for the MARVIN-owned config. Consider a merge strategy for character/item registrations.

### M-9: Rapid-Fire Commands

**Scenario:** Multiple `cmd/rfid/register` messages arrive in quick succession
**MARVIN behaviour:** Processes sequentially (paho callback thread is single-threaded). Each writes full config via configparser. No locking — theoretically, rapid-fire could interleave reads and writes.
**EDD defence:** Space commands by at least 100 ms. If bulk-registering, use `sync/offer` instead of individual register commands.

### M-10: MARVIN Offline / Heartbeat Timeout

**Scenario:** MARVIN table loses power or network
**MARVIN behaviour:** Heartbeat messages stop. Retained `state/table` and `state/items` remain on broker.
**EDD detection:** If no heartbeat within 90 s (3x interval), mark MARVIN table as offline. Retained state is stale but still shows last known state. When MARVIN reconnects, it publishes fresh `state/config_version` — use this as a "back online" signal.

### M-11: Register with Missing Fields

**Scenario:** EDD sends `cmd/rfid/register` without the `rfid` field
**MARVIN behaviour:** Logs "missing 'rfid' field — ignoring". No state change.
**EDD defence:** Always validate required fields before publishing. Required: `type`, `rfid`. Character also needs `name`, `skills`. Item needs `name`, `level`, `load`, `function`.

### M-12: Config Version Rollback

**Scenario:** MARVIN restarts from an old backup config with a lower version
**MARVIN behaviour:** Publishes old version. EDD responds with sync offer containing newer data.
**EDD defence:** Always keep a complete character/item snapshot so the sync offer can fully restore MARVIN state.

---

## 7. Test Plan

### Unit Tests (Edd.Tests)

| ID | Test | Description |
|----|------|-------------|
| MT-1 | QueueMessageRouter routes MARVIN topics | Verify `marvin/test-001/state/rfid` routes to `QueueElement<MarvinRfidModel>` |
| MT-2 | QueueMessageRouter ignores empnode topics | Verify `empnode/node-abc/state/rfid` still routes to `QueueElement<VoidRfidModel>` |
| MT-3 | QueueMessageRouter handles unknown MARVIN subtopic | Verify `marvin/test-001/state/unknown` returns null |
| MT-4 | MarvinRfidModel deserialization | Verify all three payload variants (character, item, unknown) |
| MT-5 | MarvinItemsModel deserialization | Verify connected/disconnected/cleared/overload variants |
| MT-6 | MarvinGameModel deserialization | Verify failure and success variants |
| MT-7 | MarvinSyncPushModel deserialization | Verify full sync push with characters and items |
| MT-8 | HermesService dispatches MARVIN RFID | Mock EventBus, verify BusEvent published with correct type |
| MT-9 | HermesService dispatches MARVIN items | Verify all 4 action types produce correct EventBus events |
| MT-10 | HermesService dispatches MARVIN game | Verify failure/success produce correct EventBus events |
| MT-11 | HermesService dispatches MARVIN heartbeat | Verify logged, no crash on unknown nodeId |
| MT-12 | HermesService dispatches MARVIN config_version | Verify version stored/compared correctly |
| MT-13 | PublishMarvinCommandAsync uses correct topic prefix | Verify `marvin/` not `empnode/` |
| MT-14 | MarvinRegisterCommand serialization | Verify JSON matches MARVIN expected format |
| MT-15 | MarvinSyncOfferCommand serialization | Verify full sync offer with characters/items |

### Integration Tests

| ID | Test | Description |
|----|------|-------------|
| MI-1 | End-to-end RFID flow | Publish MARVIN RFID state → verify EventBus event arrives in Sphinx |
| MI-2 | End-to-end command flow | Send register command → verify arrives on MARVIN topic |
| MI-3 | Sync exchange (EDD newer) | Simulate config_version receive → verify sync offer sent |
| MI-4 | Sync exchange (MARVIN newer) | Send sync offer with lower version → verify sync push received |
| MI-5 | Retained message replay | Subscribe after MARVIN publishes items → verify retained arrives |
| MI-6 | Heartbeat monitoring | Publish MARVIN heartbeats → verify NodeRegistry or equivalent updates |
| MI-7 | Concurrent empnode + MARVIN | Both empnode and MARVIN messages flow simultaneously |

### Simulation Test (with MARVIN tools)

| ID | Test | Description |
|----|------|-------------|
| MS-1 | EDD stub round-trip | Start `tools/edd_stub.py`, connect to MARVIN sim, exercise all commands |
| MS-2 | Full lifecycle | Register character → scan → connect items → game → overload → reset |

---

## 8. Adding MARVIN to the Simulation Environment

### Prerequisites

- Python 3.10+ with `paho-mqtt>=2.0` and `amqtt` installed
- An MQTT broker (Mosquitto, amqtt, or EDD's built-in VoidBroker)

### Option A: Use EDD's Built-in Broker

EDD already runs an embedded MQTT broker (VoidBroker / MQTTnet). MARVIN can connect to the same broker:

1. Start EDD normally — VoidBroker starts on configured port (default 1883)
2. In MARVIN's `marvinconfig.txt`, set `[MQTT] broker = <EDD-host>` and `port = 1883`
3. Start MARVIN in simulation mode: `py -3 MARVIN.py`
4. MARVIN connects, publishes `state/config_version`, subscribes to `cmd/#`

### Option B: Standalone Broker + MARVIN Stub

For development without running the full MARVIN game:

```bash
# Terminal 1: Start broker
mosquitto -p 1883
# or: py -3 -m amqtt

# Terminal 2: Start MARVIN in sim mode
cd Marvin_MainController && py -3 MARVIN.py

# Terminal 3: Run EDD stub to send commands manually
cd Marvin_MainController && py -3 tools/edd_stub.py --broker localhost --node-id marvin-001
```

### Option C: Integration Test Harness

For automated testing, use the pattern from `tests/test_mqtt_integration.py`:

```python
# Spawns an amqtt broker in a daemon thread
# Creates a real _MQTT instance (MARVIN side)
# Creates an EddSubscriber (EDD side)
# Tests actual message flow through the broker
```

The `EddSubscriber` class in that file is a minimal EDD MQTT client that:
- Subscribes to `marvin/<id>/state/#`
- Collects messages with `wait_for(subtopic, timeout)`
- Publishes commands with `publish_cmd(subtopic, payload)`

This can be adapted into EDD's own integration test suite using NUnit/xUnit with an embedded amqtt or MQTTnet broker.

### Option D: Run empnode + MARVIN Side by Side

Both systems connect to the same broker and operate independently:

```bash
# Terminal 1: Start broker
mosquitto -p 1883

# Terminal 2: empnode server
cd empnode/tools && uv run empnode-tools --broker localhost server

# Terminal 3: empnode simulator (a physical node)
cd empnode/tools && uv run empnode-tools --broker localhost node --mac AA:BB:CC:DD:EE:FF

# Terminal 4: MARVIN sim
cd Marvin_MainController && py -3 MARVIN.py

# Terminal 5: Monitor all traffic
mosquitto_sub -h localhost -t "#" -v
```

You'll see `empnode/...` and `marvin/...` traffic on separate topic trees. EDD is the only system that needs to subscribe to both.

---

## 9. File Change Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `Edd.Shared/Models/Mqtt/MarvinRfidModel.cs` | New | MARVIN RFID event model |
| `Edd.Shared/Models/Mqtt/MarvinItemsModel.cs` | New | MARVIN items state model |
| `Edd.Shared/Models/Mqtt/MarvinGameModel.cs` | New | MARVIN game event model |
| `Edd.Shared/Models/Mqtt/MarvinTableModel.cs` | New | MARVIN table status model |
| `Edd.Shared/Models/Mqtt/MarvinHeartbeatModel.cs` | New | MARVIN heartbeat model |
| `Edd.Shared/Models/Mqtt/MarvinConfigVersionModel.cs` | New | MARVIN config version model |
| `Edd.Shared/Models/Mqtt/MarvinSyncPushModel.cs` | New | MARVIN sync push model (with character/item refs) |
| `Edd.Shared/Models/Mqtt/MarvinRegisterCommand.cs` | New | Register character/item command |
| `Edd.Shared/Models/Mqtt/MarvinTableStatusCommand.cs` | New | Set table status command |
| `Edd.Shared/Models/Mqtt/MarvinWellSizeCommand.cs` | New | Set well size command |
| `Edd.Shared/Models/Mqtt/MarvinColorCommand.cs` | New | Set idle colour command |
| `Edd.Shared/Models/Mqtt/MarvinGameColorCommand.cs` | New | Set game colour command |
| `Edd.Shared/Models/Mqtt/MarvinSyncOfferCommand.cs` | New | Sync offer command |
| `Edd.Shared/Models/QueueElement.cs` | Modify | Add MARVIN QueueType entries |
| `Edd.Shared/Models/QueueMessageRouter.cs` | Modify | Add `marvin/` topic routing |
| `Edd.Shared/Abstractions/IHermesService.cs` | Modify | Add MARVIN command publishing methods |
| `Edd.Core/Workers/EddWorker.cs` | Modify | Add `marvin/+/state/*` subscriptions |
| `Edd.Services.Hermes/HermesService.cs` | Modify | Add MARVIN dispatch arms + handler methods |
| `Edd.Shared/Models/Entities/MarvinTableEntity.cs` | New | Alexandria entity for MARVIN table state |
| `Edd.Shared/Models/Entities/MarvinItemEntity.cs` | New | Alexandria entity for MARVIN items (table-bound, with RFID) |
| `Alexandria.Tables/Tables/MarvinTable.sql` | New | Schema for MarvinTable |
| `Alexandria.Tables/Tables/MarvinItem.sql` | New | Schema for MarvinItem (designed for future Nexus alignment) |
| `Edd.Services.Alexandria/AlexandriaService.cs` | Modify | Add MarvinTable + MarvinItem schemas to StartAsync |

---

## 10. Implementation Order

1. **Models first** — create all MARVIN model classes (Step 1, 5). Zero risk, no behavioural change.
2. **Router** — extend QueueMessageRouter (Step 2). Messages start flowing but are dropped at dispatch.
3. **Subscriptions** — add MARVIN topics to EddWorker (Step 3). Messages now enter the channel.
4. **Handlers** — add dispatch arms to HermesService (Step 4). MARVIN events appear on EventBus.
5. **Commands** — add publish methods to HermesService (Step 5). EDD can now send commands.
6. **Alexandria** — persist characters (existing tables), items + table state (new tables), skill mapping (Step 6).
7. **Sphinx** — wire puzzle definitions that react to MARVIN events (Step 7). Last, requires game design input.

Each step is independently deployable and testable.
