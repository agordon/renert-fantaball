"""Provider selection / configuration from the Flask config + environment. Never exposes the API key."""
import os

from fantaball import timeline
from fantaball.nba.balldontlie import DEFAULT_BASE_URL, BallDontLieProvider
from fantaball.nba.mock import MockNBAProvider
from fantaball.nba.provider import NBADataProvider, ProviderNotConfigured


def _get(config, name, default=None):
    """Read FLASK_<NAME> (app.config[NAME]) or the plain environment variable <NAME>."""
    value = config.get(name)
    if value in (None, ""):
        value = os.environ.get(name)
    return default if value in (None, "") else value


def provider_name(config) -> str:
    return str(_get(config, "NBA_PROVIDER", "balldontlie")).lower()


def api_key(config) -> str | None:
    key = _get(config, "BALLDONTLIE_API_KEY")
    if key and ("your" in str(key).lower() and "key" in str(key).lower()):
        return None                 # the placeholder from .env.example is not a key
    return key


def build_provider(config) -> NBADataProvider:
    name = provider_name(config)
    if name == "mock":
        return MockNBAProvider(today=timeline.today())
    if name == "balldontlie":
        return BallDontLieProvider(api_key(config), base_url=str(_get(config, "BALLDONTLIE_BASE_URL", DEFAULT_BASE_URL)),
                                   requests_per_minute=float(_get(config, "BALLDONTLIE_REQUESTS_PER_MINUTE", 5)))
    raise ProviderNotConfigured(f"Unknown NBA_PROVIDER '{name}' (use 'balldontlie' or 'mock')")


def provider_status(config) -> dict:
    """Safe-to-show configuration status (the key itself is never included)."""
    name = provider_name(config)
    configured = name == "mock" or bool(api_key(config))
    return dict(provider=name, configured=configured, is_mock=name == "mock",
                requests_per_minute=float(_get(config, "BALLDONTLIE_REQUESTS_PER_MINUTE", 5)),
                demo_data=bool(config.get("DEMO_DATA")),
                message=None if configured else "BALLDONTLIE_API_KEY is not set - real NBA data cannot be imported until it is configured.")


def current_season(config) -> int:
    """NBA season identified by its start year (2026 = the 2026-27 season)."""
    configured = _get(config, "NBA_SEASON")
    if configured:
        return int(configured)
    today = timeline.today()
    return today.year if today.month >= 9 else today.year - 1
