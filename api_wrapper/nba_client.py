from nba_api.stats.endpoints import teamdashboardbygeneralsplits

def get_team_dashboard(team_id: int, last_n_games: int):
    response = teamdashboardbygeneralsplits.TeamDashboardByGeneralSplits(
        team_id=team_id,
        last_n_games=last_n_games
    )

    df = response.get_data_frames()[0]

    return {
        "team_id": team_id,
        "last_n_games": last_n_games,
        "metrics": df.iloc[0].to_dict()
    }

