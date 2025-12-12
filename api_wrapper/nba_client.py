from nba_api.stats.endpoints import teamdashboardbygeneralsplits
import time

SEASON = "2025-26"

def _overall_row(df):
    """
    Extract ONLY the 'Overall' row.
    This is where OFF_RATING / DEF_RATING / PACE live.
    """
    if "GROUP_SET" in df.columns:
        overall = df[df["GROUP_SET"] == "Overall"]
        if not overall.empty:
            return overall.iloc[0].to_dict()
    return {}

def get_team_dashboard(team_id: int, last_n_games: int = 5):
    time.sleep(0.6)  # NBA API safety

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
        "Base": _overall_row(dfs[0]),
        "Advanced": _overall_row(dfs[1]),      # ✅ OFF_RATING / DEF_RATING / PACE
        "Misc": _overall_row(dfs[2]),
        "Four Factors": _overall_row(dfs[3]),
        "Scoring": _overall_row(dfs[4]),
        "Opponent": _overall_row(dfs[5])
    }
