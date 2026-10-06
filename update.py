"""Render the neofetch-style profile card (dark_mode.svg / light_mode.svg).

Live numbers come from the GitHub GraphQL API when GITHUB_TOKEN (or GH_TOKEN)
is set; otherwise the last values saved in stats.json are reused, so the card
can be re-rendered offline after editing the static fields below.
"""
import datetime as dt
import json
import os
import time
import urllib.request
from html import escape
from pathlib import Path

ROOT = Path(__file__).parent
USER = os.environ.get("PROFILE_USER", "aakarshitv")

# --- Static fields: edit these freely -------------------------------------
HEADER = "aakarshit@verma"
ABOUT = [
    ("OS", "macOS"),
    ("Uptime", "{uptime}"),
    ("Host", "Open Source / GSoC 2026"),
    ("Kernel", "Student Developer"),
    ("IDE", "VS Code, Zed"),
    None,
    ("Languages.Programming", "TypeScript, Rust, Python, Kotlin"),
    ("Languages.Real", "English, Hindi"),
    None,
    ("Contributing.To", "Effect, nushell, uutils, Kiwix, iD"),
    ("Hobbies", "Open source, CLI tools"),
]
CONTACT = [
    ("GitHub", USER),
]
# ---------------------------------------------------------------------------

ASCII_COLS, ASCII_ROWS = 40, 25
WIDTH_CHARS = 60  # right column width, in characters
LINE_H, TOP, LEFT_X, RIGHT_X = 20, 30, 15, 395
CARD_W = 1000
STAT_W = 20  # width of the right-hand pair on two-pair stat rows

THEMES = {
    "dark": dict(bg="#161b22", text="#c9d1d9", key="#ffa657", value="#a5d6ff",
                 dots="#616e7f", good="#3fb950", bad="#f85149"),
    "light": dict(bg="#f6f8fa", text="#24292f", key="#953800", value="#0a3069",
                  dots="#c2cfde", good="#1a7f37", bad="#cf222e"),
}


def graphql(query, **variables):
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        body = json.load(resp)
    if "errors" in body:
        raise RuntimeError(body["errors"])
    return body["data"]


def own_repo_loc(repo):
    """(added, deleted) lines by USER on a repo's default branch, or None if
    GitHub is still computing the stats."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{USER}/{repo}/stats/contributors",
        headers={"Authorization": f"bearer {token}"},
    )
    # GitHub computes these stats lazily and answers 202 until they're ready.
    for _ in range(12):
        with urllib.request.urlopen(req) as resp:
            if resp.status == 200:
                for author in json.load(resp):
                    if (author.get("author") or {}).get("login", "").lower() == USER.lower():
                        return (sum(w["a"] for w in author["weeks"]),
                                sum(w["d"] for w in author["weeks"]))
                return 0, 0
            if resp.status == 204:  # empty repo
                return 0, 0
        time.sleep(5)
    return None


def fetch_stats():
    user = graphql(
        """query($login: String!) {
          user(login: $login) {
            createdAt
            followers { totalCount }
            repositories(first: 100, ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false) {
              totalCount
              nodes { name stargazerCount }
            }
          }
        }""",
        login=USER,
    )["user"]
    created = dt.datetime.fromisoformat(user["createdAt"].replace("Z", "+00:00"))

    # contributionsCollection spans at most one year, so walk year by year.
    contributions = 0
    start, now = created, dt.datetime.now(dt.timezone.utc)
    while start < now:
        end = min(start + dt.timedelta(days=365), now)
        contributions += graphql(
            """query($login: String!, $from: DateTime!, $to: DateTime!) {
              user(login: $login) {
                contributionsCollection(from: $from, to: $to) {
                  contributionCalendar { totalContributions }
                }
              }
            }""",
            login=USER, **{"from": start.isoformat(), "to": end.isoformat()},
        )["user"]["contributionsCollection"]["contributionCalendar"]["totalContributions"]
        start = end

    merged_repos, merged, added, deleted = upstream_prs("is:merged")
    open_repos, opened, _, _ = upstream_prs("is:open")
    # Lines of code: own repos plus upstream PRs that actually landed.
    own = [own_repo_loc(repo["name"]) for repo in user["repositories"]["nodes"]]
    if None in own:
        # Stats not ready (common right after a push): keep the last totals.
        old = json.loads((ROOT / "stats.json").read_text())
        added, deleted = old.get("loc_added", added), old.get("loc_deleted", deleted)
    else:
        added += sum(a for a, _ in own)
        deleted += sum(d for _, d in own)
    return {
        "created": user["createdAt"],
        "repos": user["repositories"]["totalCount"],
        "stars": sum(n["stargazerCount"] for n in user["repositories"]["nodes"]),
        "followers": user["followers"]["totalCount"],
        "contributions": contributions,
        "prs_merged": merged,
        "prs_open": opened,
        "projects": len(merged_repos | open_repos),
        "loc_added": added,
        "loc_deleted": deleted,
    }


def upstream_prs(state):
    """PRs to repositories owned by someone else: (repos, count, added, deleted)."""
    repos, cursor, count, added, deleted = set(), None, 0, 0, 0
    while True:
        search = graphql(
            """query($q: String!, $cursor: String) {
              search(query: $q, type: ISSUE, first: 100, after: $cursor) {
                issueCount
                nodes { ... on PullRequest { additions deletions repository { nameWithOwner } } }
                pageInfo { hasNextPage endCursor }
              }
            }""",
            q=f"author:{USER} is:pr {state} -user:{USER}", cursor=cursor,
        )["search"]
        count = search["issueCount"]
        nodes = [n for n in search["nodes"] if n]
        repos |= {n["repository"]["nameWithOwner"] for n in nodes}
        added += sum(n["additions"] for n in nodes)
        deleted += sum(n["deletions"] for n in nodes)
        if not search["pageInfo"]["hasNextPage"]:
            return repos, count, added, deleted
        cursor = search["pageInfo"]["endCursor"]


def uptime(created_iso):
    created = dt.date.fromisoformat(created_iso[:10])
    today = dt.date.today()
    months = (today.year - created.year) * 12 + today.month - created.month
    if today.day < created.day:
        months -= 1
    anchor_month = created.month + months
    anchor = dt.date(created.year + (anchor_month - 1) // 12, (anchor_month - 1) % 12 + 1,
                     min(created.day, 28))
    days = (today - anchor).days
    y, m = divmod(months, 12)
    plural = lambda n, unit: f"{n} {unit}{'' if n == 1 else 's'}"
    return f"{plural(y, 'year')}, {plural(m, 'month')}, {plural(days, 'day')}"


# --- SVG rendering ----------------------------------------------------------
# A line is a list of (css class, text) spans; widths are counted in characters.

def pair(key, value, width):
    """'Key: ..... value' padded with dots to exactly `width` characters."""
    key_spans = []
    for i, part in enumerate(key.split(".")):
        if i:
            key_spans.append(("text", "."))
        key_spans.append(("key", part))
    dots = width - len(key) - 1 - len(value)
    filler = " " + "." * (dots - 2) + " " if dots >= 3 else " " * max(dots, 1)
    return key_spans + [("text", ":"), ("dots", filler), ("value", value)]


def row(*pairs):
    """Prefix a row of key/value pairs, joining several with ' | '."""
    spans = [("dots", ". ")]
    budget = WIDTH_CHARS - 2 - 3 * (len(pairs) - 1)
    widths = [budget - STAT_W * (len(pairs) - 1)] + [STAT_W] * (len(pairs) - 1)
    for i, ((key, value), width) in enumerate(zip(pairs, widths)):
        if i:
            spans.append(("text", " | "))
        spans += pair(key, value, width)
    return spans


def loc_row(added, deleted):
    """'Lines of Code: .... net ( added++, deleted-- )', coloured like a diff."""
    tail = [("text", " ( "), ("good", f"{added:,}++"), ("text", ", "),
            ("bad", f"{deleted:,}--"), ("text", " )")]
    spans = pair("Lines of Code", f"{added - deleted:,}",
                 WIDTH_CHARS - 2 - sum(len(t) for _, t in tail))
    return [("dots", ". ")] + spans + tail


def heading(title):
    return [("text", title + " " + "-" * (WIDTH_CHARS - len(title) - 1))]


def build_lines(stats):
    lines = [heading(HEADER)]
    for item in ABOUT:
        if item is None:
            lines.append([("dots", ".")])
        else:
            key, value = item
            lines.append(row((key, value.format(uptime=uptime(stats["created"])))))
    lines.append([])
    lines.append(heading("- Contact"))
    lines += [row(item) for item in CONTACT]
    lines.append([])
    lines.append(heading("- GitHub Stats"))
    n = lambda key: f"{stats[key]:,}"
    lines.append(row(("Repos", n("repos")), ("Stars", n("stars"))))
    lines.append(row(("Contributions", n("contributions")), ("Followers", n("followers"))))
    lines.append(row(("Upstream.PRs", f"{n('prs_merged')} merged, {n('prs_open')} open"),
                     ("Projects", n("projects"))))
    lines.append(loc_row(stats.get("loc_added", 0), stats.get("loc_deleted", 0)))
    return lines


def render(theme, stats):
    c = THEMES[theme]
    art = (ROOT / "ascii.txt").read_text().splitlines()[:ASCII_ROWS]
    while art and not art[0].strip():
        art.pop(0)
    while art and not art[-1].strip():
        art.pop()
    lines = build_lines(stats)
    rows = max(len(art), len(lines))
    art_top = TOP + (rows - len(art)) // 2 * LINE_H  # centre the art beside the text
    height = TOP + (rows - 1) * LINE_H + 20
    width = CARD_W

    out = [
        "<?xml version='1.0' encoding='UTF-8'?>",
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}px" height="{height}px" '
        'font-family="ConsolasFallback,Consolas,\'SF Mono\',Menlo,\'DejaVu Sans Mono\',monospace" '
        'font-size="16px">',
        "<style>",
        # Consolas runs narrower than other monospace fonts; scale it so the
        # dot-justified columns line up the same on every OS.
        "@font-face {src: local('Consolas'); font-family: 'ConsolasFallback'; size-adjust: 109%;}",
        f".text {{fill: {c['text']};}} .key {{fill: {c['key']};}} .value {{fill: {c['value']};}}",
        f".dots {{fill: {c['dots']};}} .good {{fill: {c['good']};}} .bad {{fill: {c['bad']};}}",
        "text, tspan {white-space: pre;}",
        "</style>",
        f'<rect width="{width}px" height="{height}px" fill="{c["bg"]}" rx="15"/>',
        f'<text class="text" x="{LEFT_X}" y="{art_top}">',
    ]
    for i, line in enumerate(art):
        out.append(f'<tspan x="{LEFT_X}" y="{art_top + i * LINE_H}">{escape(line)}</tspan>')
    out.append("</text>")
    out.append(f'<text class="text" x="{RIGHT_X}" y="{TOP}">')
    for i, spans in enumerate(lines):
        if not spans:
            continue
        y = TOP + i * LINE_H
        parts = "".join(f'<tspan class="{cls}">{escape(text)}</tspan>' for cls, text in spans)
        out.append(f'<tspan x="{RIGHT_X}" y="{y}">{parts}</tspan>')
    out.append("</text>")
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main():
    cache = ROOT / "stats.json"
    if os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"):
        stats = fetch_stats()
        cache.write_text(json.dumps(stats, indent=2) + "\n")
    else:
        stats = json.loads(cache.read_text())
    for theme in THEMES:
        (ROOT / f"{theme}_mode.svg").write_text(render(theme, stats))
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
