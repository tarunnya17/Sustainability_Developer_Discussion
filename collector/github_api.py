"""
A small GitHub API client used by the collector.

It does four things:
  1. Adds your token to every request (so you get 5000 requests/hour instead of 60).
  2. Follows REST pagination (GitHub's "Link: <...>; rel=next" header).
  3. Waits automatically when the rate limit is almost used up.
  4. Retries temporary errors (server errors, network timeouts).
"""

import os
import time

import requests

API_URL = "https://api.github.com"
GRAPHQL_URL = "https://api.github.com/graphql"

MAX_RETRIES = 6          # how many times to retry a failing request
MIN_REMAINING = 20       # pause when fewer than this many requests are left


class GitHubClient:
    def __init__(self, token=None):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "sustainability-developer-discussion-collector",
        })
        if self.token:
            self.session.headers["Authorization"] = f"Bearer {self.token}"

    # ------------------------------------------------------------------
    # Low-level request with retries and rate-limit handling
    # ------------------------------------------------------------------
    def _request(self, method, url, **kwargs):
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self.session.request(method, url, timeout=60, **kwargs)
            except (requests.ConnectionError, requests.Timeout) as error:
                wait = 2 ** attempt
                print(f"  network error ({error.__class__.__name__}), retrying in {wait}s")
                time.sleep(wait)
                continue

            # Rate limited: GitHub says how long to wait (Retry-After) or when the limit resets.
            if response.status_code in (403, 429) and self._is_rate_limited(response):
                self._sleep_until_reset(response)
                continue

            # Temporary server problem: wait a bit and try again.
            if response.status_code >= 500:
                wait = 2 ** attempt
                print(f"  server error {response.status_code}, retrying in {wait}s")
                time.sleep(wait)
                continue

            response.raise_for_status()
            self._pause_if_low(response)
            return response

        raise RuntimeError(f"Giving up on {url} after {MAX_RETRIES} attempts")

    @staticmethod
    def _is_rate_limited(response):
        return (
            "Retry-After" in response.headers
            or response.headers.get("X-RateLimit-Remaining") == "0"
            or "rate limit" in response.text.lower()
        )

    @staticmethod
    def _sleep_until_reset(response):
        if "Retry-After" in response.headers:
            wait = int(response.headers["Retry-After"]) + 1
        else:
            reset_at = int(response.headers.get("X-RateLimit-Reset", time.time() + 60))
            wait = max(reset_at - time.time(), 0) + 5
        print(f"  rate limit reached, sleeping {wait / 60:.1f} min")
        time.sleep(wait)

    def _pause_if_low(self, response):
        remaining = response.headers.get("X-RateLimit-Remaining")
        if remaining is not None and int(remaining) < MIN_REMAINING:
            self._sleep_until_reset(response)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------
    def get_json(self, path_or_url, params=None):
        """GET a single REST resource, e.g. get_json('/repos/huggingface/transformers')."""
        url = path_or_url if path_or_url.startswith("http") else API_URL + path_or_url
        return self._request("GET", url, params=params).json()

    def get_pages(self, start_url, params=None):
        """
        Yield (page_items, next_url) for every page of a REST list endpoint.

        next_url is the URL of the following page (or None on the last page).
        The collector saves next_url as a checkpoint so it can resume later.
        """
        url = start_url if start_url.startswith("http") else API_URL + start_url
        while url:
            response = self._request("GET", url, params=params)
            params = None  # the "next" URL from GitHub already contains all parameters
            url = response.links.get("next", {}).get("url")
            yield response.json(), url

    def graphql(self, query, variables=None):
        """Run a GraphQL query and return its "data" part."""
        if not self.token:
            raise RuntimeError("The GraphQL API needs a token. Put GITHUB_TOKEN in your .env file.")
        for attempt in range(1, MAX_RETRIES + 1):
            response = self._request("POST", GRAPHQL_URL, json={"query": query, "variables": variables or {}})
            result = response.json()
            if "errors" not in result:
                return result["data"]
            # GraphQL sometimes reports temporary problems (timeouts, secondary limits) as "errors".
            print(f"  GraphQL error: {result['errors'][0].get('message')} (attempt {attempt})")
            time.sleep(10 * attempt)
        raise RuntimeError(f"GraphQL query kept failing: {result['errors']}")
