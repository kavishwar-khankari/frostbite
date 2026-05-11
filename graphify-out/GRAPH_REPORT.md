# Graph Report - .  (2026-05-11)

## Corpus Check
- Corpus is ~30,377 words - fits in a single context window. You may not need a graph.

## Summary
- 399 nodes · 632 edges · 34 communities (24 shown, 10 thin omitted)
- Extraction: 83% EXTRACTED · 17% INFERRED · 0% AMBIGUOUS · INFERRED: 106 edges (avg confidence: 0.69)
- Token cost: 12,849 input · 2,892 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Frontend Views & API Client|Frontend Views & API Client]]
- [[_COMMUNITY_Models & Serializers|Models & Serializers]]
- [[_COMMUNITY_Scheduler & Library Sync|Scheduler & Library Sync]]
- [[_COMMUNITY_Architecture Concepts|Architecture Concepts]]
- [[_COMMUNITY_Transfer Manager Core|Transfer Manager Core]]
- [[_COMMUNITY_Scoring Engine|Scoring Engine]]
- [[_COMMUNITY_Manual Controls|Manual Controls]]
- [[_COMMUNITY_Transfer Routes|Transfer Routes]]
- [[_COMMUNITY_Jellyfin Client|Jellyfin Client]]
- [[_COMMUNITY_Prefetcher & Webhook|Prefetcher & Webhook]]
- [[_COMMUNITY_Playback Import|Playback Import]]
- [[_COMMUNITY_Filesystem & Storage|Filesystem & Storage]]
- [[_COMMUNITY_Runtime Settings|Runtime Settings]]
- [[_COMMUNITY_Tdarr Client|Tdarr Client]]
- [[_COMMUNITY_Sonarr Client|Sonarr Client]]
- [[_COMMUNITY_Radarr Client|Radarr Client]]
- [[_COMMUNITY_Alembic Environment|Alembic Environment]]
- [[_COMMUNITY_Layout & Navigation|Layout & Navigation]]
- [[_COMMUNITY_Migration - Initial Schema|Migration - Initial Schema]]
- [[_COMMUNITY_Migration - Tdarr Eligibility|Migration - Tdarr Eligibility]]
- [[_COMMUNITY_Migration - App Settings|Migration - App Settings]]
- [[_COMMUNITY_Migration - Widen Storage Tier|Migration - Widen Storage Tier]]
- [[_COMMUNITY_Migration - Last Prefetch At|Migration - Last Prefetch At]]
- [[_COMMUNITY_Migration - Upload Blocked|Migration - Upload Blocked]]
- [[_COMMUNITY_Configuration|Configuration]]

## God Nodes (most connected - your core abstractions)
1. `Frostbite` - 31 edges
2. `req()` - 29 edges
3. `MediaItem` - 16 edges
4. `queue_transfer()` - 11 edges
5. `Transfer` - 10 edges
6. `BulkActionResult` - 9 edges
7. `JellyfinClient` - 9 edges
8. `broadcast()` - 8 edges
9. `sync_playback_from_reporting()` - 8 edges
10. `BulkActionResponse` - 7 edges

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

## Communities (34 total, 10 thin omitted)

### Community 0 - "Frontend Views & API Client"
Cohesion: 0.05
Nodes (46): bulkBumpTransfers(), bulkCancelTransfers(), bulkFreeze(), bulkReheat(), bulkRetryTransfers(), cancelTransfer(), freezeSeries(), getDashboard() (+38 more)

### Community 1 - "Models & Serializers"
Cohesion: 0.09
Nodes (33): Base, BaseModel, Thin facade so deps.py can hold a typed singleton reference.     All actual log, TransferManager, DeclarativeBase, Base, DashboardStats, ItemStatusResponse (+25 more)

### Community 2 - "Scheduler & Library Sync"
Cohesion: 0.07
Nodes (30): lifespan(), _extract_compact(), _fetch_path_map(), _parse_dt(), Library sync — syncs Jellyfin's item catalogue into media_items.  Strategy:, Sync Jellyfin catalogue → DB. No filesystem walk — NAS existence     check per, Pull only the fields we need from a Jellyfin item + source pair., Fetch all Jellyfin items page by page.     Returns {absolute_file_path: compact (+22 more)

### Community 3 - "Architecture Concepts"
Cohesion: 0.08
Nodes (35): Alembic Migrations, APScheduler, ArgoCD GitOps, Doppler Secrets, Emergency Freeze, FastAPI, Freeze Window, Frostbite Dashboard (+27 more)

### Community 4 - "Transfer Manager Core"
Cohesion: 0.16
Nodes (19): _delete_nas_copy(), _execute_transfer(), _freeze_window_active(), _on_transfer_complete(), _poll_transfer(), _process_queue(), _quick_cloud_check(), rclone RC integration and transfer queue management.  Transfers are stored in (+11 more)

### Community 5 - "Scoring Engine"
Cohesion: 0.16
Nodes (17): Rescore all items and queue freeze/reheat candidates., scoring_sweep(), calculate_temperature(), calculate_temperature_with_breakdown(), ItemMeta, _naive_utc(), PlaybackStats, Temperature scoring engine.  Score = float in [0.0, 100.0]. Items below FREEZ (+9 more)

### Community 6 - "Manual Controls"
Cohesion: 0.15
Nodes (18): is_paused(), queue_transfer(), Insert a transfer record and return it. Caller must commit.     Returns None if, resume_transfers(), _bulk_action(), bulk_freeze(), bulk_reheat(), freeze_series() (+10 more)

### Community 7 - "Transfer Routes"
Cohesion: 0.15
Nodes (16): pause_all_transfers(), Stop all active rclone jobs and re-queue their transfers. Returns count., Tell rclone RC to stop a job. Best-effort — logs on failure., stop_rclone_job(), pause_all(), Stop all active rclone jobs and pause the transfer worker., bulk_bump_transfers(), bulk_cancel_transfers() (+8 more)

### Community 8 - "Jellyfin Client"
Cohesion: 0.24
Nodes (4): JellyfinClient, Async Jellyfin REST API client., Search Jellyfin for an item whose path ends with rel_path., Fetch every Movie and Episode from Jellyfin with pagination (500/page).

### Community 9 - "Prefetcher & Webhook"
Cohesion: 0.39
Nodes (10): _boost_temperature(), _get_or_create_item(), on_item_added(), on_playback_progress(), on_playback_start(), on_playback_stop(), _prefetch_next_episodes(), Predictive prefetch engine + playback event handlers.  Entry points called by (+2 more)

### Community 10 - "Playback Import"
Cohesion: 0.27
Nodes (10): _get_cursor(), _make_query(), _parse_date(), Incremental playback sync from the Jellyfin Playback Reporting plugin.  The Pl, Build the SQL string to send to the plugin's submit_custom_query endpoint., Incremental sync from the Jellyfin Playback Reporting plugin.      full_reimpo, _set_cursor(), sync_playback_from_reporting() (+2 more)

### Community 11 - "Filesystem & Storage"
Cohesion: 0.2
Nodes (9): get_storage_tier(), iter_media_files(), nas_free_bytes(), mergerfs xattr helpers and file discovery., Detect whether a file lives on NAS or cloud via mergerfs xattr., Yield (full_path, rel_path, size_bytes) for all media files under root., Return free bytes on the NAS mount., check_nas_space() (+1 more)

### Community 12 - "Runtime Settings"
Cohesion: 0.24
Nodes (8): get_all(), DB-backed runtime settings overlay.  Stores overrides for UI-editable config k, Persist a setting override to DB and apply it in-memory immediately., Return current values of all editable settings., save_override(), get_settings(), SettingUpdate, update_setting()

### Community 13 - "Tdarr Client"
Cohesion: 0.2
Nodes (5): Tdarr REST API client.  Tdarr tracks every file it knows about in its own data, Given a Tdarr file record, return whether Frostbite can manage it., Query Tdarr for a specific file by its absolute path (used as docID).         R, Fetch all files Tdarr considers done using the paginated status-tables, TdarrClient

### Community 17 - "Layout & Navigation"
Cohesion: 0.6
Nodes (3): Layout(), NAV, useWebSocket()

## Knowledge Gaps
- **89 isolated node(s):** `Initial schema — all tables + item_playback_stats materialized view  Revision`, `Tdarr eligibility columns — now included in 0001, this migration is a no-op.`, `App settings table for UI-editable runtime configuration.  Revision ID: 0003`, `Widen storage_tier and transfer_direction columns from VARCHAR(10) to VARCHAR(20`, `Add last_prefetch_at to media_items for prefetch cooldown.  Revision ID: 0005` (+84 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **10 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MediaItem` connect `Models & Serializers` to `Prefetcher & Webhook`, `Scheduler & Library Sync`, `Scoring Engine`?**
  _High betweenness centrality (0.103) - this node is a cross-community bridge._
- **Why does `SQLAlchemy ORM` connect `Models & Serializers` to `Architecture Concepts`, `Transfer Routes`?**
  _High betweenness centrality (0.102) - this node is a cross-community bridge._
- **Why does `Frostbite` connect `Architecture Concepts` to `Models & Serializers`?**
  _High betweenness centrality (0.102) - this node is a cross-community bridge._
- **Are the 14 inferred relationships involving `MediaItem` (e.g. with `BulkActionRequest` and `BulkActionResponse`) actually correct?**
  _`MediaItem` has 14 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `queue_transfer()` (e.g. with `_queue_manual()` and `_series_action()`) actually correct?**
  _`queue_transfer()` has 9 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Initial schema — all tables + item_playback_stats materialized view  Revision`, `Tdarr eligibility columns — now included in 0001, this migration is a no-op.`, `App settings table for UI-editable runtime configuration.  Revision ID: 0003` to the rest of the system?**
  _89 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Frontend Views & API Client` be split into smaller, more focused modules?**
  _Cohesion score 0.05 - nodes in this community are weakly interconnected._