# Acceptance examples and test coverage

These `.feature` files are **human-readable Gherkin examples** based on behavior already implemented in Frostbite. There are no step definitions or Gherkin runner: CI runs the Python tests with `python -m pytest -q`, not these files. They document examples rather than claiming the features were developed test-first.

| Examples | Existing supporting tests | Checked boundary |
| --- | --- | --- |
| [Runtime settings](runtime-settings.feature) | `tests/test_runtime_settings.py`, `tests/test_settings_api.py` | Unit checks; Playback Reheat update also uses FastAPI and disposable SQLite |
| [Playback reheat](playback-reheat.feature) | `tests/test_playback_reheat.py` | Unit decisions and playback-duration calculation |
| [Jellyfin webhooks](jellyfin-webhooks.feature) | `tests/test_schemas.py` | Unit-level payload normalization |
| [Temperature scoring](temperature-scoring.feature) | `tests/test_scorer.py` | Unit-level scoring |
| [Freeze protection](freeze-protection.feature) | `tests/test_freeze_policy.py`, `tests/test_prefetch_state.py`, `tests/test_schemas.py` | Unit decisions, fake playback-history lookup, response serialization |
| [Transfer safety](transfer-safety.feature) | `tests/test_transfer_gate.py`, `tests/test_freeze_policy.py`, `tests/test_transfer_manager.py` | Unit/preflight checks; VFS HTTP calls use a fake client |

The suite does not exercise the dashboard in a browser, production PostgreSQL, the full transfer worker, or live rclone/Jellyfin services. For an interview, describe it as a personal-project BDD documentation exercise with one API-and-database integration test and a broader unit suite.
