# LegendsViewer API

REST API for the **LegendsViewer-Next** backend (ASP.NET Core). Used by the Vue frontend and available for external clients.

## Base URL

| Mode | URL |
|------|-----|
| Local / Docker | `http://localhost:15421` |
| Frontend (static) | `http://localhost:15422` |

All endpoints are under `/api/...`.

## Overview

- **Format:** JSON (`application/json`)
- **Enums:** serialized as strings
- **Authentication:** none
- **CORS:** any origin, method, and header allowed
- **Swagger UI:** Development only — [http://localhost:15421/swagger](http://localhost:15421/swagger)
- **OpenAPI JSON:** `http://localhost:15421/swagger/v1/swagger.json` (Development)

Generate TypeScript types from the schema:

```bash
cd LegendsViewer.Frontend/legends-viewer-frontend
npm run generate-api-schema
# → src/generated/api-schema.d.ts
```

---

## Pagination

Common query parameters for list endpoints:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pageNumber` | int | `1` | Page number (≥ 1) |
| `pageSize` | int | `10` | Page size (≥ 1) |
| `sortKey` | string? | — | Property to sort by |
| `sortOrder` | string? | — | Sort direction |

List responses use `PaginatedResponse<T>`:

```json
{
  "items": [],
  "totalCount": 0,
  "totalFilteredCount": 0,
  "pageSize": 10,
  "pageNumber": 1,
  "totalPages": 0
}
```

---

## Filters

### EventFilterDto

Used by `events`, `eventchart`, and `eventtypechart` (optional POST body):

```json
{
  "excludedEventTypes": ["hf died", "change hf state"]
}
```

### WorldObjectFilterDto

Used by `POST /api/{Type}`:

```json
{
  "searchTerm": "Urist",
  "filters": [
    {
      "propertyName": "Name",
      "operator": "Contains",
      "value": "Urist"
    }
  ]
}
```

`operator`: `Equals` | `NotEquals` | `Contains` | `GreaterThan` | `LessThan`

---

## Version

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/version` | Backend version |

**Response:** `{ "version": "1.0.0" }` — Development builds append `-dev`.

---

## World

Summary and events for the currently loaded world.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/World` | Current world summary (`WorldDto`) |
| `GET` / `POST` | `/api/World/events` | World events (pagination + `EventFilterDto`) |
| `GET` | `/api/World/eventcollections` | Event collections (pagination) |
| `GET` / `POST` | `/api/World/eventchart` | Chart: events per year |
| `GET` / `POST` | `/api/World/eventtypechart` | Chart: events by type |
| `GET` | `/api/World/records` | World records (`WorldRecordsDto`) |

For `events` / `eventchart` / `eventtypechart`, pass the filter in the body (POST). Query: `pageNumber`, `pageSize`, `sortKey`, `sortOrder` where applicable.

---

## Bookmark

Manage bookmarks and load legends exports.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/Bookmark` | List all bookmarks |
| `GET` | `/api/Bookmark/{encodedFilePath}` | Get a single bookmark |
| `DELETE` | `/api/Bookmark/{encodedFilePath}` | Delete a bookmark |
| `POST` | `/api/Bookmark/loadByFullPath` | Load a world by full file path |
| `POST` | `/api/Bookmark/loadByFolderAndFile` | Load a world by folder and file name |

Paths in the URL must be **URL-encoded** (`HttpUtility.UrlDecode`).

### loadByFullPath

**Body:** a JSON string with the absolute path to `*-legends.xml` or `*-legends_plus.xml`.

```http
POST /api/Bookmark/loadByFullPath
Content-Type: application/json

"/data/region1-00101-legends.xml"
```

Expected sibling files (by `regionId`):

- `{regionId}-legends.xml` (required)
- `{regionId}-legends_plus.xml`
- `{regionId}-world_history.txt`
- `{regionId}-world_sites_and_pops.txt`
- `{regionId}-world_map.bmp`

### DELETE

- `404` — bookmark not found
- `204` — fully deleted
- `200` — updated bookmark (other timestamps remain)
- Header `X-File-Missing: true` — file is missing on disk

---

## FileSystem

Host filesystem browser (for picking legends files).

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/FileSystem` | User home directory |
| `GET` | `/api/FileSystem/{encodedPath}` | Directory contents |
| `GET` | `/api/FileSystem/{encodedCurrentPath}/{encodedSubFolder}` | Navigate into a subdirectory |

Special path value: `mounts` — list of logical drives / mount points.

**Response** (`FilesAndSubdirectoriesDto`):

```json
{
  "currentDirectory": "/home/user",
  "parentDirectory": "/home",
  "subdirectories": ["Documents", "Downloads"],
  "files": ["region1-00101-legends.xml"]
}
```

`files` only includes `*-legends.xml`. Hidden Unix paths (starting with `.`) are omitted, except `.steam`.

---

## CreatureInfo

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/CreatureInfo` | List of creature types |

**Query:** `pageNumber`, `pageSize`, `search` (matches singular/plural name).

---

## World objects

Shared endpoint set for every world object type. Base path: `/api/{Type}`.

### Common endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/{Type}` | Filtered list (`WorldObjectFilterDto` in body) + pagination |
| `GET` | `/api/{Type}/{id}` | Object by id (includes `previousId` / `nextId`) |
| `GET` | `/api/{Type}/count` | Object count |
| `GET` / `POST` | `/api/{Type}/{id}/events` | Object events |
| `GET` | `/api/{Type}/{id}/eventcollections` | Object event collections |
| `GET` / `POST` | `/api/{Type}/{id}/eventchart` | Chart: events per year |
| `GET` / `POST` | `/api/{Type}/{id}/eventtypechart` | Chart: events by type |

### Types (`{Type}`)

| Controller | Description |
|------------|-------------|
| `DanceForm` | Dance forms |
| `MusicalForm` | Musical forms |
| `PoeticForm` | Poetic forms |
| `WrittenContent` | Written works |
| `Landmass` | Landmasses |
| `River` | Rivers |
| `Site` | Sites |
| `Region` | Regions |
| `UndergroundRegion` | Underground regions |
| `Artifact` | Artifacts |
| `Entity` | Entities (civilizations, organizations) |
| `HistoricalFigure` | Historical figures |
| `MountainPeak` | Mountain peaks |
| `Structure` | Structures |
| `Construction` | World constructions |
| `Era` | Eras |
| `War` | Wars |
| `Battle` | Battles |
| `Duel` | Duels |
| `Raid` | Raids |
| `SiteConquered` | Site conquests |
| `Insurrection` | Insurrections |
| `Persecution` | Persecutions |
| `Purge` | Purges |
| `Coup` | Coups |
| `BeastAttack` | Beast attacks |
| `Abduction` | Abductions |
| `Theft` | Thefts |
| `Procession` | Processions |
| `Performance` | Performances |
| `Journey` | Journeys |
| `Competition` | Competitions |
| `Ceremony` | Ceremonies |
| `Occasion` | Occasions |

### Entity — extra endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/Entity/civs` | Main civilizations |
| `GET` | `/api/Entity/{id}/monarchs` | Ruler timelines (`LeaderTimelineDto[]`) |

---

## WorldMap

Maps and object coordinates.

### Coordinates and warfare overlays

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/WorldMap/coordinates/{type}/{id}` | Object coordinates / bounding box |
| `GET` | `/api/WorldMap/warfare` | Wars and battles for the map |
| `GET` | `/api/WorldMap/war/{id}/overlay` | Overlay for a single war |
| `GET` | `/api/WorldMap/battle/{id}/marker` | Marker for a single battle |

**Query `warfare`:** `activeOnly` (bool, default `true`) — only unfinished wars/battles.

**`type` for coordinates:**  
`site` | `entity` | `region` | `undergroundregion` | `landmass` | `river` | `construction` | `mountainpeak` | `structure` | `artifact` | `war` | `battle`

### Map images

Response is `byte[]` (binary map image).

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/WorldMap/world/{size}` | Full world map |
| `GET` | `/api/WorldMap/underworld/{size}/{depth}` | Underworld map at depth |
| `GET` | `/api/WorldMap/landmass/{id}/{size}` | Landmass map |
| `GET` | `/api/WorldMap/mountainpeak/{id}/{size}` | Mountain peak map |
| `GET` | `/api/WorldMap/region/{id}/{size}` | Region map |
| `GET` | `/api/WorldMap/river/{id}/{size}` | River map |
| `GET` | `/api/WorldMap/construction/{id}/{size}` | Construction map |
| `GET` | `/api/WorldMap/undergroundregion/{id}/{size}` | Underground region map |
| `GET` | `/api/WorldMap/site/{id}/{size}` | Site map |
| `GET` | `/api/WorldMap/structure/{id}/{size}` | Structure map |
| `GET` | `/api/WorldMap/entity/{id}/{size}` | Entity map |
| `GET` | `/api/WorldMap/artifact/{id}/{size}` | Artifact map |
| `GET` | `/api/WorldMap/war/{id}/{size}` | War map |
| `GET` | `/api/WorldMap/battle/{id}/{size}` | Battle map |

### MapSize

| Value | Description |
|-------|-------------|
| `Default` | Medium tile size |
| `Small` | Minimum tile size |
| `Large` | Maximum tile size |

Example: `GET /api/WorldMap/site/42/Large`

---

## Status codes

| Code | When |
|------|------|
| `200` | Success |
| `204` | Success with no body (bookmark fully deleted) |
| `400` | Invalid parameters (pagination, path, file name) |
| `404` | Object / bookmark / map not found |
| `500` | XML parse error while loading a world |

---

## Examples

### Load a world (Docker, `./data` folder)

```bash
curl -X POST http://localhost:15421/api/Bookmark/loadByFullPath \
  -H "Content-Type: application/json" \
  -d '"/data/region1-00101-legends.xml"'
```

### List sites with search

```bash
curl -X POST "http://localhost:15421/api/Site?pageNumber=1&pageSize=20" \
  -H "Content-Type: application/json" \
  -d '{"searchTerm":"Mountainhome","filters":[]}'
```

### World summary

```bash
curl http://localhost:15421/api/World
```

### Version

```bash
curl http://localhost:15421/api/version
```
