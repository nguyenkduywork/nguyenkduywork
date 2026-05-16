import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape


API_ROOT = "https://api.github.com"


def request_json(url, token=None, method="GET", payload=None):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "nguyenkduywork-profile-assets",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8")), response.headers


def get_all_repos(username, token):
    repos = []
    page = 1

    while True:
        url = f"{API_ROOT}/users/{username}/repos?per_page=100&type=owner&sort=updated&page={page}"
        chunk, _headers = request_json(url, token=token)
        if not chunk:
            break
        repos.extend(repo for repo in chunk if not repo.get("fork"))
        if len(chunk) < 100:
            break
        page += 1

    return repos


def get_year_contributions(username, token):
    if not token:
        return None

    now = datetime.now(timezone.utc)
    start = datetime(now.year, 1, 1, tzinfo=timezone.utc).isoformat()
    end = now.isoformat()
    query = """
      query($login: String!, $from: DateTime!, $to: DateTime!) {
        user(login: $login) {
          contributionsCollection(from: $from, to: $to) {
            contributionCalendar {
              totalContributions
            }
            totalCommitContributions
            totalIssueContributions
            totalPullRequestContributions
            totalPullRequestReviewContributions
            restrictedContributionsCount
          }
        }
      }
    """

    payload = {
        "query": query,
        "variables": {"login": username, "from": start, "to": end},
    }
    data, _headers = request_json(f"{API_ROOT}/graphql", token=token, method="POST", payload=payload)
    if data.get("errors"):
        return None

    collection = data["data"]["user"]["contributionsCollection"]
    return {
        "total": collection["contributionCalendar"]["totalContributions"],
        "commits": collection["totalCommitContributions"],
        "issues": collection["totalIssueContributions"],
        "prs": collection["totalPullRequestContributions"],
        "reviews": collection["totalPullRequestReviewContributions"],
        "private": collection["restrictedContributionsCount"],
        "year": now.year,
    }


def format_number(value):
    if value is None:
        return "n/a"
    return f"{value:,}"


def render_svg(username, profile, repos, contributions):
    repos_count = profile.get("public_repos", len(repos))
    stars = sum(repo.get("stargazers_count", 0) for repo in repos)
    forks = sum(repo.get("forks_count", 0) for repo in repos)
    open_issues = sum(repo.get("open_issues_count", 0) for repo in repos)
    followers = profile.get("followers", 0)
    year = contributions["year"] if contributions else datetime.now(timezone.utc).year

    metrics = [
        ("Public repos", repos_count),
        ("Total stars", stars),
        ("Forks", forks),
        (f"{year} contributions", contributions["total"] if contributions else None),
        ("Pull requests", contributions["prs"] if contributions else None),
        ("Issues", contributions["issues"] if contributions else None),
        ("Followers", followers),
        ("Open issues", open_issues),
    ]

    rows = []
    for index, (label, value) in enumerate(metrics):
        column = index % 2
        row = index // 2
        x = 34 + column * 180
        y = 64 + row * 29
        rows.append(
            f"""
            <g transform="translate({x} {y})">
              <text class="metric-label" x="0" y="0">{escape(label)}</text>
              <text class="metric-value" x="0" y="18">{escape(format_number(value))}</text>
            </g>"""
        )

    display_name = profile.get("name") or username
    now = datetime.now(timezone.utc)
    generated_at = f"{now.strftime('%b')} {now.day}, {now.year}"

    return f"""<svg width="410" height="165" viewBox="0 0 410 165" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc">
  <title id="title">{escape(display_name)} GitHub stats</title>
  <desc id="desc">GitHub profile stats for {escape(username)}, generated from GitHub API data.</desc>
  <style>
    .card {{ fill: #1a1b27; }}
    .title {{ fill: #70a5fd; font: 700 18px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .subtitle {{ fill: #38bdf8; font: 500 11px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .metric-label {{ fill: #9ca3af; font: 500 10px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; text-transform: uppercase; }}
    .metric-value {{ fill: #bf91f3; font: 700 16px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .accent {{ stroke: #38bdf8; stroke-width: 2; stroke-linecap: round; opacity: 0.85; }}
    .muted {{ fill: #7dd3fc; font: 500 10px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; opacity: 0.9; }}
  </style>
  <rect class="card" width="410" height="165" rx="6" />
  <path class="accent" d="M24 44H386" />
  <text class="title" x="24" y="30">{escape(display_name)}</text>
  <text class="subtitle" x="386" y="30" text-anchor="end">@{escape(username)}</text>
  {''.join(rows)}
  <text class="muted" x="386" y="149" text-anchor="end">Updated {escape(generated_at)}</text>
</svg>
"""


def main():
    username = os.environ.get("GITHUB_USERNAME", "nguyenkduywork")
    token = os.environ.get("GITHUB_TOKEN")
    output_path = Path(os.environ.get("OUTPUT_PATH", "dist/github-stats.svg"))

    try:
        profile, _headers = request_json(f"{API_ROOT}/users/{username}", token=token)
        repos = get_all_repos(username, token)
        contributions = get_year_contributions(username, token)
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, TimeoutError) as exc:
        print(f"Failed to fetch GitHub stats: {exc}", file=sys.stderr)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_svg(username, profile, repos, contributions), encoding="utf-8")
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
