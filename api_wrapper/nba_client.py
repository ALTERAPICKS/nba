from nba_api.stats.endpoints import teamdashboardbygeneralsplits
import time

SEASON = "2025-26"

def _df_to_dict(df):
    return df.iloc[0].to_dict() if not df.empty else {}

def get_team_dashboard(team_id: int, last_n_games: int = 5):
    """
    Fetches NBA-calculated team dashboard stats directly from nba_api.
    Returns ALL tables required by both models.
    """

    # NBA API protection (Render cold starts)
    time.sleep(0.6)

    dashboard = teamdashboardbygeneralsplits.TeamDashboardByGeneralSplits(
        team_id=team_id,
        season=SEASON,
        last_n_games=last_n_games
    )

    dfs = dashboard.get_data_frames()

    if len(dfs) < 6:
        raise RuntimeError("Unexpected NBA API response shape")

    return {
        "team_id": team_id,
        "last_n_games": last_n_games,
        "Base": _df_to_dict(dfs[0]),
        "Advanced": _df_to_dict(dfs[1]),        # ✅ OFF_RATING, DEF_RATING, PACE
        "Misc": _df_to_dict(dfs[2]),
        "Four Factors": _df_to_dict(dfs[3]),
        "Scoring": _df_to_dict(dfs[4]),
        "Opponent": _df_to_dict(dfs[5])
    }
