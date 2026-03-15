from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://frostbite:Kavi%402003@192.168.0.14:5432/frostbite"

    # rclone RC endpoints
    rclone_rc_url: str = "http://127.0.0.1:5572"
    rclone_vfs_url: str = "http://127.0.0.1:5573"
    rclone_remote: str = "opendrive-crypt"

    # Paths
    media_root: str = "/mnt/merged/media"
    nas_root: str = "/mnt/nas/media"
    cloud_root: str = "/mnt/cloud/media"
    # Path prefix that Jellyfin uses internally for media files.
    # Jellyfin may mount media at a different path than the host (e.g. /media_2).
    # Used to translate Jellyfin paths → host NAS paths for tier detection.
    jellyfin_media_root: str = "/media_2"

    # Jellyfin
    jellyfin_url: str = "https://jellyfin.techtronics.top"
    jellyfin_api_key: str = ""  # injected via Doppler → JELLYFIN_API_KEY

    # Tdarr
    tdarr_url: str = "http://tdarr-server.tdarr.svc.cluster.local:8265"
    tdarr_api_key: str = ""  # optional — leave empty if Tdarr auth is disabled

    # Sonarr
    sonarr_url: str = "http://arr-stack-service.arr-stack.svc.cluster.local:8989"
    sonarr_api_key: str = ""  # injected via Doppler → SONARR_API_KEY

    # Radarr
    radarr_url: str = "http://arr-stack-service.arr-stack.svc.cluster.local:7878"
    radarr_api_key: str = ""  # injected via Doppler → RADARR_API_KEY

    # Scoring thresholds
    freeze_threshold: float = 25.0
    reheat_threshold: float = 60.0
    prefetch_boost: float = 40.0

    # Transfer settings
    max_concurrent_reheats: int = 2
    max_concurrent_freezes: int = 2
    freeze_window_start: int = 0   # Hour (IST)
    freeze_window_end: int = 8     # Hour (IST)

    # Space management
    emergency_freeze_threshold_gb: float = 15.0

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
