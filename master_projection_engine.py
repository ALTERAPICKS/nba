"""
NBA Master Projection Engine
Integrates injury data + player impacts into team-level projections

THE MASTER PIPELINE (7 Steps + Optional Modules):
STEP 1: Load baseline team stats (OffRtg, DefRtg, Pace)
STEP 2: Run injury module → availability flags only
STEP 3: Run player stats module → base impacts
STEP 4: Apply Vegas modules → final player-level impacts
STEP 5: Merge injuries + players (KEY INTEGRATION)
STEP 6: Adjust team ratings
STEP 7: Project game using adjusted ratings
STEP 8: Apply rest adjustment (OPTIONAL) → rest-adjusted spread
STEP 9: Apply pace adjustment (OPTIONAL) → pace-adjusted total
"""

import sys
import time
import requests
import pandas as pd
from typing import Dict, List, Tuple
from datetime import datetime
from nba_api.stats.static import teams
from nba_api.stats.endpoints import (
    commonteamroster,
    playercareerstats
)

# API Wrapper Configuration
BASE_URL = "https://nba-e6du.onrender.com"

def warm_up_api():
    try:
        print("Warming up Render API...")
        requests.get(f"{BASE_URL}/health", timeout=10)
        time.sleep(10)  # allow Render + nba_api to fully wake
    except Exception as e:
        print(f"Warm-up warning: {e}")

def get_team_dashboard(team_id, last_n):
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

    # If we get here, all retries failed
    raise RuntimeError(f"Failed to fetch dashboard for team {team_id}")


from injury_processor import InjuryProcessor
from player_stats_processor import PlayerStatsProcessor
from rest_adjustment_module import RestAdjustmentModule
from pace_adjustment_module import PaceAdjustmentModule

# Performance tracking imports
try:
    from pathlib import Path as _Path
    # Add model_performance to path if needed
    perf_module_path = _Path(__file__).parent / 'model_performance'
    if str(perf_module_path) not in sys.path:
        sys.path.insert(0, str(perf_module_path))

    from outcome_fetcher import OutcomeFetcher
    from save_predictions_helper import save_predictions
    PERFORMANCE_TRACKING_ENABLED = True
except ImportError as e:
    PERFORMANCE_TRACKING_ENABLED = False
    print(f"⚠ Performance tracking not available: {e}")


class MasterProjectionEngine:
    """
    Master integration engine that combines:
    - Baseline team statistics
    - Injury availability data
    - Player impact calculations
    - Vegas refinements
    Into injury-adjusted game projections
    """

    # Constants from statistical model
    SEASON = '2025-26'
    LEAGUE_AVG_PACE = 98.5
    LEAGUE_AVG_OFF_RATING = 114.0
    LEAGUE_AVG_DEF_RATING = 114.0
    HOME_COURT_ADJ = 1.8

    # Recency weighting
    LAST5_WEIGHT = 0.65
    SEASON_WEIGHT = 0.35

    # Pace dampening
    PACE_DAMPENING = 0.6

    def __init__(self):
        """Initialize all processors"""
        self.injury_processor = InjuryProcessor()
        self.player_processor = PlayerStatsProcessor()
        self.rest_module = RestAdjustmentModule(season=self.SEASON)
        self.pace_module = PaceAdjustmentModule(league_avg_pace=self.LEAGUE_AVG_PACE)
        self.all_teams = teams.get_teams()
        print("✓ Master Projection Engine initialized")
        print("  - Injury Processor loaded")
        print("  - Player Stats Processor loaded")
        print("  - Rest Adjustment Module loaded")
        print("  - Pace Adjustment Module loaded")
        print("  - Statistical Model constants loaded\n")

    def get_team_name_by_id(self, team_id: int) -> str:
        """Get team name from team ID"""
        for team in self.all_teams:
            if team['id'] == team_id:
                return team['full_name']
        return "Unknown Team"

    def get_team_id(self, team_name: str) -> int:
        """Get team ID from team name"""
        for team in self.all_teams:
            if team_name.lower() in team['full_name'].lower() or \
               team_name.lower() in team['nickname'].lower() or \
               team_name.lower() in team['abbreviation'].lower():
                return team['id']
        raise ValueError(f"Team '{team_name}' not found")

    def step_1_load_baseline_stats(self, team_name: str) -> Dict:
        """
        STEP 1: Load baseline team stats (OffRtg, DefRtg, Pace)

        Args:
            team_name: Full NBA team name

        Returns:
            Dict with baseline stats
        """
        print(f"  [STEP 1] Loading baseline stats for {team_name}...")

        team_id = self.get_team_id(team_name)

        # Fetch season stats
        season_data = get_team_dashboard(team_id, last_n=0)
        team_season = pd.Series(season_data.get('Advanced', {}))

        # Fetch Last 5 stats
        last5_data = get_team_dashboard(team_id, last_n=5)
        team_last5 = pd.Series(last5_data.get('Advanced', {}))

        # Apply recency weighting
        off_rtg_weighted = (team_last5['OFF_RATING'] * self.LAST5_WEIGHT +
                           team_season['OFF_RATING'] * self.SEASON_WEIGHT)
        def_rtg_weighted = (team_last5['DEF_RATING'] * self.LAST5_WEIGHT +
                           team_season['DEF_RATING'] * self.SEASON_WEIGHT)
        pace_weighted = (team_last5['PACE'] * self.LAST5_WEIGHT +
                        team_season['PACE'] * self.SEASON_WEIGHT)

        # Apply pace dampening
        pace_dampened = self.LEAGUE_AVG_PACE + (pace_weighted - self.LEAGUE_AVG_PACE) * self.PACE_DAMPENING

        baseline = {
            'team_name': team_name,
            'off_rating_base': round(off_rtg_weighted, 2),
            'def_rating_base': round(def_rtg_weighted, 2),
            'pace_base': round(pace_dampened, 2)
        }

        print(f"    ✓ OffRtg: {baseline['off_rating_base']}")
        print(f"    ✓ DefRtg: {baseline['def_rating_base']}")
        print(f"    ✓ Pace: {baseline['pace_base']}")

        return baseline

    def step_2_get_injury_report(self, team_name: str, injury_adjustment: bool = True) -> Dict:
        """
        STEP 2: Run injury module → availability flags only (OPTIONAL)

        Args:
            team_name: Full NBA team name
            injury_adjustment: Enable injury processing (default: True)

        Returns:
            Injury report with availability flags (or empty if disabled)
        """
        if not injury_adjustment:
            print(f"  [STEP 2] Injury adjustment disabled - skipping injury fetch")
            return {
                'team': team_name,
                'injury_report': [],
                'report_timestamp': datetime.now().isoformat()
            }

        print(f"  [STEP 2] Fetching injury report for {team_name}...")

        report = self.injury_processor.generate_injury_report(team_name)

        unavailable_count = sum(1 for p in report['injury_report']
                               if p['model_status'] == 'unavailable')

        print(f"    ✓ Total injuries reported: {len(report['injury_report'])}")
        print(f"    ✓ Unavailable players: {unavailable_count}")

        return report

    def step_3_get_player_impacts(self, team_name: str) -> List[Dict]:
        """
        STEP 3: Run player stats module → base impacts

        Args:
            team_name: Full NBA team name

        Returns:
            List of player impact reports
        """
        print(f"  [STEP 3] Processing player impacts for {team_name}...")

        team_id = self.get_team_id(team_name)
        player_impacts = []

        try:
            # Fetch team roster
            roster = commonteamroster.CommonTeamRoster(
                team_id=team_id,
                season=self.SEASON
            )
            roster_df = roster.get_data_frames()[0]

            print(f"    → Roster fetched: {len(roster_df)} players")

            # Process ALL players - let the 4-filter system identify key players
            top_players = roster_df  # Process entire roster

            print(f"    → Processing all {len(top_players)} players...")

            # Process each player
            for idx, player_row in top_players.iterrows():
                player_id = player_row['PLAYER_ID']
                player_name = player_row['PLAYER']
                position = player_row.get('POSITION', 'F')  # Default to F if missing

                # Rate limiting
                if idx > 0:
                    time.sleep(0.6)  # 600ms between requests

                try:
                    # Fetch player career stats
                    career_stats = playercareerstats.PlayerCareerStats(player_id=player_id)
                    career_df = career_stats.get_data_frames()[0]

                    # Get 2025-26 season stats
                    season_stats = career_df[career_df['SEASON_ID'] == self.SEASON]

                    if len(season_stats) == 0:
                        continue

                    stats = season_stats.iloc[0]

                    # Extract required stats for processing
                    games_played = stats['GP']
                    total_minutes = stats['MIN']
                    minutes_per_game = total_minutes / games_played if games_played > 0 else 0

                    # Usage rate approximation from box score stats
                    fga = stats.get('FGA', 0)
                    fta = stats.get('FTA', 0)
                    tov = stats.get('TOV', 0)
                    # Usage% ≈ (FGA + 0.44*FTA + TOV) / (Team Minutes / 5)
                    # Simplified: (FGA + 0.44*FTA + TOV) / Minutes * 48
                    usage_rate = ((fga + 0.44 * fta + tov) / total_minutes * 48) if total_minutes > 0 else 0

                    # Net rating approximation from +/-
                    # Career stats don't have PLUS_MINUS, so we'll estimate from points/efficiency
                    pts = stats.get('PTS', 0)
                    ppg = pts / games_played if games_played > 0 else 0
                    # Rough net rating estimate: scale PPG to approximate impact
                    net_rating = (ppg - 15) / 3  # Simplified: avg scorer (15ppg) = 0, elite (30ppg) = +5

                    # For last 10 games usage, use season for now
                    usage_rate_last_10 = usage_rate

                    # Estimate ON-COURT impact from basic stats (not raw ratings)
                    # These should be small differentials (±3 to ±8 range), not full ratings
                    fg_pct = stats.get('FG_PCT', 0.45)
                    ppg = stats.get('PTS', 15.0) / games_played if games_played > 0 else 15.0

                    # Offensive impact: based on scoring efficiency and volume
                    # Good scorers: +2 to +5, Poor scorers: -2 to -5
                    scoring_efficiency = (fg_pct - 0.45) * 10  # FG% above/below average
                    volume_bonus = min((ppg - 15) / 5, 3)  # Bonus for high scoring (capped at +3)
                    off_impact = scoring_efficiency + volume_bonus

                    # Defensive impact: use approximation from net rating
                    # Split net rating 60/40 between offense and defense
                    def_impact = net_rating * 0.4

                    # Convert to "on-court rating" format (league avg + impact)
                    off_rating = self.LEAGUE_AVG_OFF_RATING + off_impact
                    def_rating = self.LEAGUE_AVG_DEF_RATING + def_impact

                    # Calculate minutes per game
                    mpg = total_minutes / games_played if games_played > 0 else 0

                    # Build player stats dict - MUST match keys expected by player_stats_processor
                    player_stat_dict = {
                        'player_name': player_name,
                        'minutes_played_season': total_minutes,
                        'minutes_per_game': mpg,
                        'games_played': games_played,
                        'usage_rate': usage_rate,  # PRIMARY KEY - required by player_stats_processor
                        'usage_rate_season': usage_rate,
                        'usage_rate_last_10': usage_rate_last_10,
                        'net_rating': net_rating,
                        'off_rating_oncourt': off_rating,  # MUST be '_oncourt' suffix
                        'def_rating_oncourt': def_rating   # MUST be '_oncourt' suffix
                    }

                    # Process through player stats processor
                    # Default Vegas module values (can be enhanced later)
                    result = self.player_processor.process_player(
                        player_stats=player_stat_dict,
                        team_name=team_name,
                        position=position,
                        starter_overlap_pct=100.0,  # Default assumption
                        is_rim_protector=(position == 'C'),
                        is_poa_defender=(position == 'G')
                    )

                    player_impacts.append(result)

                    # DEBUG: Show filter results for top 3 players
                    if len(player_impacts) <= 3:
                        print(f"      [{player_name}] Eligible: {result['eligible']}, Tier: {result['tier']}")
                        if not result['eligible']:
                            filters = result.get('filter_results', {})
                            print(f"        Filter A (>300min): {filters.get('min_minutes', '?')}, Filter B (usage stable): {filters.get('usage_stable', '?')}, Filter C (|net|>1.5): {filters.get('strong_onoff', '?')}, Filter D (T1/T2): {filters.get('tier_eligible', '?')}")
                            print(f"        Stats: Usage={usage_rate:.1f}%, MPG={mpg:.1f}, Net={net_rating:+.2f}, Min={total_minutes:.0f}, Games={games_played}")

                except Exception as e:
                    # Skip players that fail (probably didn't play enough)
                    print(f"      ⚠ Skipped {player_name}: {str(e)[:60]}")
                    continue

            eligible_count = sum(1 for p in player_impacts if p['eligible'])
            print(f"    ✓ Player impacts calculated: {len(player_impacts)} total, {eligible_count} eligible")

        except Exception as e:
            print(f"    ❌ Error fetching roster: {e}")
            player_impacts = []

        return player_impacts

    def step_4_apply_vegas_modules(self, player_impacts: List[Dict]) -> List[Dict]:
        """
        STEP 4: Apply Vegas modules → final player-level impacts

        Vegas Module #1: Lineup Dependency Weighting
        Vegas Module #2: Position-Based Defensive Weighting
        Vegas Module #3: Sample-Size Dampening

        Args:
            player_impacts: List of base player impacts

        Returns:
            List of Vegas-adjusted player impacts
        """
        print(f"  [STEP 4] Applying Vegas modules to {len(player_impacts)} players...")

        # Vegas adjustments are already integrated into player_stats_processor.py
        # This step is essentially already done in step 3

        print(f"    ✓ Vegas adjustments applied")

        return player_impacts

    def step_5_merge_injuries_and_impacts(self, injury_report: Dict,
                                         player_impacts: List[Dict],
                                         injury_adjustment: bool = True) -> Dict:
        """
        STEP 5: Merge injuries + players (KEY INTEGRATION) - OPTIONAL

        Critical Logic:
        for each player:
            if eligible == True and model_status == "unavailable":
                off_adjustment += -off_impact
                def_adjustment += -def_impact

        Args:
            injury_report: Injury report from step 2
            player_impacts: Player impacts from steps 3+4
            injury_adjustment: Enable injury impact processing (default: True)

        Returns:
            Dict with team adjustments and breakdown
        """
        if not injury_adjustment:
            print(f"  [STEP 5] Injury adjustment disabled - no adjustments applied")
            return {
                'off_adjustment': 0.0,
                'def_adjustment': 0.0,
                'impact_breakdown': []
            }

        print(f"  [STEP 5] Merging injuries + player impacts...")

        off_adjustment = 0.0
        def_adjustment = 0.0
        impact_breakdown = []

        # Create lookup dictionary for player impacts
        impact_lookup = {p['player_name']: p for p in player_impacts}

        # Process each injured player
        for injury in injury_report['injury_report']:
            player_name = injury['player_name']
            model_status = injury['model_status']

            # Check if we have impact data for this player
            if player_name in impact_lookup:
                player_data = impact_lookup[player_name]
                eligible = player_data['eligible']

                # KEY LOGIC: If eligible AND unavailable, flip and apply impact
                if eligible and model_status == 'unavailable':
                    off_impact = player_data['off_impact']
                    def_impact = player_data['def_impact']

                    # FLIP THE IMPACT (removing player)
                    off_adjustment += -off_impact
                    def_adjustment += -def_impact

                    impact_breakdown.append({
                        'player_name': player_name,
                        'espn_status': injury['espn_status'],
                        'eligible': True,
                        'off_impact': off_impact,
                        'def_impact': def_impact,
                        'off_adjustment': -off_impact,
                        'def_adjustment': -def_impact
                    })

                    print(f"    ✓ {player_name} (OUT) - Off: {-off_impact:+.2f}, Def: {-def_impact:+.2f}")

        print(f"    ✓ Total Off Adjustment: {off_adjustment:+.2f}")
        print(f"    ✓ Total Def Adjustment: {def_adjustment:+.2f}")

        return {
            'off_adjustment': round(off_adjustment, 2),
            'def_adjustment': round(def_adjustment, 2),
            'impact_breakdown': impact_breakdown
        }

    def step_6_adjust_team_ratings(self, baseline: Dict, adjustments: Dict) -> Dict:
        """
        STEP 6: Adjust team ratings

        OffRtg_Final = OffRtg_Base + off_adjustment
        DefRtg_Final = DefRtg_Base + def_adjustment

        Args:
            baseline: Baseline stats from step 1
            adjustments: Adjustments from step 5

        Returns:
            Final adjusted ratings
        """
        print(f"  [STEP 6] Adjusting team ratings...")

        off_rtg_final = baseline['off_rating_base'] + adjustments['off_adjustment']
        def_rtg_final = baseline['def_rating_base'] + adjustments['def_adjustment']

        adjusted = {
            'team_name': baseline['team_name'],
            'off_rating_base': baseline['off_rating_base'],
            'def_rating_base': baseline['def_rating_base'],
            'pace_base': baseline['pace_base'],
            'off_adjustment': adjustments['off_adjustment'],
            'def_adjustment': adjustments['def_adjustment'],
            'off_rating_final': round(off_rtg_final, 2),
            'def_rating_final': round(def_rtg_final, 2),
            'pace_final': baseline['pace_base']  # Pace doesn't change
        }

        print(f"    ✓ Final OffRtg: {adjusted['off_rating_final']} ({adjusted['off_adjustment']:+.2f})")
        print(f"    ✓ Final DefRtg: {adjusted['def_rating_final']} ({adjusted['def_adjustment']:+.2f})")

        return adjusted

    def step_7_project_game(self, home_adjusted: Dict, away_adjusted: Dict) -> Dict:
        """
        STEP 7: Project game using adjusted ratings

        Args:
            home_adjusted: Home team adjusted ratings
            away_adjusted: Away team adjusted ratings

        Returns:
            Game projection with spread and total
        """
        print(f"  [STEP 7] Projecting game...")

        # Calculate average pace
        avg_pace = (home_adjusted['pace_final'] + away_adjusted['pace_final']) / 2

        # Project possessions (simplified - actual model uses more complex formula)
        possessions = avg_pace

        # Project points (with home court adjustment)
        home_points = (home_adjusted['off_rating_final'] + away_adjusted['def_rating_final']) / 2
        home_points = (home_points / 100) * possessions + self.HOME_COURT_ADJ

        away_points = (away_adjusted['off_rating_final'] + home_adjusted['def_rating_final']) / 2
        away_points = (away_points / 100) * possessions

        # Calculate total
        total = round(home_points + away_points, 1)

        # Determine favorite (team with higher projected score)
        # Favorite gets negative spread, underdog gets positive spread
        point_differential = abs(home_points - away_points)

        if home_points > away_points:
            # Home team is favorite
            favorite_team = home_adjusted['team_name']
            favorite_spread = -round(point_differential, 1)
            underdog_team = away_adjusted['team_name']
            underdog_spread = round(point_differential, 1)
        else:
            # Away team is favorite
            favorite_team = away_adjusted['team_name']
            favorite_spread = -round(point_differential, 1)
            underdog_team = home_adjusted['team_name']
            underdog_spread = round(point_differential, 1)

        projection = {
            'home_team': home_adjusted['team_name'],
            'away_team': away_adjusted['team_name'],
            'home_points': round(home_points, 1),
            'away_points': round(away_points, 1),
            'favorite_team': favorite_team,
            'favorite_spread': favorite_spread,
            'underdog_team': underdog_team,
            'underdog_spread': underdog_spread,
            'total': total,
            'possessions': round(possessions, 1)
        }

        # Display spread for BOTH teams (home and away)
        if home_points > away_points:
            home_spread = favorite_spread  # Negative (home is favorite)
            away_spread = underdog_spread  # Positive (away is underdog)
        else:
            home_spread = underdog_spread  # Positive (home is underdog)
            away_spread = favorite_spread  # Negative (away is favorite)

        print(f"    ✓ Spread: {home_adjusted['team_name']} {home_spread:+.1f} / {away_adjusted['team_name']} {away_spread:+.1f}")
        print(f"    ✓ Total: {projection['total']}")
        print(f"    ✓ Score: {home_adjusted['team_name']} {projection['home_points']} - {away_adjusted['team_name']} {projection['away_points']}")

        return projection

    def step_8_apply_rest_adjustment(self, projection: Dict, home_team: str,
                                     away_team: str, game_date: datetime,
                                     rest_adjustment: bool = True) -> Dict:
        """
        STEP 8: Apply rest adjustment to baseline spread (OPTIONAL MODULE)

        This step adjusts the baseline spread based on each team's rest days.
        It runs AFTER step 7 produces the baseline projection.

        Args:
            projection: Baseline projection from step 7
            home_team: Home team name
            away_team: Away team name
            game_date: Date of current game
            rest_adjustment: Toggle to enable/disable rest adjustment

        Returns:
            Dict with rest adjustment details and final spread
        """
        if not rest_adjustment:
            print(f"  [STEP 8] Rest adjustment disabled")
            return {
                'rest_adjustment_enabled': False,
                'rest_days_home': None,
                'rest_days_away': None,
                'rest_adj_home': 0.0,
                'rest_adj_away': 0.0,
                'baseline_spread': projection.get('favorite_spread', 0.0),
                'rest_module_spread': projection.get('favorite_spread', 0.0)
            }

        print(f"  [STEP 8] Applying rest adjustment...")

        # Get team IDs
        home_team_id = self.get_team_id(home_team)
        away_team_id = self.get_team_id(away_team)

        # Calculate baseline spread (home perspective: negative = home favored)
        home_points = projection['home_points']
        away_points = projection['away_points']
        baseline_spread = away_points - home_points  # Negative if home favored

        # Apply rest adjustment
        rest_result = self.rest_module.apply_rest_adjustment(
            baseline_spread=baseline_spread,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            game_date=game_date,
            rest_adjustment_enabled=rest_adjustment
        )

        # Display results
        print(f"    Rest Days: {home_team} = {rest_result['rest_days_home']}, {away_team} = {rest_result['rest_days_away']}")
        print(f"    Rest Adj: {home_team} = {rest_result['rest_adj_home']:+.2f}, {away_team} = {rest_result['rest_adj_away']:+.2f}")
        print(f"    Baseline Spread: {baseline_spread:+.1f}")
        print(f"    Rest-Adjusted Spread: {rest_result['rest_module_spread']:+.1f}")
        print(f"    ✓ Rest adjustment applied")

        return rest_result

    def step_9_apply_pace_adjustment(self, projection: Dict, home_adjusted: Dict,
                                     away_adjusted: Dict, pace_adjustment: bool = True) -> Dict:
        """
        STEP 9: Apply pace adjustment to baseline total (OPTIONAL MODULE)

        This step adjusts the baseline total based on team pace interaction.
        It runs AFTER step 7 produces the baseline projection.
        This does NOT modify the spread - ONLY the total.

        Args:
            projection: Baseline projection from step 7
            home_adjusted: Home team adjusted ratings
            away_adjusted: Away team adjusted ratings
            pace_adjustment: Toggle to enable/disable pace adjustment

        Returns:
            Dict with pace adjustment details and final total
        """
        if not pace_adjustment:
            print(f"  [STEP 9] Pace adjustment disabled")
            return {
                'pace_adjustment_enabled': False,
                'pace_delta': 0.0,
                'pace_total_adj': 0.0,
                'baseline_total': projection['total'],
                'pace_module_total': projection['total']
            }

        print(f"  [STEP 9] Applying pace adjustment...")

        # Get team pace values
        home_pace = home_adjusted['pace_final']
        away_pace = away_adjusted['pace_final']
        baseline_total = projection['total']

        # Apply pace adjustment
        pace_result = self.pace_module.apply_pace_adjustment(
            baseline_total=baseline_total,
            home_pace=home_pace,
            away_pace=away_pace,
            pace_adjustment_enabled=pace_adjustment
        )

        # Display results
        print(f"    Team Pace: Home={home_pace:.1f}, Away={away_pace:.1f}, League Avg={self.LEAGUE_AVG_PACE:.1f}")
        print(f"    Pace Delta: {pace_result['pace_delta']:+.2f}")
        print(f"    Pace Total Adj: {pace_result['pace_total_adj']:+.1f}")
        print(f"    Baseline Total: {baseline_total:.1f}")
        print(f"    Pace-Adjusted Total: {pace_result['pace_module_total']:.1f}")
        print(f"    ✓ Pace adjustment applied")

        return pace_result

    def run_full_pipeline(self, home_team: str, away_team: str,
                          injury_adjustment: bool = True,
                          rest_adjustment: bool = True,
                          pace_adjustment: bool = True) -> Dict:
        """
        Execute complete pipeline for a matchup (7 steps baseline + optional modules)

        Args:
            home_team: Home team name
            away_team: Away team name
            injury_adjustment: Enable injury impact processing (default: True)
            rest_adjustment: Enable rest adjustment module (default: True)
            pace_adjustment: Enable pace adjustment module (default: True)

        Returns:
            Complete projection with baseline and adjusted values
        """
        print(f"\n{'='*80}")
        print(f"MASTER PROJECTION PIPELINE")
        print(f"Matchup: {away_team} @ {home_team}")
        print(f"{'='*80}\n")

        # Process home team
        print(f"📊 PROCESSING HOME TEAM: {home_team}")
        print("-" * 80)
        home_baseline = self.step_1_load_baseline_stats(home_team)
        home_injuries = self.step_2_get_injury_report(home_team, injury_adjustment)
        home_player_impacts = self.step_3_get_player_impacts(home_team)
        home_player_impacts = self.step_4_apply_vegas_modules(home_player_impacts)
        home_adjustments = self.step_5_merge_injuries_and_impacts(home_injuries, home_player_impacts, injury_adjustment)
        home_adjusted = self.step_6_adjust_team_ratings(home_baseline, home_adjustments)

        print(f"\n📊 PROCESSING AWAY TEAM: {away_team}")
        print("-" * 80)
        away_baseline = self.step_1_load_baseline_stats(away_team)
        away_injuries = self.step_2_get_injury_report(away_team, injury_adjustment)
        away_player_impacts = self.step_3_get_player_impacts(away_team)
        away_player_impacts = self.step_4_apply_vegas_modules(away_player_impacts)
        away_adjustments = self.step_5_merge_injuries_and_impacts(away_injuries, away_player_impacts, injury_adjustment)
        away_adjusted = self.step_6_adjust_team_ratings(away_baseline, away_adjustments)

        # Project game
        print(f"\n🎯 FINAL PROJECTION")
        print("-" * 80)
        projection = self.step_7_project_game(home_adjusted, away_adjusted)

        # Apply rest adjustment (optional module)
        rest_result = self.step_8_apply_rest_adjustment(
            projection=projection,
            home_team=home_team,
            away_team=away_team,
            game_date=datetime.now(),
            rest_adjustment=rest_adjustment
        )

        # Apply pace adjustment (optional module)
        pace_result = self.step_9_apply_pace_adjustment(
            projection=projection,
            home_adjusted=home_adjusted,
            away_adjusted=away_adjusted,
            pace_adjustment=pace_adjustment
        )

        return {
            'home_adjusted': home_adjusted,
            'away_adjusted': away_adjusted,
            'projection': projection,
            'rest_adjustment': rest_result,
            'pace_adjustment': pace_result,
            'home_injury_breakdown': home_adjustments['impact_breakdown'],
            'away_injury_breakdown': away_adjustments['impact_breakdown']
        }

    def get_todays_games(self) -> List[Tuple[str, str]]:
        """
        Fetch today's NBA schedule
        Uses ESPN's public scoreboard API (reliable in cloud environments)

        Returns:
            List of (away_team, home_team) tuples
        """
        print("Fetching today's NBA schedule...")

        try:
            # Fetch from ESPN's public scoreboard API
            url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            data = response.json()
            events = data.get('events', [])

            if len(events) == 0:
                print("No games scheduled for today.\n")
                return []

            matchups = []

            for event in events:
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

                # Convert abbreviations to full team names
                home_team = self._espn_abbr_to_full_name(home_abbr)
                away_team = self._espn_abbr_to_full_name(away_abbr)

                matchups.append((away_team, home_team))

            print(f"✓ Found {len(matchups)} games today\n")
            return matchups

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

    def project_all_games(self):
        """
        Run full pipeline on all games today

        warm_up_api()

        Also evaluates yesterday's predictions and saves today's predictions
        """
        print(f"\n{'='*80}")
        print(f"NBA MASTER PROJECTION ENGINE - {datetime.now().strftime('%B %d, %Y')}")
        print(f"{'='*80}\n")

        # STEP 0: Evaluate yesterday's predictions (if performance tracking enabled)
        if PERFORMANCE_TRACKING_ENABLED:
            print(f"\n{'='*80}")
            print(f"EVALUATING YESTERDAY'S PREDICTIONS")
            print(f"{'='*80}")
            try:
                fetcher = OutcomeFetcher()
                fetcher.update_performance_log()
            except Exception as e:
                print(f"⚠ Could not evaluate yesterday's predictions: {e}")
                print("Continuing with today's projections...\n")

        matchups = self.get_todays_games()

        if not matchups:
            print("No games scheduled today.")
            return

        all_projections = []

        for i, (away_team, home_team) in enumerate(matchups, 1):
            print(f"\n{'='*80}")
            print(f"GAME {i}/{len(matchups)}")
            print(f"{'='*80}")

            try:
                result = self.run_full_pipeline(home_team, away_team)
                all_projections.append(result)
            except Exception as e:
                print(f"❌ Error processing {away_team} @ {home_team}: {e}")
                continue

        # Print summary
        self.print_summary(all_projections)

        # FINAL STEP: Save today's predictions for tomorrow's evaluation
        if PERFORMANCE_TRACKING_ENABLED and all_projections:
            print(f"\n{'='*80}")
            print(f"SAVING TODAY'S PREDICTIONS")
            print(f"{'='*80}\n")
            try:
                self.save_predictions_for_tracking(all_projections)
            except Exception as e:
                print(f"⚠ Could not save predictions: {e}")

    def save_predictions_for_tracking(self, all_projections: List[Dict]):
        """
        Save today's predictions for tomorrow's performance evaluation

        Args:
            all_projections: List of projection result dicts
        """
        today = datetime.now().strftime('%Y-%m-%d')

        # Format predictions for saving
        games_to_save = []

        for result in all_projections:
            proj = result['projection']
            home_adj = result['home_adjusted']
            away_adj = result['away_adjusted']
            rest = result.get('rest_adjustment', {})
            pace = result.get('pace_adjustment', {})

            # Calculate total injury adjustments
            home_total_adj = home_adj['off_adjustment'] + home_adj['def_adjustment']
            away_total_adj = away_adj['off_adjustment'] + away_adj['def_adjustment']

            # Get the appropriate spread and total
            baseline_spread = proj.get('spread', 0)
            rest_adjusted_spread = rest.get('rest_module_spread', baseline_spread)

            baseline_total = proj.get('total', 0)
            pace_adjusted_total = pace.get('pace_module_total', baseline_total)

            game_dict = {
                'home_team': proj['home_team'],
                'away_team': proj['away_team'],
                'spread': {
                    'baseline': baseline_spread,
                    'rest_adjusted': rest_adjusted_spread
                },
                'total': {
                    'baseline': baseline_total,
                    'pace_adjusted': pace_adjusted_total
                },
                'injury_impact': {
                    'home_total_adjustment': home_total_adj,
                    'away_total_adjustment': away_total_adj
                }
            }

            games_to_save.append(game_dict)

        # Save to JSON
        save_predictions(today, games_to_save)
        print(f"✓ Saved {len(games_to_save)} prediction(s) for future evaluation")

    def print_summary(self, projections: List[Dict]):
        """
        Print summary of all projections

        Args:
            projections: List of projection results
        """
        print(f"\n{'='*80}")
        print(f"PROJECTION SUMMARY - {len(projections)} GAMES")
        print(f"{'='*80}\n")

        for i, result in enumerate(projections, 1):
            proj = result['projection']
            home = result['home_adjusted']
            away = result['away_adjusted']
            rest = result.get('rest_adjustment', {})
            pace = result.get('pace_adjustment', {})

            print(f"Game {i}: {proj['away_team']} @ {proj['home_team']}")
            print(f"  Spread: {proj['favorite_team']} {proj['favorite_spread']:.1f}")

            # Show rest-adjusted spread if enabled
            if rest.get('rest_adjustment_enabled', False):
                rest_spread = rest['rest_module_spread']
                # Determine which team is favored in rest-adjusted spread
                if rest_spread < 0:
                    fav_team = proj['home_team']
                    spread_display = f"{fav_team} {rest_spread:.1f}"
                else:
                    fav_team = proj['away_team']
                    spread_display = f"{fav_team} {-rest_spread:.1f}"
                print(f"  Rest-Adjusted Spread: {spread_display}")
                print(f"    Rest Days: {proj['home_team']}={rest['rest_days_home']}d, {proj['away_team']}={rest['rest_days_away']}d")

            print(f"  Total: {proj['total']}")

            # Show pace-adjusted total if enabled
            if pace.get('pace_adjustment_enabled', False):
                pace_total = pace['pace_module_total']
                pace_delta = pace['pace_delta']
                print(f"  Pace-Adjusted Total: {pace_total:.1f}")
                print(f"    Pace Delta: {pace_delta:+.2f} (Adj: {pace['pace_total_adj']:+.1f})")

            print(f"  Score: {proj['home_points']}-{proj['away_points']}")

            # Show injury impacts
            home_adj = home['off_adjustment'] + home['def_adjustment']
            away_adj = away['off_adjustment'] + away['def_adjustment']

            if home_adj != 0 or away_adj != 0:
                print(f"  Injury Impact:")
                if home_adj != 0:
                    print(f"    {home['team_name']}: {home_adj:+.2f} total adjustment")
                if away_adj != 0:
                    print(f"    {away['team_name']}: {away_adj:+.2f} total adjustment")

            print()


if __name__ == "__main__":
    # Run master projection engine
    engine = MasterProjectionEngine()
    engine.project_all_games()
