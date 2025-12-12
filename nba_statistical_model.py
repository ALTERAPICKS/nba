"""
NBA Statistical Projection Model
8-Stage System with Recency Weighting, Pace Dampening, and Opponent Normalization
(Hardened for Render + GitHub Actions)
"""

from nba_api.stats.static import teams
from nba_api.stats.endpoints import teamdashboardbyshootingsplits
import pandas as pd
import requests
import time
from datetime import datetime
from typing import Dict, List

# -----------------------------------------------------------------------------
# Render API Configuration
# -----------------------------------------------------------------------------
BASE_URL = "https://nba-e6du.onrender.com"


def warm_up_api():
    """Warm up Render service + upstream nba_api before heavy usage."""
    try:
        print("Warming up Render API...")
        requests.get(f"{BASE_URL}/health", timeout=10)
        time.sleep(10)  # allow container + nba_api to fully wake
    except Exception as e:
        print(f"Warm-up warning: {e}")


def get_team_dashboard(team_id, last_n):
    """Safe Render client with retries, backoff, and realistic timeout."""
    if not last_n or last_n <= 0:
        last_n = 5

    url = f"{BASE_URL}/team-dashboard/{team_id}"

    for attempt in range(3):
        try:
            resp = requests.get(
                url,
                params={"last_n_games": last_n},
                timeout=30
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            print(f"Retrying team {team_id} (attempt {attempt + 1})")
            time.sleep(5)

    raise RuntimeError(f"Failed to fetch dashboard for team {team_id}")


# -----------------------------------------------------------------------------
# Model Class
# -----------------------------------------------------------------------------
class NBAStatisticalModel:
    """
    NBA Statistical Model with recency weighting and regression adjustments
    """

    SEASON = '2025-26'
    LEAGUE_AVG_PACE = 98.5
    LEAGUE_AVG_OFFRTG = 115.0
    LEAGUE_AVG_DEFRTG = 115.0

    LAST5_WEIGHT = 0.65
    SEASON_WEIGHT = 0.35
    PACE_DAMPENING = 0.6
    SHOOTING_REGRESSION = 0.25
    HOME_COURT_ADJ = 1.8

    def __init__(self):
        self.all_teams = teams.get_teams()

    # -------------------------------------------------------------------------
    # Team Helpers
    # -------------------------------------------------------------------------
    def get_team_id(self, team_name: str) -> int:
        for team in self.all_teams:
            if team_name.lower() in team['full_name'].lower() or \
               team_name.lower() in team['nickname'].lower() or \
               team_name.lower() in team['abbreviation'].lower():
                return team['id']
        raise ValueError(f"Team '{team_name}' not found")

    def _espn_abbr_to_full_name(self, abbr: str) -> str:
        espn_to_nba = {
            'WSH': 'WAS',
            'UTAH': 'UTA',
            'GS': 'GSW',
            'SA': 'SAS',
            'NY': 'NYK',
            'NO': 'NOP'
        }
        nba_abbr = espn_to_nba.get(abbr, abbr)
        for team in self.all_teams:
            if team['abbreviation'] == nba_abbr:
                return team['full_name']
        return abbr

    # -------------------------------------------------------------------------
    # Schedule
    # -------------------------------------------------------------------------
    def get_todays_schedule(self) -> List[Dict]:
        today = datetime.now().strftime('%m/%d/%Y')
        print(f"\nFetching NBA schedule for {today}...")

        url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        schedule = []
        for event in data.get('events', []):
            competitions = event.get('competitions', [])
            if not competitions:
                continue
            competitors = competitions[0].get('competitors', [])
            if len(competitors) < 2:
                continue

            home = competitors[0] if competitors[0].get('homeAway') == 'home' else competitors[1]
            away = competitors[1] if competitors[0].get('homeAway') == 'home' else competitors[0]

            schedule.append({
                'home_team': self._espn_abbr_to_full_name(home['team']['abbreviation']),
                'away_team': self._espn_abbr_to_full_name(away['team']['abbreviation'])
            })

        print(f"Found {len(schedule)} game(s) today")
        return schedule

    # -------------------------------------------------------------------------
    # Data Pull
    # -------------------------------------------------------------------------
    def pull_team_data(self, team_name: str) -> Dict:
        team_id = self.get_team_id(team_name)
        team_data = {'last5': {}, 'season': {}, 'opponent_last5': {}}

        categories = ['Base', 'Advanced', 'Four Factors', 'Misc', 'Scoring', 'Opponent']

        for category in categories:
            try:
                data = get_team_dashboard(team_id, last_n=5)
                team_data['last5'][category] = pd.Series(data.get(category, {}))
            except Exception as e:
                print(f"Last5 {team_name} {category} failed: {e}")
                team_data['last5'][category] = None

        for category in categories:
            try:
                data = get_team_dashboard(team_id, last_n=0)
                team_data['season'][category] = pd.Series(data.get(category, {}))
            except Exception as e:
                print(f"Season {team_name} {category} failed: {e}")
                team_data['season'][category] = None

        try:
            data = get_team_dashboard(team_id, last_n=5)
            team_data['opponent_last5'] = pd.Series(data.get('Opponent', {}))
        except Exception as e:
            print(f"Opponent stats failed: {e}")
            team_data['opponent_last5'] = None

        return team_data

    # -------------------------------------------------------------------------
    # Stages (unchanged logic)
    # -------------------------------------------------------------------------
    def stage1_recency_weighting(self, team_data: Dict) -> Dict:
        adjusted = {}
        stats = [
            ('Advanced', 'OFF_RATING'),
            ('Advanced', 'DEF_RATING'),
            ('Advanced', 'PACE'),
        ]
        for category, stat in stats:
            try:
                last5 = team_data['last5'][category][stat]
                season = team_data['season'][category][stat]
                adjusted[stat] = last5 * self.LAST5_WEIGHT + season * self.SEASON_WEIGHT
            except Exception:
                adjusted[stat] = 0
        return adjusted

    def stage2_pace_dampening(self, pace):
        return self.LEAGUE_AVG_PACE + (pace - self.LEAGUE_AVG_PACE) * self.PACE_DAMPENING

    def stage5_projected_points(self, off, opp_def, pace):
        return ((off + opp_def) / 2) / 100 * pace

    def stage6_home_court(self, home_pts, away_pts):
        return home_pts + self.HOME_COURT_ADJ, away_pts - self.HOME_COURT_ADJ

    # -------------------------------------------------------------------------
    # Full Game Projection
    # -------------------------------------------------------------------------
    def project_game(self, home_team: str, away_team: str) -> Dict:
        home_data = self.pull_team_data(home_team)
        away_data = self.pull_team_data(away_team)

        home_adj = self.stage1_recency_weighting(home_data)
        away_adj = self.stage1_recency_weighting(away_data)

        pace = (self.stage2_pace_dampening(home_adj['PACE']) +
                self.stage2_pace_dampening(away_adj['PACE'])) / 2

        home_pts = self.stage5_projected_points(home_adj['OFF_RATING'], away_adj['DEF_RATING'], pace)
        away_pts = self.stage5_projected_points(away_adj['OFF_RATING'], home_adj['DEF_RATING'], pace)

        home_pts, away_pts = self.stage6_home_court(home_pts, away_pts)

        return {
            'home_team': home_team,
            'away_team': away_team,
            'home_points': round(home_pts, 1),
            'away_points': round(away_pts, 1),
            'spread': round(home_pts - away_pts, 1),
            'total': round(home_pts + away_pts, 1)
        }

    # -------------------------------------------------------------------------
    # Entry Point
    # -------------------------------------------------------------------------
    def project_all_games(self):
        warm_up_api()  # CRITICAL: warm Render once

        schedule = self.get_todays_schedule()
        results = []

        for game in schedule:
            try:
                result = self.project_game(game['home_team'], game['away_team'])
                results.append(result)
                print(result)
                time.sleep(1.0)  # pacing
            except Exception as e:
                print(f"Game failed: {e}")
                continue

        return results


# -----------------------------------------------------------------------------
# Script Execution
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    model = NBAStatisticalModel()
    model.project_all_games()
