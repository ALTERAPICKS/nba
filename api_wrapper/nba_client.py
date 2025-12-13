import time
from nba_api.stats.endpoints import leaguedashteamstats

SEASON = "2025-26"
SEASON_TYPE = "Regular Season"
API_SLEEP = 0.6


def _sleep():
    time.sleep(API_SLEEP)


def _get_row(df, team_id):
    row = df[df["TEAM_ID"] == team_id]
    if row.empty:
        raise RuntimeError("Team not found in NBA response")
    return row.iloc[0]


def _pull(team_id, last_n_games, measure_type):
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
    return _get_row(df, team_id)


# --------------------------------------------------
# PUBLIC FUNCTION — EXACT NBA.com TEAM STATS
# --------------------------------------------------
def get_team_stats(team_id: int, last_n_games: int = 5):
    """
    Mirrors NBA.com Team Stats tabs with Last N Games + Pace Adjust ON
    """

    return {
        "team_id": team_id,
        "last_n_games": last_n_games,

        # --- NBA.com tabs ---
        "advanced": dict(_pull(team_id, last_n_games, "Advanced")),
        "traditional": dict(_pull(team_id, last_n_games, "Base")),
        "four_factors": dict(_pull(team_id, last_n_games, "Four Factors")),
        "misc": dict(_pull(team_id, last_n_games, "Misc")),
        "scoring": dict(_pull(team_id, last_n_games, "Scoring")),
        "opponent": dict(_pull(team_id, last_n_games, "Opponent")),
        "shooting": dict(_pull(team_id, last_n_games, "Shooting"))
    }
