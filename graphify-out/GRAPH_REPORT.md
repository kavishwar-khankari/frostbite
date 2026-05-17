# Graph Report - frostbite  (2026-05-18)

## Corpus Check
- 62 files · ~30,593 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 409 nodes · 636 edges · 35 communities (25 shown, 10 thin omitted)
- Extraction: 83% EXTRACTED · 17% INFERRED · 0% AMBIGUOUS · INFERRED: 105 edges (avg confidence: 0.69)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `6e1cfff2`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 26|Community 26]]

## God Nodes (most connected - your core abstractions)
1. `req()` - 29 edges
2. `Frostbite` - 24 edges
3. `MediaItem` - 16 edges
4. `AGENTS.md — Frostbite` - 13 edges
5. `queue_transfer()` - 11 edges
6. `Transfer` - 10 edges
7. `BulkActionResult` - 9 edges
8. `JellyfinClient` - 9 edges
9. `broadcast()` - 8 edges
10. `sync_playback_from_reporting()` - 8 edges

## Surprising Connections (you probably didn't know these)
- `Teapot` --semantically_similar_to--> `Jellyfin`  [INFERRED] [semantically similar]
  docs/teapot-architecture.md → README.md
- `lifespan()` --calls--> `JellyfinClient`  [INFERRED]
  api/main.py → core/jellyfin_client.py
- `lifespan()` --calls--> `TransferManager`  [INFERRED]
  api/main.py → core/transfer_manager.py
- `trigger_scoring_sweep()` --calls--> `scoring_sweep()`  [INFERRED]
  api/routes/controls.py → core/scheduler.py
- `ItemsPage` --uses--> `MediaItem`  [INFERRED]
  api/routes/items.py → models/tables.py

## Hyperedges (group relationships)
- **Storage Tiering Pipeline** — frostbite_project, nas_storage, opendrive_storage, mergerfs_union, rclone_tool, rclone_rc_daemon, transfer_manager [EXTRACTED 0.95]
- **Scoring Pipeline** — frostbite_project, scorer_engine, temperature_scoring_model, prefetcher_engine, websocket_protocol, item_playback_stats_mv [EXTRACTED 0.90]
- **Jellyfin UI Enhancement Stack** — jellyfin_ui_modifications, websocket_protocol, frostbite_dashboard, frostbite_project [INFERRED 0.80]

## Communities (35 total, 10 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (46): bulkBumpTransfers(), bulkCancelTransfers(), bulkFreeze(), bulkReheat(), bulkRetryTransfers(), cancelTransfer(), freezeSeries(), getDashboard() (+38 more)

### Community 1 - "Community 1"
Cohesion: 0.09
Nodes (32): Base, BaseModel, Thin facade so deps.py can hold a typed singleton reference.     All actual log, TransferManager, DeclarativeBase, Base, DashboardStats, ItemStatusResponse (+24 more)

### Community 2 - "Community 2"
Cohesion: 0.09
Nodes (28): cleanup_stale_transfers(), APScheduler periodic tasks., Rescore all items and queue freeze/reheat candidates., Mark transfers that have been active for >2 hours as failed,     and cancel que, Record an aggregate snapshot for dashboard historical charts., Wrapper for scheduled runs — logs errors instead of crashing., Check non-eligible items individually against Tdarr and flip     tdarr_eligible, record_score_snapshot() (+20 more)

### Community 3 - "Community 3"
Cohesion: 0.1
Nodes (29): APScheduler, ArgoCD GitOps, Doppler Secrets, Emergency Freeze, FastAPI, Freeze Window, Frostbite Dashboard, Frostbite (+21 more)

### Community 4 - "Community 4"
Cohesion: 0.16
Nodes (19): _delete_nas_copy(), _execute_transfer(), _freeze_window_active(), _on_transfer_complete(), _poll_transfer(), _process_queue(), _quick_cloud_check(), rclone RC integration and transfer queue management.  Transfers are stored in (+11 more)

### Community 5 - "Community 5"
Cohesion: 0.15
Nodes (18): is_paused(), queue_transfer(), Insert a transfer record and return it. Caller must commit.     Returns None if, resume_transfers(), _bulk_action(), bulk_freeze(), bulk_reheat(), freeze_series() (+10 more)

### Community 6 - "Community 6"
Cohesion: 0.12
Nodes (14): lifespan(), get_all(), load_overrides(), DB-backed runtime settings overlay.  Stores overrides for UI-editable config k, Apply any DB-persisted overrides to the settings object at startup., Persist a setting override to DB and apply it in-memory immediately., Return current values of all editable settings., save_override() (+6 more)

### Community 7 - "Community 7"
Cohesion: 0.12
Nodes (16): AGENTS.md — Frostbite, Architecture, code:block1 (api/main.py          → FastAPI app, lifespan manages singlet), code:python (app.include_router(controls.router, prefix="/api")   # befor), code:python (normalized_id = event.jellyfin_id.replace("-", "")), Dependencies, graphify, Item ID format quirk (+8 more)

### Community 8 - "Community 8"
Cohesion: 0.15
Nodes (16): pause_all_transfers(), Stop all active rclone jobs and re-queue their transfers. Returns count., Tell rclone RC to stop a job. Best-effort — logs on failure., stop_rclone_job(), pause_all(), Stop all active rclone jobs and pause the transfer worker., bulk_bump_transfers(), bulk_cancel_transfers() (+8 more)

### Community 9 - "Community 9"
Cohesion: 0.19
Nodes (13): _extract_compact(), _fetch_path_map(), _parse_dt(), Library sync — syncs Jellyfin's item catalogue into media_items.  Strategy:, Sync Jellyfin catalogue → DB. No filesystem walk — NAS existence     check per, Pull only the fields we need from a Jellyfin item + source pair., Fetch all Jellyfin items page by page.     Returns {absolute_file_path: compact, _resolution_label() (+5 more)

### Community 10 - "Community 10"
Cohesion: 0.24
Nodes (4): JellyfinClient, Async Jellyfin REST API client., Search Jellyfin for an item whose path ends with rel_path., Fetch every Movie and Episode from Jellyfin with pagination (500/page).

### Community 11 - "Community 11"
Cohesion: 0.39
Nodes (10): _boost_temperature(), _get_or_create_item(), on_item_added(), on_playback_progress(), on_playback_start(), on_playback_stop(), _prefetch_next_episodes(), Predictive prefetch engine + playback event handlers.  Entry points called by (+2 more)

### Community 12 - "Community 12"
Cohesion: 0.27
Nodes (10): _get_cursor(), _make_query(), _parse_date(), Incremental playback sync from the Jellyfin Playback Reporting plugin.  The Pl, Build the SQL string to send to the plugin's submit_custom_query endpoint., Incremental sync from the Jellyfin Playback Reporting plugin.      full_reimpo, _set_cursor(), sync_playback_from_reporting() (+2 more)

### Community 13 - "Community 13"
Cohesion: 0.2
Nodes (5): Tdarr REST API client.  Tdarr tracks every file it knows about in its own data, Given a Tdarr file record, return whether Frostbite can manage it., Query Tdarr for a specific file by its absolute path (used as docID).         R, Fetch all files Tdarr considers done using the paginated status-tables, TdarrClient

### Community 14 - "Community 14"
Cohesion: 0.2
Nodes (9): get_storage_tier(), iter_media_files(), nas_free_bytes(), mergerfs xattr helpers and file discovery., Detect whether a file lives on NAS or cloud via mergerfs xattr., Yield (full_path, rel_path, size_bytes) for all media files under root., Return free bytes on the NAS mount., check_nas_space() (+1 more)

### Community 18 - "Community 18"
Cohesion: 0.6
Nodes (3): Layout(), NAV, useWebSocket()

## Knowledge Gaps
- **97 isolated node(s):** `Quick reference`, `code:block1 (api/main.py          → FastAPI app, lifespan manages singlet)`, `Settings quirks`, `code:python (app.include_router(controls.router, prefix="/api")   # befor)`, `code:python (normalized_id = event.jellyfin_id.replace("-", ""))` (+92 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **10 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MediaItem` connect `Community 1` to `Community 9`, `Community 2`, `Community 11`?**
  _High betweenness centrality (0.071) - this node is a cross-community bridge._
- **Why does `queue_transfer()` connect `Community 5` to `Community 1`, `Community 2`, `Community 4`, `Community 8`, `Community 11`, `Community 14`?**
  _High betweenness centrality (0.054) - this node is a cross-community bridge._
- **Why does `TransferManager` connect `Community 1` to `Community 4`, `Community 6`?**
  _High betweenness centrality (0.049) - this node is a cross-community bridge._
- **Are the 14 inferred relationships involving `MediaItem` (e.g. with `BulkActionRequest` and `BulkActionResponse`) actually correct?**
  _`MediaItem` has 14 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Quick reference`, `code:block1 (api/main.py          → FastAPI app, lifespan manages singlet)`, `Settings quirks` to the rest of the system?**
  _97 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.05 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.09 - nodes in this community are weakly interconnected._