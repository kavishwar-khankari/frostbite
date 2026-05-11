# Graph Report - frostbite  (2026-05-11)

## Corpus Check
- 62 files · ~30,486 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 526 nodes · 754 edges · 39 communities (28 shown, 11 thin omitted)
- Extraction: 86% EXTRACTED · 14% INFERRED · 0% AMBIGUOUS · INFERRED: 106 edges (avg confidence: 0.69)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `3f568680`
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
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]

## God Nodes (most connected - your core abstractions)
1. `Frostbite` - 31 edges
2. `req()` - 29 edges
3. `MediaItem` - 16 edges
4. `Teapot — Intelligent Tiered Storage for Jellyfin` - 14 edges
5. `queue_transfer()` - 11 edges
6. `AGENTS.md — Frostbite` - 11 edges
7. `Transfer` - 10 edges
8. `5. Layer 2 — Frostbite Engine (Backend)` - 10 edges
9. `JellyfinClient` - 9 edges
10. `BulkActionResult` - 9 edges

## Surprising Connections (you probably didn't know these)
- `Teapot` --semantically_similar_to--> `Jellyfin`  [INFERRED] [semantically similar]
  docs/teapot-architecture.md → README.md
- `run_library_sync()` --calls--> `MediaItem`  [INFERRED]
  core/library_sync.py → models/tables.py
- `lifespan()` --calls--> `TransferManager`  [INFERRED]
  api/main.py → core/transfer_manager.py
- `queue_transfer()` --calls--> `Transfer`  [INFERRED]
  core/transfer_manager.py → models/tables.py
- `save_override()` --calls--> `AppSettings`  [INFERRED]
  core/runtime_settings.py → models/tables.py

## Hyperedges (group relationships)
- **Storage Tiering Pipeline** — frostbite_project, nas_storage, opendrive_storage, mergerfs_union, rclone_tool, rclone_rc_daemon, transfer_manager [EXTRACTED 0.95]
- **Scoring Pipeline** — frostbite_project, scorer_engine, temperature_scoring_model, prefetcher_engine, websocket_protocol, item_playback_stats_mv [EXTRACTED 0.90]
- **Jellyfin UI Enhancement Stack** — jellyfin_ui_modifications, websocket_protocol, frostbite_dashboard, frostbite_project [INFERRED 0.80]

## Communities (39 total, 11 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (46): bulkBumpTransfers(), bulkCancelTransfers(), bulkFreeze(), bulkReheat(), bulkRetryTransfers(), cancelTransfer(), freezeSeries(), getDashboard() (+38 more)

### Community 1 - "Community 1"
Cohesion: 0.06
Nodes (50): Base, BaseModel, Rescore all items and queue freeze/reheat candidates., scoring_sweep(), calculate_temperature(), calculate_temperature_with_breakdown(), ItemMeta, _naive_utc() (+42 more)

### Community 2 - "Community 2"
Cohesion: 0.05
Nodes (31): lifespan(), get_storage_tier(), iter_media_files(), nas_free_bytes(), mergerfs xattr helpers and file discovery., Detect whether a file lives on NAS or cloud via mergerfs xattr., Yield (full_path, rel_path, size_bytes) for all media files under root., Return free bytes on the NAS mount. (+23 more)

### Community 3 - "Community 3"
Cohesion: 0.05
Nodes (39): 10.1 Failure Modes, 10.2 Monitoring, 10.3 Backup Strategy, 10.4 Performance Estimates, 10. Operational Considerations, 11. Implementation Phases, 12. Open Questions & Future Ideas, 1. Vision (+31 more)

### Community 4 - "Community 4"
Cohesion: 0.08
Nodes (34): is_paused(), pause_all_transfers(), queue_transfer(), Stop all active rclone jobs and re-queue their transfers. Returns count., Insert a transfer record and return it. Caller must commit.     Returns None if, Tell rclone RC to stop a job. Best-effort — logs on failure., resume_transfers(), stop_rclone_job() (+26 more)

### Community 5 - "Community 5"
Cohesion: 0.08
Nodes (35): Alembic Migrations, APScheduler, ArgoCD GitOps, Doppler Secrets, Emergency Freeze, FastAPI, Freeze Window, Frostbite Dashboard (+27 more)

### Community 6 - "Community 6"
Cohesion: 0.16
Nodes (19): _delete_nas_copy(), _execute_transfer(), _freeze_window_active(), _on_transfer_complete(), _poll_transfer(), _process_queue(), _quick_cloud_check(), rclone RC integration and transfer queue management.  Transfers are stored in Po (+11 more)

### Community 7 - "Community 7"
Cohesion: 0.11
Nodes (18): 5.1 Technology Stack, 5.2 Application Structure, 5.3 PostgreSQL Schema, 5.4 Temperature Scoring Model, 5.5 Predictive Prefetch Engine, 5.6 Transfer Manager, 5.7 NAS Space Monitor, 5.8 Jellyfin Webhook Integration (+10 more)

### Community 8 - "Community 8"
Cohesion: 0.13
Nodes (14): AGENTS.md — Frostbite, Architecture, code:block1 (api/main.py          → FastAPI app, lifespan manages singlet), code:python (app.include_router(controls.router, prefix="/api")   # befor), code:python (normalized_id = event.jellyfin_id.replace("-", "")), Dependencies, graphify, Item ID format quirk (+6 more)

### Community 9 - "Community 9"
Cohesion: 0.19
Nodes (13): _extract_compact(), _fetch_path_map(), _parse_dt(), Library sync — syncs Jellyfin's item catalogue into media_items.  Strategy:   1., Sync Jellyfin catalogue → DB. No filesystem walk — NAS existence     check per i, Pull only the fields we need from a Jellyfin item + source pair., Fetch all Jellyfin items page by page.     Returns {absolute_file_path: compact_, _resolution_label() (+5 more)

### Community 10 - "Community 10"
Cohesion: 0.14
Nodes (12): Architecture, Cloud remote, Deployment, Incidents, Infrastructure (already running, not in this repo), Key endpoints on the VM, Project: Frostbite — Intelligent Tiered Storage Engine for Jellyfin, Reading Reddit threads (+4 more)

### Community 11 - "Community 11"
Cohesion: 0.14
Nodes (14): 4.1 Mount Hierarchy, 4.2 SMB NAS Mount, 4.3 rclone Mount (Cloud Read Path), 4.4 rclone RC Daemon (Cloud Write Path), 4.5 mergerfs Union Mount, 4.6 hostPath Exposure to Kubernetes, 4. Layer 1 — VM Storage Infrastructure, code:block2 (# Boot order:) (+6 more)

### Community 12 - "Community 12"
Cohesion: 0.39
Nodes (10): _boost_temperature(), _get_or_create_item(), on_item_added(), on_playback_progress(), on_playback_start(), on_playback_stop(), _prefetch_next_episodes(), Predictive prefetch engine + playback event handlers.  Entry points called by th (+2 more)

### Community 13 - "Community 13"
Cohesion: 0.24
Nodes (4): JellyfinClient, Async Jellyfin REST API client., Search Jellyfin for an item whose path ends with rel_path., Fetch every Movie and Episode from Jellyfin with pagination (500/page).

### Community 14 - "Community 14"
Cohesion: 0.17
Nodes (11): API, Architecture, code:block1 (NAS (hot tier) ──── score drops below 25 ────► Cloud (cold t), code:block2 (Jellyfin ──webhook──► Frostbite API ◄── React Dashboard (SPA), Configuration, Deployment, Features, Frostbite (+3 more)

### Community 15 - "Community 15"
Cohesion: 0.27
Nodes (10): _get_cursor(), _make_query(), _parse_date(), Incremental playback sync from the Jellyfin Playback Reporting plugin.  The Play, Build the SQL string to send to the plugin's submit_custom_query endpoint., Incremental sync from the Jellyfin Playback Reporting plugin.      full_reimport, _set_cursor(), sync_playback_from_reporting() (+2 more)

### Community 16 - "Community 16"
Cohesion: 0.18
Nodes (11): 8.1 Namespace and Secrets, 8.2 PostgreSQL, 8.3 Frostbite Engine, 8.4 Services and Ingress, 8.5 Git Repository Structure, 8. Kubernetes Manifests Overview, code:yaml (# frostbite/namespace.yaml), code:yaml (# frostbite/postgresql.yaml) (+3 more)

### Community 17 - "Community 17"
Cohesion: 0.24
Nodes (8): get_all(), DB-backed runtime settings overlay.  Stores overrides for UI-editable config key, Persist a setting override to DB and apply it in-memory immediately., Return current values of all editable settings., save_override(), get_settings(), SettingUpdate, update_setting()

### Community 20 - "Community 20"
Cohesion: 0.6
Nodes (3): Layout(), NAV, useWebSocket()

## Knowledge Gaps
- **166 isolated node(s):** `Library sync — syncs Jellyfin's item catalogue into media_items.  Strategy:   1.`, `Pull only the fields we need from a Jellyfin item + source pair.`, `Fetch all Jellyfin items page by page.     Returns {absolute_file_path: compact_`, `Sync Jellyfin catalogue → DB. No filesystem walk — NAS existence     check per i`, `rclone RC integration and transfer queue management.  Transfers are stored in Po` (+161 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **11 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MediaItem` connect `Community 1` to `Community 9`, `Community 12`?**
  _High betweenness centrality (0.059) - this node is a cross-community bridge._
- **Why does `SQLAlchemy ORM` connect `Community 1` to `Community 4`, `Community 5`?**
  _High betweenness centrality (0.059) - this node is a cross-community bridge._
- **Why does `Frostbite` connect `Community 5` to `Community 1`?**
  _High betweenness centrality (0.058) - this node is a cross-community bridge._
- **Are the 14 inferred relationships involving `MediaItem` (e.g. with `TransferManager` and `Base`) actually correct?**
  _`MediaItem` has 14 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Library sync — syncs Jellyfin's item catalogue into media_items.  Strategy:   1.`, `Pull only the fields we need from a Jellyfin item + source pair.`, `Fetch all Jellyfin items page by page.     Returns {absolute_file_path: compact_` to the rest of the system?**
  _166 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.05 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.06 - nodes in this community are weakly interconnected._