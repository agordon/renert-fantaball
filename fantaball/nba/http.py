"""Small, dependency-free HTTP client for JSON APIs: timeout, rate limiting, retries with exponential backoff.

Error policy (matches the provider docs):
  401 / 403        -> never retried (bad key, or the plan does not include the endpoint)
  429              -> wait (Retry-After if given, else exponential backoff) and retry, up to max_retries
  5xx, timeouts    -> exponential backoff, up to max_retries
  other 4xx        -> never retried (our request is wrong)
The API key is sent as a header and is never put in URLs, log lines or exception messages.
"""
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

from fantaball.nba.provider import (ProviderAccessError, ProviderAuthError, ProviderBadResponse, ProviderRateLimited, ProviderUnavailable)

log = logging.getLogger("fantaball.nba.http")


class HttpClient:
    def __init__(self, base_url: str, api_key: str | None, *, auth_header: str = "Authorization", timeout: float = 20.0, max_retries: int = 4,
                 backoff_base: float = 2.0, backoff_max: float = 60.0, requests_per_minute: float = 5.0, max_requests: int | None = None,
                 quota_header: str | None = None, opener=None, sleep=time.sleep, clock=time.monotonic):
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.auth_header = auth_header
        self.max_requests = max_requests            # hard cap for this client (e.g. what is left of today's quota)
        self.quota_header = quota_header            # response header carrying the requests still available today
        self.quota_remaining: int | None = None
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self.min_interval = 60.0 / requests_per_minute if requests_per_minute else 0.0
        self._opener = opener or urllib.request.urlopen
        self._sleep = sleep
        self._clock = clock
        self._last_start: float | None = None
        self.requests_made = 0

    def _throttle(self):
        if self._last_start is not None and self.min_interval:
            wait = self.min_interval - (self._clock() - self._last_start)
            if wait > 0:
                self._sleep(wait)
        self._last_start = self._clock()

    def _backoff(self, attempt: int, retry_after: float | None = None) -> float:
        if retry_after is not None:
            return min(max(retry_after, 0), self.backoff_max)
        return min(self.backoff_base * (2 ** attempt), self.backoff_max)

    def _note_quota(self, headers):
        if not self.quota_header or headers is None:
            return
        try:
            self.quota_remaining = int(headers.get(self.quota_header))
        except (TypeError, ValueError):
            pass

    def get_json(self, path: str, params: list[tuple[str, str]] | None = None) -> dict:
        url = f"{self.base_url}/{path.lstrip('/')}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = {"Accept": "application/json", "User-Agent": "FantaBall/1.0 (school project)"}
        if self._api_key:
            headers[self.auth_header] = self._api_key
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            if self.quota_remaining is not None and self.quota_remaining <= 0:
                raise ProviderRateLimited("The provider's daily request quota is used up (it resets daily). Nothing more was requested.")
            if self.max_requests is not None and self.requests_made >= self.max_requests:
                raise ProviderRateLimited("Today's request budget for this plan is used up. Nothing more was requested; try again tomorrow.")
            self._throttle()
            self.requests_made += 1
            retry_after = None
            try:
                with self._opener(urllib.request.Request(url, headers=headers), timeout=self.timeout) as resp:
                    raw = resp.read()
                    self._note_quota(getattr(resp, "headers", None))
                try:
                    return json.loads(raw)
                except ValueError as exc:
                    raise ProviderBadResponse(f"Response from {path} was not valid JSON") from exc
            except urllib.error.HTTPError as exc:
                code = exc.code
                if code == 401:
                    raise ProviderAuthError("HTTP 401 from the data provider: the API key is missing/invalid, or your plan does not include this endpoint") from None
                if code == 403:
                    raise ProviderAccessError("HTTP 403 from the data provider: access forbidden (missing or unauthorised request headers, or not allowed for this plan)") from None
                if code == 429:
                    last_error = ProviderRateLimited("HTTP 429 from the data provider: rate limit exceeded (retries exhausted)")
                    try:
                        retry_after = float(exc.headers.get("Retry-After")) if exc.headers and exc.headers.get("Retry-After") else None
                    except ValueError:
                        retry_after = None
                elif code >= 500:
                    last_error = ProviderUnavailable(f"HTTP {code} from the data provider (retries exhausted)")
                else:
                    raise ProviderBadResponse(f"HTTP {code} from the data provider for {path}") from None
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
                last_error = ProviderUnavailable(f"Could not reach the data provider ({type(exc).__name__})")
            if attempt < self.max_retries:
                delay = self._backoff(attempt, retry_after)
                log.warning("provider request to %s failed (%s); retry %d/%d in %.1fs", path, last_error, attempt + 1, self.max_retries, delay)
                self._sleep(delay)
        assert last_error is not None
        raise last_error
