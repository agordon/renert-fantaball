"""Provider selection / configuration from the Flask config + environment. Never exposes an API key."""
import os
from datetime import datetime, timezone

from fantaball import timeline
from fantaball.nba.balldontlie import DEFAULT_BASE_URL as BDL_URL, BallDontLieProvider
from fantaball.nba.highlightly import DEFAULT_BASE_URL as HL_URL, HighlightlyProvider
from fantaball.nba.provider import NBADataProvider, ProviderNotConfigured

PROVIDERS = {"highlightly": ("HIGHLIGHTLY_API_KEY", HighlightlyProvider), "balldontlie": ("BALLDONTLIE_API_KEY", BallDontLieProvider)}


def _get(config, name, default=None):
    """Read FLASK_<NAME> (app.config[NAME]) or the plain environment variable <NAME>."""
    value = config.get(name)
    if value in (None, ""):
        value = os.environ.get(name)
    return default if value in (None, "") else value


def provider_name(config) -> str:
    return str(_get(config, "NBA_PROVIDER", "highlightly")).lower()


def api_key(config, name: str | None = None) -> str | None:
    key_var = PROVIDERS[name or provider_name(config)][0]
    key = _get(config, key_var)
    if key and ("your" in str(key).lower() and "key" in str(key).lower()):
        return None                 # the placeholder from .env.example is not a key
    return key


def used_requests_today(provider: str) -> int:
    """Provider requests already spent today (UTC), from the sync run log - the plan's daily quota is shared by every job."""
    from root import db
    from models.fantasy import DataSyncRun
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    return db.session.scalar(db.select(db.func.coalesce(db.func.sum(DataSyncRun.requests_made), 0)).where(
        DataSyncRun.provider == provider, DataSyncRun.started_at >= start)) or 0


def daily_quota(config) -> int | None:
    name = provider_name(config)
    return int(_get(config, "HIGHLIGHTLY_DAILY_QUOTA", 100)) if name == "highlightly" else None


def build_provider(config) -> NBADataProvider:
    factory = config.get("NBA_PROVIDER_FACTORY")      # set only by the automated tests (an offline fixture provider)
    if factory is not None:
        return factory()
    name = provider_name(config)
    if name == "highlightly":
        quota = daily_quota(config)
        return HighlightlyProvider(api_key(config), base_url=str(_get(config, "HIGHLIGHTLY_BASE_URL", HL_URL)), daily_quota=quota, today=timeline.today,
                                   requests_per_minute=float(_get(config, "HIGHLIGHTLY_REQUESTS_PER_MINUTE", 10)),
                                   max_requests=max(quota - used_requests_today("highlightly"), 0) if quota else None)
    if name == "balldontlie":
        return BallDontLieProvider(api_key(config), base_url=str(_get(config, "BALLDONTLIE_BASE_URL", BDL_URL)),
                                   requests_per_minute=float(_get(config, "BALLDONTLIE_REQUESTS_PER_MINUTE", 5)))
    raise ProviderNotConfigured(f"Unknown NBA_PROVIDER '{name}' (use 'highlightly' or 'balldontlie')")


def provider_status(config) -> dict:
    """Safe-to-show configuration status (the key itself is never included)."""
    factory = config.get("NBA_PROVIDER_FACTORY")
    name = factory().name if factory is not None else provider_name(config)
    configured = factory is not None or bool(api_key(config, name))
    quota = None if factory is not None else daily_quota(config)
    key_var = PROVIDERS.get(name, ("the provider API key",))[0]
    return dict(provider=name, configured=configured, key_variable=key_var,
                requests_per_minute=float(_get(config, "HIGHLIGHTLY_REQUESTS_PER_MINUTE", 10) if name == "highlightly" else _get(config, "BALLDONTLIE_REQUESTS_PER_MINUTE", 5)),
                daily_quota=quota, requests_used_today=used_requests_today(name) if quota else None,
                message=None if configured else f"{key_var} is not set - real NBA data cannot be imported until it is configured.")


def stats_hint(config) -> str:
    """What to tell the user when the provider's plan does not return box scores."""
    factory = config.get("NBA_PROVIDER_FACTORY")
    if factory is not None:
        return factory().stats_plan_hint
    return PROVIDERS.get(provider_name(config), (None, NBADataProvider))[1].stats_plan_hint


def current_season(config) -> int:
    """NBA season identified by its start year (2026 = the 2026-27 season)."""
    configured = _get(config, "NBA_SEASON")
    if configured:
        return int(configured)
    today = timeline.today()
    return today.year if today.month >= 9 else today.year - 1
