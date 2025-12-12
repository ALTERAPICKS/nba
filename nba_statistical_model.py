"""
NBA Statistical Projection Model
8-Stage System with Recency Weighting, Pace Dampening, and Opponent Normalization
"""

from nba_api.stats.static import teams
from nba_api.stats.endpoints import (
    teamdashboardbyshootingsplits
)
import pandas as pd
import requests
from datetime import datetime
from typing import Dict, List, Optional

# API Wrapper Configuration
BASE_URL = "https://nba-e6du.onrender.com"

def get_team_dashboard(team_id, last_n):
    if not last_n or last_n <= 0:
        last_n = 5

    url = f"{BASE_URL}/team-dashboard/{team_id}"
    resp = requests.get(
        url,
        params={"last_n_games": last_n},
        timeout=15
    )
    resp.raise_for_status()
    return resp.json()


class NBAStatisticalModel:
    """
    NBA Statistical Model with recency weighting and regression adjustments
    """

    SEASON = '2025-26'
    LEAGUE_AVG_PACE = 98.5
    LEAGUE_AVG_OFFRTG = 115.0
    LEAGUE_AVG_DEFRTG = 115.0

    # Stage 1: Recency weighting
    LAST5_WEIGHT = 0.65
    SEASON_WEIGHT = 0.35

    # Stage 2: Pace dampening
    PACE_DAMPENING = 0.6

    # Stage 3: Shooting regression
    SHOOTING_REGRESSION = 0.25

    # Stage 6: Home court advantage
    HOME_COURT_ADJ = 1.8

    def __init__(self):
        """Initialize statistical model"""
        self.all_teams = teams.get_teams()

    def get_team_id(self, team_name: str) -> int:
        """Get team ID from team name"""
        for team in self.all_teams:
            if team_name.lower() in team['full_name'].lower() or \
               team_name.lower() in team['nickname'].lower() or \
               team_name.lower() in team['abbreviation'].lower():
                return team['id']
        raise ValueError(f"Team '{team_name}' not found")

    def get_team_name_by_id(self, team_id: int) -> str:
        """Get team name from team ID"""
        for team in self.all_teams:
            if team['id'] == team_id:
                return team['full_name']
        return "Unknown Team"

    def get_todays_schedule(self) -> List[Dict]:
        """
        Get today's NBA schedule with home/away teams identified
        Uses ESPN's public scoreboard API (reliable in cloud environments)
        """
        today = datetime.now().strftime('%m/%d/%Y')

        print(f"\nFetching NBA schedule for {today}...")
        print("=" * 80)

        try:
            # Fetch from ESPN's public scoreboard API
            url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            data = response.json()
            events = data.get('events', [])

            if len(events) == 0:
                print("No games scheduled for today.")
                return []

            schedule = []

            for event in events:
                # Extract game info
                event_id = event.get('id', 'unknown')
                competitions = event.get('competitions', [])

                if not competitions:
                    continue

                competition = competitions[0]
                competitors = competition.get('competitors', [])

                if len(competitors) < 2:
                    continue

                # ESPN format: competitors[0] is home, competitors[1] is away
                home_competitor = competitors[0] if competitors[0].get('homeAway') == 'home' else competitors[1]
                away_competitor = competitors[1] if competitors[0].get('homeAway') == 'home' else competitors[0]

                home_abbr = home_competitor.get('team', {}).get('abbreviation', '')
                away_abbr = away_competitor.get('team', {}).get('abbreviation', '')

                # Get game status/time
                status = event.get('status', {}).get('type', {}).get('shortDetail', 'TBD')

                # Convert abbreviations to full team names
                home_team_name = self._espn_abbr_to_full_name(home_abbr)
                away_team_name = self._espn_abbr_to_full_name(away_abbr)

                schedule.append({
                    'game_id': event_id,
                    'away_team': away_team_name,
                    'home_team': home_team_name,
                    'game_time': status
                })

            print(f"\nFound {len(schedule)} game(s) today:\n")
            for i, game in enumerate(schedule, 1):
                print(f"{i}. {game['away_team']} @ {game['home_team']} ({game['game_time']})")

            print("\n" + "=" * 80)

            return schedule

        except requests.RequestException as e:
            raise Exception(f"Failed to fetch schedule from ESPN API: {e}")
        except Exception as e:
            print(f"Error parsing schedule: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _espn_abbr_to_full_name(self, abbr: str) -> str:
        """
        Convert ESPN team abbreviation to full team name
        Handles differences between ESPN and nba_api abbreviations
        """
        # ESPN -> nba_api abbreviation mapping for mismatches
        espn_to_nba = {
            'WSH': 'WAS',  # Washington
            'UTAH': 'UTA',  # Utah
            'GS': 'GSW',    # Golden State
            'SA': 'SAS',    # San Antonio
            'NY': 'NYK',    # New York
            'NO': 'NOP'     # New Orleans
        }

        # Convert ESPN abbreviation if needed
        nba_abbr = espn_to_nba.get(abbr, abbr)

        # Find team by nba_api abbreviation
        for team in self.all_teams:
            if team['abbreviation'] == nba_abbr:
                return team['full_name']

        # Fallback: return original abbreviation if not found
        return abbr

    def pull_team_data(self, team_name: str) -> Dict:
        """
        Pull BOTH Last 5 games and Season Average data

        Returns:
            Dict with 'last5' and 'season' keys, each containing stat categories
        """
        team_id = self.get_team_id(team_name)
        team_data = {
            'last5': {},
            'season': {},
            'opponent_last5': {}
        }

        print(f"\nPulling data for {team_name}...")

        # Categories to pull
        categories = ['Base', 'Advanced', 'Four Factors', 'Misc', 'Scoring', 'Opponent']

        # Pull Last 5 games with pace adjustment
        print(f"  Fetching Last 5 games...")
        for category in categories:
            try:
                data = get_team_dashboard(team_id, last_n=5)
                team_data['last5'][category] = pd.Series(data.get(category, {})) if data else None
            except Exception as e:
                print(f"    Error fetching Last 5 {category}: {e}")
                team_data['last5'][category] = None

        # Pull Season Average with pace adjustment
        print(f"  Fetching Season Average...")
        for category in categories:
            try:
                data = get_team_dashboard(team_id, last_n=0)
                team_data['season'][category] = pd.Series(data.get(category, {})) if data else None
            except Exception as e:
                print(f"    Error fetching Season {category}: {e}")
                team_data['season'][category] = None

        # Pull Opponent stats for normalization (Last 5 opponents)
        print(f"  Fetching Opponent stats...")
        try:
            data = get_team_dashboard(team_id, last_n=5)
            team_data['opponent_last5'] = pd.Series(data.get('Opponent', {})) if data else None
        except Exception as e:
            print(f"    Error fetching Opponent stats: {e}")
            team_data['opponent_last5'] = None

        print(f"  Complete data loaded for {team_name}")
        return team_data

    # ============================================================================
    # STAGE 1 — RECENCY WEIGHTING
    # ============================================================================

    def stage1_recency_weighting(self, team_data: Dict) -> Dict:
        """
        Calculate adjusted stats using recency weighting:
        AdjStat = (Last5 * 0.65) + (SeasonAvg * 0.35)
        """
        adjusted_stats = {}

        # Key stats to adjust
        stats_to_adjust = [
            ('Advanced', 'OFF_RATING'),
            ('Advanced', 'DEF_RATING'),
            ('Advanced', 'PACE'),
            ('Four Factors', 'EFG_PCT'),
            ('Four Factors', 'TOV_PCT'),
            ('Four Factors', 'OREB_PCT'),
            ('Four Factors', 'FTA_RATE'),
            ('Four Factors', 'OPP_EFG_PCT'),
            ('Four Factors', 'OPP_TOV_PCT'),
            ('Four Factors', 'OPP_OREB_PCT'),
            ('Four Factors', 'OPP_FTA_RATE'),
            ('Base', 'FG3_PCT'),
            ('Base', 'FG_PCT'),
            ('Opponent', 'OPP_FG_PCT'),
            ('Opponent', 'OPP_FG3_PCT'),
            ('Misc', 'PTS_OFF_TOV'),
            ('Misc', 'PTS_2ND_CHANCE'),
            ('Misc', 'PTS_FB'),
            ('Misc', 'PTS_PAINT')
        ]

        for category, stat in stats_to_adjust:
            try:
                last5_val = team_data['last5'][category][stat] if team_data['last5'][category] is not None else 0
                season_val = team_data['season'][category][stat] if team_data['season'][category] is not None else 0

                adj_val = (last5_val * self.LAST5_WEIGHT) + (season_val * self.SEASON_WEIGHT)
                adjusted_stats[stat] = adj_val
            except (KeyError, TypeError):
                adjusted_stats[stat] = 0

        return adjusted_stats

    # ============================================================================
    # STAGE 2 — PACE DAMPENING
    # ============================================================================

    def stage2_pace_dampening(self, raw_pace: float) -> float:
        """
        Apply pace dampening:
        AdjPace = LeagueAvgPace + (TeamPace - LeagueAvgPace) * 0.6
        """
        return self.LEAGUE_AVG_PACE + (raw_pace - self.LEAGUE_AVG_PACE) * self.PACE_DAMPENING

    # ============================================================================
    # STAGE 3 — SHOOTING REGRESSION
    # ============================================================================

    def stage3_shooting_regression(self, team_data: Dict) -> Dict:
        """
        Shooting regression:
        Adj_Shooting = SeasonValue + (Last5Value - SeasonValue) * 0.25
        """
        shooting_stats = {}

        shooting_stats_to_regress = [
            ('Base', 'FG3_PCT'),
            ('Base', 'FG_PCT')
        ]

        for category, stat in shooting_stats_to_regress:
            try:
                last5_val = team_data['last5'][category][stat] if team_data['last5'][category] is not None else 0
                season_val = team_data['season'][category][stat] if team_data['season'][category] is not None else 0

                adj_shooting = season_val + (last5_val - season_val) * self.SHOOTING_REGRESSION
                shooting_stats[stat] = adj_shooting
            except (KeyError, TypeError):
                shooting_stats[stat] = 0

        return shooting_stats

    # ============================================================================
    # STAGE 4 — OPPONENT NORMALIZATION
    # ============================================================================

    def stage4_opponent_normalization(self, adj_offrtg: float, adj_defrtg: float,
                                     opponent_data: pd.Series) -> tuple:
        """
        Correct for strength of schedule:
        Adj_OFFRTG = Adj_OFFRTG - (Opp_DEFRTG - 115)
        Adj_DEFRTG = Adj_DEFRTG - (Opp_OFFRTG - 115)
        """
        try:
            # Opponent's defensive rating (how good their opponents' defenses were)
            opp_defrtg = opponent_data.get('OPP_DEF_RATING', self.LEAGUE_AVG_DEFRTG)
            # Opponent's offensive rating (how good their opponents' offenses were)
            opp_offrtg = opponent_data.get('OPP_OFF_RATING', self.LEAGUE_AVG_OFFRTG)

            normalized_offrtg = adj_offrtg - (opp_defrtg - self.LEAGUE_AVG_DEFRTG)
            normalized_defrtg = adj_defrtg - (opp_offrtg - self.LEAGUE_AVG_OFFRTG)

            return normalized_offrtg, normalized_defrtg
        except:
            return adj_offrtg, adj_defrtg

    # ============================================================================
    # STAGE 5 — PROJECTED POINTS CALCULATION
    # ============================================================================

    def stage5_projected_points(self, adj_offrtg: float, opp_adj_defrtg: float, adj_pace: float) -> float:
        """
        ProjectedPoints = Adj_OFFRTG / 100 * AdjPace
        """
        # Average the offensive rating against opponent's defensive rating
        effective_rtg = (adj_offrtg + opp_adj_defrtg) / 2
        return (effective_rtg / 100) * adj_pace

    # ============================================================================
    # STAGE 6 — HOME COURT ADJUSTMENT
    # ============================================================================

    def stage6_home_court(self, team_a_points: float, team_b_points: float,
                         team_a_is_home: bool) -> tuple:
        """
        Apply home court advantage:
        If team is HOME: ProjectedPoints += 1.8, OpponentProjectedPoints -= 1.8
        """
        if team_a_is_home:
            team_a_points += self.HOME_COURT_ADJ
            team_b_points -= self.HOME_COURT_ADJ
        else:
            team_a_points -= self.HOME_COURT_ADJ
            team_b_points += self.HOME_COURT_ADJ

        return team_a_points, team_b_points

    # ============================================================================
    # STAGE 7 — FINAL OUTPUT METRICS
    # ============================================================================

    def stage7_final_metrics(self, team_a_points: float, team_b_points: float,
                            home_team: str, away_team: str) -> Dict:
        """
        Calculate spread and total
        TrueSpread = HomeTeamPoints - AwayTeamPoints (from home team perspective)
        Total = ProjectedPoints + OpponentProjectedPoints
        """
        # Spread from home team perspective
        spread = team_a_points - team_b_points
        total = team_a_points + team_b_points

        return {
            'home_team': home_team,
            'away_team': away_team,
            'home_projected_score': round(team_a_points, 1),
            'away_projected_score': round(team_b_points, 1),
            'spread': round(spread, 1),  # Positive = home team favored
            'total': round(total, 1)
        }

    # ============================================================================
    # STAGE 8 — UPSIDE / RISK FACTORS
    # ============================================================================

    def stage8_variance_flags(self, team_a_stats: Dict, team_b_stats: Dict,
                             team_a_adj: Dict, team_b_adj: Dict) -> List[str]:
        """
        Flag high-variance games when:
        - TOV% difference > 4%
        - 3P rate (3PA%) is extreme
        - Pace between teams differs by > 4
        - Defensive rating gap > 6
        """
        flags = []

        # TOV% difference
        tov_diff = abs(team_a_adj.get('TOV_PCT', 0) - team_b_adj.get('TOV_PCT', 0))
        if tov_diff > 4.0:
            flags.append(f"⚠️  HIGH TURNOVER VARIANCE (Diff: {tov_diff:.1f}%)")

        # Pace difference
        pace_diff = abs(team_a_adj.get('PACE', 0) - team_b_adj.get('PACE', 0))
        if pace_diff > 4.0:
            flags.append(f"⚠️  PACE MISMATCH (Diff: {pace_diff:.1f})")

        # Defensive rating gap
        def_diff = abs(team_a_adj.get('DEF_RATING', 0) - team_b_adj.get('DEF_RATING', 0))
        if def_diff > 6.0:
            flags.append(f"⚠️  DEFENSIVE GAP (Diff: {def_diff:.1f})")

        # 3P rate check (using FG3A from Base stats)
        try:
            team_a_3pa = team_a_stats['last5']['Base']['FG3A'] if team_a_stats['last5']['Base'] is not None else 0
            team_b_3pa = team_b_stats['last5']['Base']['FG3A'] if team_b_stats['last5']['Base'] is not None else 0

            if team_a_3pa > 40 or team_b_3pa > 40:
                flags.append(f"⚠️  EXTREME 3-POINT VOLUME (Team A: {team_a_3pa:.1f}, Team B: {team_b_3pa:.1f})")
        except:
            pass

        if not flags:
            flags.append("✓ Standard variance game")

        return flags

    # ============================================================================
    # FULL PROJECTION
    # ============================================================================

    def project_game(self, home_team: str, away_team: str) -> Dict:
        """
        Run full 8-stage projection for a single game
        """
        print(f"\n{'='*80}")
        print(f"PROJECTING: {away_team} @ {home_team}")
        print(f"{'='*80}")

        # Pull data
        home_data = self.pull_team_data(home_team)
        away_data = self.pull_team_data(away_team)

        # Stage 1: Recency weighting
        home_adj = self.stage1_recency_weighting(home_data)
        away_adj = self.stage1_recency_weighting(away_data)

        # Stage 2: Pace dampening
        home_pace_raw = home_adj['PACE']
        away_pace_raw = away_adj['PACE']

        home_pace = self.stage2_pace_dampening(home_pace_raw)
        away_pace = self.stage2_pace_dampening(away_pace_raw)

        game_pace = (home_pace + away_pace) / 2

        # Stage 3: Shooting regression
        home_shooting = self.stage3_shooting_regression(home_data)
        away_shooting = self.stage3_shooting_regression(away_data)

        # Stage 4: Opponent normalization
        home_offrtg_norm, home_defrtg_norm = self.stage4_opponent_normalization(
            home_adj['OFF_RATING'], home_adj['DEF_RATING'],
            home_data['opponent_last5'] if home_data['opponent_last5'] is not None else pd.Series()
        )
        away_offrtg_norm, away_defrtg_norm = self.stage4_opponent_normalization(
            away_adj['OFF_RATING'], away_adj['DEF_RATING'],
            away_data['opponent_last5'] if away_data['opponent_last5'] is not None else pd.Series()
        )

        # Stage 5: Projected points (before home court)
        home_points = self.stage5_projected_points(home_offrtg_norm, away_defrtg_norm, game_pace)
        away_points = self.stage5_projected_points(away_offrtg_norm, home_defrtg_norm, game_pace)

        # Stage 6: Home court adjustment
        home_points, away_points = self.stage6_home_court(home_points, away_points, team_a_is_home=True)

        # Stage 7: Final metrics
        final_metrics = self.stage7_final_metrics(home_points, away_points, home_team, away_team)

        # Stage 8: Variance flags
        variance_flags = self.stage8_variance_flags(home_data, away_data, home_adj, away_adj)

        # Compile full projection
        projection = {
            **final_metrics,
            'game_pace': round(game_pace, 1),
            'home_offrtg': round(home_offrtg_norm, 1),
            'home_defrtg': round(home_defrtg_norm, 1),
            'away_offrtg': round(away_offrtg_norm, 1),
            'away_defrtg': round(away_defrtg_norm, 1),
            'variance_flags': variance_flags
        }

        return projection

    def print_projection(self, projection: Dict):
        """
        Print formatted projection
        """
        print(f"\n{'='*80}")
        print(f"PROJECTION: {projection['away_team']} @ {projection['home_team']}")
        print(f"{'='*80}")

        print(f"\nPROJECTED SCORES:")
        print(f"  {projection['home_team']}: {projection['home_projected_score']}")
        print(f"  {projection['away_team']}: {projection['away_projected_score']}")

        print(f"\nTRUE VALUES - NO VEGAS INFLUENCE:")
        if projection['spread'] > 0:
            print(f"  Spread: {projection['home_team']} -{abs(projection['spread'])}")
        elif projection['spread'] < 0:
            print(f"  Spread: {projection['away_team']} -{abs(projection['spread'])}")
        else:
            print(f"  Spread: EVEN")

        print(f"  Total: {projection['total']}")
        print(f"  Game Pace: {projection['game_pace']}")

        print(f"\nTEAM RATINGS:")
        print(f"  {projection['home_team']}: OffRtg {projection['home_offrtg']} | DefRtg {projection['home_defrtg']}")
        print(f"  {projection['away_team']}: OffRtg {projection['away_offrtg']} | DefRtg {projection['away_defrtg']}")

        print(f"\nVARIANCE FLAGS:")
        for flag in projection['variance_flags']:
            print(f"  {flag}")

        print(f"\n{'='*80}\n")

    def project_all_games(self):
        """
        Project all games on today's schedule
        """
        schedule = self.get_todays_schedule()

        if not schedule:
            print("No games to project.")
            return

        projections = []

        for game in schedule:
            projection = self.project_game(game['home_team'], game['away_team'])
            projections.append(projection)
            self.print_projection(projection)

        return projections


if __name__ == "__main__":
    # Run model on today's games
    model = NBAStatisticalModel()
    model.project_all_games()
