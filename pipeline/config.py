from __future__ import annotations

import os
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import env as _env  # noqa: F401 - loads .env/.env.local once
from .storage import PROJECT_ROOT, resolve_project_path


class ConfigurationError(ValueError):
    """Raised when local configuration cannot be parsed or is inconsistent."""


class SettingsModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ServerSettings(SettingsModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1, le=65535)
    studio_host: str = "127.0.0.1"
    studio_port: int = Field(default=5173, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["human", "json"] = "human"


class StorageSettings(SettingsModel):
    project_root: Path = PROJECT_ROOT
    database_path: Path = Path(".synthpost/synthpost.sqlite3")


class LLMSettings(SettingsModel):
    provider: Literal[
        "hermes",
        "codex",
        "groq",
        "gemini",
        "sarvam",
        "hosted_fallback",
        "groq_then_gemini",
        "mock",
    ] = "groq"
    request_timeout_seconds: float = Field(default=45.0, gt=0)
    max_retries: int = Field(default=2, ge=0, le=10)
    save_debug: bool = False
    hermes_binary: str = "hermes"
    hermes_model: str | None = None
    hermes_toolsets: str = "web"
    hermes_timeout_seconds: float = Field(default=900.0, gt=0)
    codex_binary: str = "codex"
    codex_sandbox_binary: str = "/usr/bin/sandbox-exec"
    codex_model: str = "gpt-5.6-sol"
    codex_reasoning_effort: Literal["low", "medium", "high", "xhigh"] = "medium"
    codex_timeout_seconds: float = Field(default=180.0, gt=0)
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash"
    gemini_temperature: float = Field(default=0.2, ge=0, le=2)
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"
    groq_temperature: float = Field(default=0.2, ge=0, le=2)
    groq_max_completion_tokens: int = Field(default=2300, ge=128)
    sarvam_api_key: str | None = None
    sarvam_model: str = "sarvam-105b"
    sarvam_temperature: float = Field(default=0.2, ge=0, le=2)
    sarvam_max_completion_tokens: int = Field(default=2300, ge=128)

    def provider_problem(self) -> str | None:
        if self.provider == "hermes":
            requested_toolsets = {
                value.strip().casefold()
                for value in self.hermes_toolsets.split(",")
                if value.strip()
            }
            if requested_toolsets != {"web"}:
                return (
                    "SYNTHPOST_HERMES_TOOLSETS must be exactly web for unattended runs"
                )
            if not shutil.which(self.hermes_binary):
                return (
                    f"Hermes Agent CLI not found or not executable at {self.hermes_binary!r}; "
                    "install Hermes or set SYNTHPOST_HERMES_BINARY"
                )
        if self.provider == "codex":
            if not shutil.which(self.codex_binary):
                return (
                    f"Codex CLI not found or not executable at {self.codex_binary!r}; "
                    "install Codex or set SYNTHPOST_CODEX_BINARY"
                )
            if not shutil.which(self.codex_sandbox_binary):
                return (
                    "macOS sandbox-exec is required for the Codex provider; set "
                    "SYNTHPOST_CODEX_SANDBOX_BINARY to its executable path"
                )
        if self.provider == "gemini" and not self.gemini_api_key:
            return "GEMINI_API_KEY is required when SYNTHPOST_LLM_PROVIDER=gemini"
        if self.provider == "groq" and not self.groq_api_key:
            return "GROQ_API_KEY is required when SYNTHPOST_LLM_PROVIDER=groq"
        if self.provider == "sarvam" and not self.sarvam_api_key:
            return "SARVAM_API_KEY is required when SYNTHPOST_LLM_PROVIDER=sarvam"
        if self.provider in {"hosted_fallback", "groq_then_gemini"}:
            missing = [
                name
                for name, value in (
                    ("GROQ_API_KEY", self.groq_api_key),
                    ("GEMINI_API_KEY", self.gemini_api_key),
                )
                if not value
            ]
            if missing:
                return f"{', '.join(missing)} required for hosted_fallback"
        return None


class SearchSettings(SettingsModel):
    searxng_url: str | None = None
    language: str = "en"
    safesearch: int = Field(default=1, ge=0, le=2)
    timeout_seconds: float = Field(default=20.0, gt=0)
    retries: int = Field(default=2, ge=1, le=10)
    api_key: str | None = None
    news_results: int = Field(default=12, ge=1)
    news_time_range: str = "month"
    research_max_documents: int = Field(default=6, ge=1)
    research_claims_per_document: int = Field(default=8, ge=1)


class DiscoverySettings(SettingsModel):
    """Controls for the actively curated story inbox."""

    max_candidate_age_hours: float = Field(default=24.0, gt=0)


class VisualSettings(SettingsModel):
    ai_query_planning: bool = True
    include_leads: bool = True
    disable_web_visuals: bool = False
    generate_fallback_visuals: bool = True
    download_videos: bool = True
    visual_max_queries: int = Field(default=12, ge=1)
    image_results_per_query: int = Field(default=3, ge=0)
    video_results_per_query: int = Field(default=2, ge=0)
    video_download_limit: int = Field(default=6, ge=0)
    video_clip_seconds: int = Field(default=45, ge=1)
    video_max_duration_seconds: int = Field(default=900, ge=1)
    video_timeout_seconds: float = Field(default=300.0, gt=0)
    searxng_socket_timeout_seconds: float = Field(default=15.0, gt=0)
    enforce_broadcast_fit: bool = True
    min_width: int = Field(default=1280, ge=1)
    min_height: int = Field(default=720, ge=1)
    aspect_tolerance: float = Field(default=0.20, gt=0)
    image_aspect_tolerance: float = Field(default=0.30, gt=0)
    download_timeout_seconds: float = Field(default=30.0, gt=0)
    download_max_bytes: int = Field(default=104_857_600, ge=1)
    yt_dlp_binary: str = "yt-dlp"
    tesseract_binary: str = "tesseract"
    approved_video_channel_ids: tuple[str, ...] = ()
    approved_video_source_names: tuple[str, ...] = ()
    blocked_video_source_names: tuple[str, ...] = ()


class AvatarSettings(SettingsModel):
    engine_path: Path = Path("avatar-engine")
    python_path: Path | None = None
    renderer: str | None = None
    asset_path: str = "assets/avatars/synthpost_anchor_v1/anchor.glb"
    metadata_path: str = "assets/avatars/synthpost_anchor_v1/avatar.json"
    words_per_minute: float = Field(default=145.0, gt=0)
    browser_timeout_padding_seconds: float = Field(default=900.0, ge=0)


class NarrationSettings(SettingsModel):
    """Local dots.tts synthesis and voice-cloning configuration."""

    python_path: Path = Path(".venv-dots-tts/bin/python")
    model_path: Path = Path(".cache/dots-tts/int4")
    model_name: str = "dots.tts-soar-mlx-int4"
    voice_id: str = "anchor"
    voice_profile_path: Path | None = None
    reference_audio_path: Path | None = None
    reference_text: str | None = None
    language_code: str = "EN"
    voice_speed: float = Field(default=1.0, gt=0)
    num_steps: int | None = Field(default=None, ge=1, le=64)
    guidance_scale: float = Field(default=1.2, ge=0, le=10)
    speaker_scale: float = Field(default=1.5, gt=0, le=10)
    seed: int = Field(default=42, ge=0)
    max_generate_length: int = Field(default=500, ge=16, le=4096)
    narration_beat_pause_ms: int = Field(default=80, ge=0, le=2000)
    narration_section_pause_ms: int = Field(default=220, ge=0, le=5000)


class RenderSettings(SettingsModel):
    remotion_path: Path = Path("compositor/remotion_renderer")
    remotion_concurrency: int = Field(default=4, ge=1, le=64)
    ffmpeg_binary: str = "ffmpeg"
    profile: Literal["preview", "production", "final_master"] = "production"
    codec: str = "h264"
    preview_frame: int = Field(default=24, ge=0)
    experimental_source_audio: bool = False


class JobSettings(SettingsModel):
    editorial_workers: int = Field(default=3, ge=1, le=32)
    media_workers: int = Field(default=3, ge=1, le=32)
    render_workers: int = Field(default=3, ge=1, le=16)
    editorial_max_attempts: int = Field(default=3, ge=1)
    media_max_attempts: int = Field(default=3, ge=1)
    render_max_attempts: int = Field(default=2, ge=1)
    retry_base_seconds: float = Field(default=15.0, ge=0)
    retry_max_seconds: float = Field(default=900.0, ge=0)
    heartbeat_seconds: float = Field(default=5.0, ge=1)

    @model_validator(mode="after")
    def validate_retry_window(self) -> "JobSettings":
        if self.retry_max_seconds < self.retry_base_seconds:
            raise ValueError("retry_max_seconds must be >= retry_base_seconds")
        return self

    def workers_for(self, lane: str) -> int:
        """Return configured process capacity for a queue lane."""

        counts = {
            "editorial": self.editorial_workers,
            "media": self.media_workers,
            "render": self.render_workers,
        }
        try:
            return counts[lane]
        except KeyError as exc:
            raise ValueError(f"Unknown queue lane: {lane}") from exc


class SynthPostSettings(SettingsModel):
    server: ServerSettings
    storage: StorageSettings
    llm: LLMSettings
    search: SearchSettings
    discovery: DiscoverySettings
    visuals: VisualSettings
    avatar: AvatarSettings
    narration: NarrationSettings
    render: RenderSettings
    jobs: JobSettings


class _Reader:
    def __init__(self, values: Mapping[str, str]):
        self.values = values

    def text(
        self, name: str, default: str | None = None, *, aliases: tuple[str, ...] = ()
    ) -> str | None:
        for key in (name, *aliases):
            value = self.values.get(key)
            if value not in (None, ""):
                return str(value)
        return default

    def boolean(self, name: str, default: bool) -> bool:
        value = self.text(name)
        if value is None:
            return default
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        raise ConfigurationError(
            f"Environment variable {name} must be a boolean (1/0, true/false, yes/no, on/off)."
        )

    def integer(self, name: str, default: int) -> int:
        value = self.text(name)
        try:
            return default if value is None else int(value)
        except ValueError as exc:
            raise ConfigurationError(
                f"Environment variable {name} must be an integer."
            ) from exc

    def number(self, name: str, default: float) -> float:
        value = self.text(name)
        try:
            return default if value is None else float(value)
        except ValueError as exc:
            raise ConfigurationError(
                f"Environment variable {name} must be a number."
            ) from exc

    def csv(self, name: str, *, lowercase: bool = True) -> tuple[str, ...]:
        value = self.text(name, "") or ""
        return tuple(
            dict.fromkeys(
                (
                    item.strip().lower() if lowercase else item.strip()
                    for item in value.split(",")
                    if item.strip()
                )
            )
        )


def load_settings(values: Mapping[str, str] | None = None) -> SynthPostSettings:
    """Parse a complete immutable settings snapshot from environment values."""

    r = _Reader(os.environ if values is None else values)
    try:
        return SynthPostSettings(
            server=ServerSettings(
                host=r.text("SYNTHPOST_SERVER_HOST", "127.0.0.1"),
                port=r.integer("SYNTHPOST_SERVER_PORT", 8765),
                studio_host=r.text("SYNTHPOST_STUDIO_HOST", "127.0.0.1"),
                studio_port=r.integer("SYNTHPOST_STUDIO_PORT", 5173),
                log_level=(r.text("SYNTHPOST_LOG_LEVEL", "INFO") or "INFO").upper(),
                log_format=(r.text("SYNTHPOST_LOG_FORMAT", "human") or "human").lower(),
            ),
            storage=StorageSettings(
                database_path=Path(
                    r.text("SYNTHPOST_DB_PATH", ".synthpost/synthpost.sqlite3")
                    or ".synthpost/synthpost.sqlite3"
                )
            ),
            llm=LLMSettings(
                provider=(r.text("SYNTHPOST_LLM_PROVIDER", "groq") or "groq").lower(),
                request_timeout_seconds=r.number(
                    "SYNTHPOST_LLM_REQUEST_TIMEOUT_SECONDS", 45.0
                ),
                max_retries=r.integer("SYNTHPOST_LLM_MAX_RETRIES", 2),
                save_debug=r.boolean("SYNTHPOST_SAVE_LLM_DEBUG", False),
                hermes_binary=r.text("SYNTHPOST_HERMES_BINARY", "hermes"),
                hermes_model=r.text("SYNTHPOST_HERMES_MODEL"),
                hermes_toolsets=r.text("SYNTHPOST_HERMES_TOOLSETS", "web"),
                hermes_timeout_seconds=r.number(
                    "SYNTHPOST_HERMES_TIMEOUT_SECONDS", 900.0
                ),
                codex_binary=r.text("SYNTHPOST_CODEX_BINARY", "codex"),
                codex_sandbox_binary=r.text(
                    "SYNTHPOST_CODEX_SANDBOX_BINARY", "/usr/bin/sandbox-exec"
                ),
                codex_model=r.text("SYNTHPOST_CODEX_MODEL", "gpt-5.6-sol"),
                codex_reasoning_effort=(
                    r.text("SYNTHPOST_CODEX_REASONING_EFFORT", "medium") or "medium"
                ).lower(),
                codex_timeout_seconds=r.number(
                    "SYNTHPOST_CODEX_TIMEOUT_SECONDS", 180.0
                ),
                gemini_api_key=r.text("GEMINI_API_KEY"),
                gemini_model=r.text("SYNTHPOST_GEMINI_MODEL", "gemini-3.5-flash"),
                gemini_temperature=r.number("SYNTHPOST_GEMINI_TEMPERATURE", 0.2),
                groq_api_key=r.text("GROQ_API_KEY"),
                groq_model=r.text("SYNTHPOST_GROQ_MODEL", "openai/gpt-oss-120b"),
                groq_temperature=r.number("SYNTHPOST_GROQ_TEMPERATURE", 0.2),
                groq_max_completion_tokens=r.integer(
                    "SYNTHPOST_GROQ_MAX_COMPLETION_TOKENS", 2300
                ),
                sarvam_api_key=r.text("SARVAM_API_KEY"),
                sarvam_model=r.text("SYNTHPOST_SARVAM_MODEL", "sarvam-105b"),
                sarvam_temperature=r.number("SYNTHPOST_SARVAM_TEMPERATURE", 0.2),
                sarvam_max_completion_tokens=r.integer(
                    "SYNTHPOST_SARVAM_MAX_COMPLETION_TOKENS", 2300
                ),
            ),
            search=SearchSettings(
                searxng_url=r.text("SYNTHPOST_SEARXNG_URL"),
                language=r.text("SYNTHPOST_SEARXNG_LANGUAGE", "en"),
                safesearch=r.integer("SYNTHPOST_SEARXNG_SAFESEARCH", 1),
                timeout_seconds=r.number("SYNTHPOST_SEARXNG_TIMEOUT", 20.0),
                retries=r.integer("SYNTHPOST_SEARXNG_RETRIES", 2),
                api_key=r.text("SYNTHPOST_SEARXNG_API_KEY"),
                news_results=r.integer("SYNTHPOST_SEARXNG_NEWS_RESULTS", 12),
                news_time_range=r.text("SYNTHPOST_SEARXNG_NEWS_TIME_RANGE", "month"),
                research_max_documents=r.integer(
                    "SYNTHPOST_RESEARCH_MAX_DOCUMENTS", 6
                ),
                research_claims_per_document=r.integer(
                    "SYNTHPOST_RESEARCH_CLAIMS_PER_DOCUMENT", 8
                ),
            ),
            discovery=DiscoverySettings(
                max_candidate_age_hours=r.number(
                    "SYNTHPOST_DISCOVERY_MAX_AGE_HOURS", 24.0
                ),
            ),
            visuals=VisualSettings(
                ai_query_planning=r.boolean("SYNTHPOST_AI_VISUAL_QUERY_PLANNING", True),
                include_leads=r.boolean("SYNTHPOST_INCLUDE_VISUAL_LEADS", True),
                disable_web_visuals=r.boolean(
                    "SYNTHPOST_DISABLE_WEB_VISUALS", False
                ),
                generate_fallback_visuals=r.boolean(
                    "SYNTHPOST_GENERATE_FALLBACK_VISUALS", True
                ),
                download_videos=r.boolean("SYNTHPOST_SEARXNG_DOWNLOAD_VIDEOS", True),
                visual_max_queries=r.integer(
                    "SYNTHPOST_SEARXNG_VISUAL_MAX_QUERIES", 12
                ),
                image_results_per_query=r.integer(
                    "SYNTHPOST_SEARXNG_IMAGE_RESULTS_PER_QUERY", 3
                ),
                video_results_per_query=r.integer(
                    "SYNTHPOST_SEARXNG_VIDEO_RESULTS_PER_QUERY", 2
                ),
                video_download_limit=r.integer(
                    "SYNTHPOST_SEARXNG_VIDEO_DOWNLOAD_LIMIT", 6
                ),
                video_clip_seconds=r.integer(
                    "SYNTHPOST_SEARXNG_VIDEO_CLIP_SECONDS", 45
                ),
                video_max_duration_seconds=r.integer(
                    "SYNTHPOST_SEARXNG_VIDEO_MAX_DURATION", 900
                ),
                video_timeout_seconds=r.number(
                    "SYNTHPOST_SEARXNG_VIDEO_TIMEOUT", 300.0
                ),
                searxng_socket_timeout_seconds=r.number(
                    "SYNTHPOST_SEARXNG_SOCKET_TIMEOUT", 15.0
                ),
                enforce_broadcast_fit=r.boolean(
                    "SYNTHPOST_VISUAL_ENFORCE_BROADCAST_FIT", True
                ),
                min_width=r.integer("SYNTHPOST_VISUAL_MIN_WIDTH", 1280),
                min_height=r.integer("SYNTHPOST_VISUAL_MIN_HEIGHT", 720),
                aspect_tolerance=r.number("SYNTHPOST_VISUAL_ASPECT_TOLERANCE", 0.20),
                image_aspect_tolerance=r.number(
                    "SYNTHPOST_VISUAL_IMAGE_ASPECT_TOLERANCE", 0.30
                ),
                download_timeout_seconds=r.number(
                    "SYNTHPOST_VISUAL_DOWNLOAD_TIMEOUT", 30.0
                ),
                download_max_bytes=r.integer(
                    "SYNTHPOST_VISUAL_DOWNLOAD_MAX_BYTES", 104_857_600
                ),
                yt_dlp_binary=r.text("SYNTHPOST_YT_DLP", "yt-dlp"),
                tesseract_binary=r.text("SYNTHPOST_TESSERACT", "tesseract"),
                approved_video_channel_ids=r.csv(
                    "SYNTHPOST_VIDEO_APPROVED_CHANNEL_IDS", lowercase=False
                ),
                approved_video_source_names=r.csv(
                    "SYNTHPOST_VIDEO_APPROVED_SOURCE_NAMES"
                ),
                blocked_video_source_names=r.csv(
                    "SYNTHPOST_VIDEO_BLOCKED_SOURCE_NAMES"
                ),
            ),
            avatar=AvatarSettings(
                engine_path=Path(
                    r.text(
                        "SYNTHPOST_AVATAR_ENGINE_PATH",
                        "avatar-engine",
                        aliases=("SYNTHPOST_AVATAR_ENGINE_DIR",),
                    )
                    or "avatar-engine"
                ),
                python_path=(
                    Path(value) if (value := r.text("SYNTHPOST_AVATAR_PYTHON")) else None
                ),
                renderer=r.text("SYNTHPOST_AVATAR_RENDERER"),
                asset_path=r.text(
                    "SYNTHPOST_AVATAR_ASSET_PATH",
                    "assets/avatars/synthpost_anchor_v1/anchor.glb",
                ),
                metadata_path=r.text(
                    "SYNTHPOST_AVATAR_META_PATH",
                    "assets/avatars/synthpost_anchor_v1/avatar.json",
                ),
                words_per_minute=r.number("SYNTHPOST_WORDS_PER_MINUTE", 145.0),
                browser_timeout_padding_seconds=r.number(
                    "AVATAR_ENGINE_BROWSER_TIMEOUT_PADDING_S", 900.0
                ),
            ),
            narration=NarrationSettings(
                python_path=Path(
                    r.text("SYNTHPOST_TTS_PYTHON", ".venv-dots-tts/bin/python")
                    or ".venv-dots-tts/bin/python"
                ),
                model_path=Path(
                    r.text(
                        "SYNTHPOST_TTS_MODEL_PATH",
                        ".cache/dots-tts/int4",
                    )
                    or ".cache/dots-tts/int4"
                ),
                model_name=r.text(
                    "SYNTHPOST_TTS_MODEL_NAME", "dots.tts-soar-mlx-int4"
                ),
                voice_id=r.text(
                    "SYNTHPOST_TTS_VOICE_ID",
                    "anchor",
                ),
                voice_profile_path=(
                    Path(value)
                    if (
                        value := r.text("SYNTHPOST_TTS_VOICE_PROFILE_PATH")
                    )
                    else None
                ),
                reference_audio_path=(
                    Path(value)
                    if (value := r.text("SYNTHPOST_TTS_REFERENCE_AUDIO"))
                    else None
                ),
                reference_text=r.text("SYNTHPOST_TTS_REFERENCE_TEXT"),
                language_code=r.text(
                    "SYNTHPOST_TTS_LANGUAGE",
                    "EN",
                ),
                voice_speed=r.number(
                    "SYNTHPOST_TTS_SPEED",
                    1.0,
                ),
                num_steps=(
                    r.integer("SYNTHPOST_TTS_NUM_STEPS", 4)
                    if r.text("SYNTHPOST_TTS_NUM_STEPS")
                    else None
                ),
                guidance_scale=r.number(
                    "SYNTHPOST_TTS_GUIDANCE_SCALE", 1.2
                ),
                speaker_scale=r.number(
                    "SYNTHPOST_TTS_SPEAKER_SCALE", 1.5
                ),
                seed=r.integer("SYNTHPOST_TTS_SEED", 42),
                max_generate_length=r.integer(
                    "SYNTHPOST_TTS_MAX_GENERATE_LENGTH", 500
                ),
                narration_beat_pause_ms=r.integer(
                    "SYNTHPOST_NARRATION_BEAT_PAUSE_MS", 80
                ),
                narration_section_pause_ms=r.integer(
                    "SYNTHPOST_NARRATION_SECTION_PAUSE_MS", 220
                ),
            ),
            render=RenderSettings(
                remotion_path=Path(
                    r.text("SYNTHPOST_REMOTION_DIR", "compositor/remotion_renderer")
                    or "compositor/remotion_renderer"
                ),
                remotion_concurrency=r.integer(
                    "SYNTHPOST_REMOTION_CONCURRENCY", 4
                ),
                ffmpeg_binary=r.text("SYNTHPOST_FFMPEG", "ffmpeg"),
                profile=(
                    r.text("SYNTHPOST_RENDER_PROFILE", "production") or "production"
                ).lower(),
                codec=r.text("SYNTHPOST_RENDER_CODEC", "h264"),
                preview_frame=r.integer("SYNTHPOST_RENDER_PREVIEW_FRAME", 24),
                experimental_source_audio=r.boolean(
                    "SYNTHPOST_EXPERIMENTAL_SOURCE_AUDIO", False
                ),
            ),
            jobs=JobSettings(
                editorial_workers=r.integer("SYNTHPOST_EDITORIAL_WORKERS", 3),
                media_workers=r.integer("SYNTHPOST_MEDIA_WORKERS", 3),
                render_workers=r.integer("SYNTHPOST_RENDER_WORKERS", 3),
                editorial_max_attempts=r.integer(
                    "SYNTHPOST_EDITORIAL_JOB_MAX_ATTEMPTS", 3
                ),
                media_max_attempts=r.integer("SYNTHPOST_MEDIA_JOB_MAX_ATTEMPTS", 3),
                render_max_attempts=r.integer("SYNTHPOST_RENDER_JOB_MAX_ATTEMPTS", 2),
                retry_base_seconds=r.number("SYNTHPOST_JOB_RETRY_BASE_SECONDS", 15.0),
                retry_max_seconds=r.number("SYNTHPOST_JOB_RETRY_MAX_SECONDS", 900.0),
                heartbeat_seconds=r.number("SYNTHPOST_JOB_HEARTBEAT_SECONDS", 5.0),
            ),
        )
    except ConfigurationError:
        raise
    except ValueError as exc:
        raise ConfigurationError(f"Invalid SynthPost configuration: {exc}") from exc


def get_settings() -> SynthPostSettings:
    """Return a fresh settings snapshot (keeps environment-patched tests deterministic)."""

    return load_settings()


def validate_startup(*, require_provider_credentials: bool = False) -> SynthPostSettings:
    settings = get_settings()
    if require_provider_credentials and (problem := settings.llm.provider_problem()):
        raise ConfigurationError(problem)
    return settings


# Compatibility accessors retained for modules and external scripts that use the
# original config API. New code should prefer get_settings().<group>.
def env(name: str, default: str | None = None) -> str | None:
    return _Reader(os.environ).text(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    return _Reader(os.environ).boolean(name, default)


def env_float(name: str, default: float) -> float:
    return _Reader(os.environ).number(name, default)


def avatar_engine_dir() -> Path:
    return resolve_project_path(get_settings().avatar.engine_path)


def remotion_dir() -> Path:
    return resolve_project_path(get_settings().render.remotion_path)


def ffmpeg_binary() -> str:
    return get_settings().render.ffmpeg_binary


def words_per_minute() -> float:
    return get_settings().avatar.words_per_minute


def source_audio_inserts_enabled() -> bool:
    """Keep unverified source audio out of production unless explicitly enabled."""

    return get_settings().render.experimental_source_audio


def sample_story_path() -> Path:
    return (
        PROJECT_ROOT
        / "episodes"
        / "ep_2026-06-20"
        / "stories"
        / "story_001"
        / "story.json"
    )
