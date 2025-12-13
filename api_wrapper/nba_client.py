import time
from nba_api.stats.endpoints import leaguedashteamstats
from nba_api.library.http import NBAStatsHTTP

# --------------------------------------------------
# NBA anti-bot headers (REQUIRED in cloud)
# --------------------------------------------------
NBAStatsHTTP.DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com",
    "Connection": "keep-alive"
}

# --------------------------------------------------
# Config
# --------------------------------------------------
SEASON = "2025-26"
SEASON_TYPE = "Regular Season"
API_SLEEP = 0.6


# --------------------------------------------------
# Helpers
# --------------------------------------------------
def _sleep():
    time.sleep(API_SLEEP)


def _get_team_row(df, team_id: int):
    row = df[df["TEAM_ID"] == team_id]
    if row.empty:
        raise RuntimeError("Team not found in NBA API response")
    return row.iloc[0]


def _pull_measure(team_id: int, last_n_games: int, measure_type: str):
    """
    Pull a single Team Stats tab exactly as NBA.com does it.
    """
    _sleep()

    dash = leaguedashteamstats.LeagueDashTeamStats(
        season=SEASON,
        season_type_all_star=SEASON_TYPE,
        team_id_nullable=team_id,
        last_n_games=last_n_games,
        pace_adjust="Y",
        per_mode_detailed="Per100Possessions",
        measure_type_detailed=measure_type
    )

    df = dash.get_data_frames()[0]
    return dict(_get_team_row(df, team_id))


# --------------------------------------------------
# PUBLIC API
# --------------------------------------------------
def get_team_stats(team_id: int, last_n_games: int = 5):
    """
    Mirrors NBA.com Team Stats with:
    - Last N Games
    - Pace Adjust ON

    Tabs returned:
    - Advanced
    - Traditional
    - Four Factors
    - Misc
    - Scoring
    - Opponent
    - Shooting
    """

    return {
        "team_id": team_id,
        "last_n_games": last_n_games,

        "advanced": _pull_measure(team_id, last_n_games, "Advanced"),
        "traditional": _pull_measure(team_id, last_n_games, "Base"),
        "four_factors": _pull_measure(team_id, last_n_games, "Four Factors"),
        "misc": _pull_measure(team_id, last_n_games, "Misc"),
        "scoring": _pull_measure(team_id, last_n_games, "Scoring"),
        "opponent": _pull_measure(team_id, last_n_games, "Opponent"),
        "shooting": _pull_measure(team_id, last_n_games, "Shooting"),
    }
