"""
NBA Player Stats Processing Module
Evaluates individual player impact eligibility using strict filters
DOES NOT modify team ratings - only produces player impact objects
"""

from nba_api.stats.endpoints import leaguedashplayerstats, playerdashboardbygeneralsplits
from nba_api.stats.static import players as players_static
import pandas as pd
import numpy as np
from typing import Dict, List, Optional


class PlayerStatsProcessor:
    """
    Processes individual player statistics to determine impact eligibility
    Uses strict filters to eliminate noise from role players
    """

    # League average baselines (2025-26 estimates)
    LEAGUE_AVG_OFF_RATING = 115.0
    LEAGUE_AVG_DEF_RATING = 115.0

    # Filter thresholds
    MIN_MINUTES_THRESHOLD = 300
    MAX_USAGE_VOLATILITY = 5.0  # Standard deviation threshold
    MIN_ON_OFF_STRENGTH = 1.5   # Absolute value threshold

    # Impact caps by tier
    TIER_1_CAP = 6.0
    TIER_2_CAP = 3.0

    # Regression weights
    PLAYER_WEIGHT = 0.7
    LEAGUE_AVG_WEIGHT = 0.3

    def __init__(self, season: str = '2025-26'):
        """Initialize player stats processor"""
        self.season = season

    def get_player_id(self, player_name: str) -> Optional[int]:
        """
        Get player ID from player name

        Args:
            player_name: Full player name

        Returns:
            Player ID or None if not found
        """
        all_players = players_static.get_players()

        for player in all_players:
            if player_name.lower() in player['full_name'].lower():
                return player['id']

        return None

    def fetch_player_stats(self, player_name: str) -> Optional[Dict]:
        """
        Fetch required player statistics from NBA API

        Args:
            player_name: Full player name

        Returns:
            Dict with required stats or None if error
        """
        player_id = self.get_player_id(player_name)

        if player_id is None:
            print(f"Player '{player_name}' not found")
            return None

        try:
            # Get advanced stats with on/off data
            player_dash = playerdashboardbygeneralsplits.PlayerDashboardByGeneralSplits(
                player_id=player_id,
                season=self.season,
                measure_type_detailed='Advanced',
                per_mode_detailed='Totals'
            )

            dfs = player_dash.get_data_frames()

            if len(dfs) == 0 or len(dfs[0]) == 0:
                return None

            overall = dfs[0].iloc[0]

            # Extract required stats
            # Note: MIN in Totals mode should be total minutes, but calculate to be safe
            games_played = overall['GP']
            minutes_per_game = overall['MIN']
            total_minutes = minutes_per_game * games_played if games_played > 0 else 0

            # Convert usage to percentage if needed (API returns as decimal sometimes)
            usage_raw = overall['USG_PCT']
            usage_pct = usage_raw * 100 if usage_raw < 1 else usage_raw

            stats = {
                'player_name': player_name,
                'player_id': player_id,
                'games_played': games_played,
                'minutes_played_season': total_minutes,
                'minutes_per_game': minutes_per_game,
                'usage_rate': usage_pct,
                'off_rating_oncourt': overall['OFF_RATING'],
                'def_rating_oncourt': overall['DEF_RATING'],
                'net_rating': overall['NET_RATING']
            }

            # Get last 10 games for usage volatility
            player_dash_last10 = playerdashboardbygeneralsplits.PlayerDashboardByGeneralSplits(
                player_id=player_id,
                season=self.season,
                measure_type_detailed='Advanced',
                last_n_games=10,
                per_mode_detailed='PerGame'
            )

            last10_dfs = player_dash_last10.get_data_frames()

            if len(last10_dfs) > 0 and len(last10_dfs[0]) > 0:
                usage_last10_raw = last10_dfs[0].iloc[0]['USG_PCT']
                usage_last10_pct = usage_last10_raw * 100 if usage_last10_raw < 1 else usage_last10_raw

                stats['games_played_last_10'] = last10_dfs[0].iloc[0]['GP']
                stats['usage_rate_last_10'] = usage_last10_pct
            else:
                stats['games_played_last_10'] = 0
                stats['usage_rate_last_10'] = stats['usage_rate']

            return stats

        except Exception as e:
            print(f"Error fetching stats for {player_name}: {e}")
            return None

    def fetch_team_roster_stats(self, team_name: str) -> List[Dict]:
        """
        Fetch stats for all players on a team

        Args:
            team_name: NBA team name

        Returns:
            List of player stat dicts
        """
        try:
            # Get all player stats filtered by team
            league_stats = leaguedashplayerstats.LeagueDashPlayerStats(
                season=self.season,
                per_mode_detailed='Totals',
                measure_type_detailed_defense='Advanced'
            )

            df = league_stats.get_data_frames()[0]

            # Filter by team
            team_players = df[df['TEAM_ABBREVIATION'] == self._get_team_abbrev(team_name)]

            roster_stats = []

            for idx, player_row in team_players.iterrows():
                player_name = player_row['PLAYER_NAME']

                # Fetch detailed stats for each player
                player_stats = self.fetch_player_stats(player_name)

                if player_stats:
                    roster_stats.append(player_stats)

            return roster_stats

        except Exception as e:
            print(f"Error fetching team roster stats: {e}")
            return []

    def _get_team_abbrev(self, team_name: str) -> str:
        """Get team abbreviation from full name"""
        team_map = {
            'Atlanta Hawks': 'ATL',
            'Boston Celtics': 'BOS',
            'Brooklyn Nets': 'BKN',
            'Charlotte Hornets': 'CHA',
            'Chicago Bulls': 'CHI',
            'Cleveland Cavaliers': 'CLE',
            'Dallas Mavericks': 'DAL',
            'Denver Nuggets': 'DEN',
            'Detroit Pistons': 'DET',
            'Golden State Warriors': 'GSW',
            'Houston Rockets': 'HOU',
            'Indiana Pacers': 'IND',
            'Los Angeles Clippers': 'LAC',
            'Los Angeles Lakers': 'LAL',
            'Memphis Grizzlies': 'MEM',
            'Miami Heat': 'MIA',
            'Milwaukee Bucks': 'MIL',
            'Minnesota Timberwolves': 'MIN',
            'New Orleans Pelicans': 'NOP',
            'New York Knicks': 'NYK',
            'Oklahoma City Thunder': 'OKC',
            'Orlando Magic': 'ORL',
            'Philadelphia 76ers': 'PHI',
            'Phoenix Suns': 'PHX',
            'Portland Trail Blazers': 'POR',
            'Sacramento Kings': 'SAC',
            'San Antonio Spurs': 'SAS',
            'Toronto Raptors': 'TOR',
            'Utah Jazz': 'UTA',
            'Washington Wizards': 'WAS'
        }
        return team_map.get(team_name, '')

    # ============================================================================
    # FILTER A: Minimum Minutes Threshold
    # ============================================================================

    def filter_a_minimum_minutes(self, minutes_played: float) -> bool:
        """
        Filter A: Player must have played at least 300 minutes this season

        Args:
            minutes_played: Total season minutes

        Returns:
            True if eligible, False if ineligible
        """
        return minutes_played >= self.MIN_MINUTES_THRESHOLD

    # ============================================================================
    # FILTER B: Usage Stability (Last 10 Games)
    # ============================================================================

    def filter_b_usage_stability(self, usage_rate_last_10: float, usage_rate_season: float) -> tuple:
        """
        Filter B: Usage volatility must be < 5%

        For now, we approximate volatility since we don't have game-by-game data easily.
        If last 10 usage differs significantly from season usage, flag as volatile.

        Args:
            usage_rate_last_10: Usage rate over last 10 games
            usage_rate_season: Season average usage rate

        Returns:
            (eligible: bool, volatility: float)
        """
        # Approximate volatility using difference between last 10 and season
        # This is a proxy - actual volatility would need game-by-game data
        usage_diff = abs(usage_rate_last_10 - usage_rate_season)

        # If usage changed by more than 5%, consider volatile
        eligible = usage_diff <= self.MAX_USAGE_VOLATILITY

        return eligible, usage_diff

    # ============================================================================
    # FILTER C: On/Off Strength Threshold
    # ============================================================================

    def filter_c_onoff_strength(self, net_rating: float) -> bool:
        """
        Filter C: Player must have strong on/off impact (|net_rating| > 1.5)

        Args:
            net_rating: Player's net rating (on-court impact)

        Returns:
            True if eligible, False if ineligible
        """
        return abs(net_rating) > self.MIN_ON_OFF_STRENGTH

    # ============================================================================
    # FILTER D: Role Tier Classification
    # ============================================================================

    def filter_d_tier_classification(self, usage_rate: float, minutes_played: float,
                                     net_rating: float, games_played: int) -> str:
        """
        Filter D: Classify player into tier based on usage, minutes, and impact

        Tier 1: Primary star (high usage + high minutes + strong impact)
        Tier 2: High-impact secondary player
        Tier 3: Normal rotation player
        Tier 4: Fringe/minimal player or insufficient data

        Args:
            usage_rate: Player usage percentage
            minutes_played: Total season minutes
            net_rating: Player net rating
            games_played: Games played this season

        Returns:
            Tier classification: "Tier 1", "Tier 2", "Tier 3", or "Tier 4"
        """
        # Sample size requirement (must be met before tier evaluation)
        if minutes_played < 300:
            return "Tier 4"  # Automatically neutral, insufficient data

        mpg = minutes_played / games_played if games_played > 0 else 0

        # Tier 1: Primary stars (superstars - high usage, high minutes, strong signal)
        # REVISED: Lowered net rating threshold to match real data
        if usage_rate >= 28 and mpg >= 30 and abs(net_rating) >= 2:
            return "Tier 1"

        # Tier 2: Secondary stars / Key players
        # REVISED: Lowered thresholds to match actual player data
        if usage_rate >= 22 and mpg >= 26 and abs(net_rating) >= 1:
            return "Tier 2"

        # Tier 3: Regular rotation players
        if mpg >= 15:
            return "Tier 3"

        # Tier 4: Fringe/minimal players
        return "Tier 4"

    # ============================================================================
    # VEGAS MODULE #1: Lineup Dependency Weighting
    # ============================================================================

    def vegas_module_1_lineup_dependency(self, starter_overlap_pct: float) -> float:
        """
        Vegas Module #1: Adjust impact based on minutes played with core starters

        Args:
            starter_overlap_pct: Percentage of minutes played with team's 5 core starters (0-100)

        Returns:
            Lineup weight multiplier (0.5, 0.8, or 1.0)
        """
        if starter_overlap_pct >= 60.0:
            return 1.0  # Full impact
        elif starter_overlap_pct >= 30.0:
            return 0.8  # Reduced impact
        else:
            return 0.5  # Minimal impact (bench specialist)

    # ============================================================================
    # VEGAS MODULE #2: Position-Based Defensive Weighting
    # ============================================================================

    def vegas_module_2_defensive_role(self, position: str, is_rim_protector: bool = False,
                                     is_poa_defender: bool = False) -> float:
        """
        Vegas Module #2: Weight defensive impact by position/role

        Args:
            position: Player position (C, PF, SF, SG, PG)
            is_rim_protector: True if player is a rim protector (C or PF/C)
            is_poa_defender: True if player is a primary point-of-attack defender

        Returns:
            Defensive role weight multiplier
        """
        # Rim protectors (centers, PF/C hybrids)
        if is_rim_protector or position in ['C', 'C-F']:
            return 1.40

        # Point-of-attack defenders (elite perimeter defenders)
        if is_poa_defender:
            return 1.20

        # All other players
        return 1.00

    # ============================================================================
    # VEGAS MODULE #3: Sample-Size Dampening
    # ============================================================================

    def vegas_module_3_sample_dampening(self, games_played: int) -> float:
        """
        Vegas Module #3: Dampen impacts for small sample sizes

        Args:
            games_played: Number of games played this season

        Returns:
            Sample size dampening multiplier (0.6 if < 15 games, 1.0 otherwise)
        """
        if games_played < 15:
            return 0.6  # Reduce impacts by 40% for unstable samples
        return 1.0

    # ============================================================================
    # Impact Calculation (For Eligible Players Only)
    # ============================================================================

    def calculate_impact(self, off_rating: float, def_rating: float, tier: str) -> tuple:
        """
        Calculate regressed offensive and defensive impact

        Args:
            off_rating: Player's on-court offensive rating
            def_rating: Player's on-court defensive rating
            tier: Player tier classification

        Returns:
            (off_impact, def_impact) tuple
        """
        # Regress toward league average (70/30 blend)
        regressed_off = (self.PLAYER_WEIGHT * off_rating +
                        self.LEAGUE_AVG_WEIGHT * self.LEAGUE_AVG_OFF_RATING)

        regressed_def = (self.PLAYER_WEIGHT * def_rating +
                        self.LEAGUE_AVG_WEIGHT * self.LEAGUE_AVG_DEF_RATING)

        # Convert to IMPACTS (differential from league average)
        off_impact = regressed_off - self.LEAGUE_AVG_OFF_RATING
        def_impact = regressed_def - self.LEAGUE_AVG_DEF_RATING

        # Apply caps based on tier
        if tier == "Tier 1":
            cap = self.TIER_1_CAP
        elif tier == "Tier 2":
            cap = self.TIER_2_CAP
        else:
            # Should never reach here for Tier 3/4, but safety check
            return 0.0, 0.0

        # Cap impacts to tier limits (now these are impact values, not ratings)
        off_impact = max(min(off_impact, cap), -cap)
        def_impact = max(min(def_impact, cap), -cap)

        return off_impact, def_impact

    # ============================================================================
    # Main Processing Function
    # ============================================================================

    def process_player(self, player_stats: Dict, team_name: str,
                      position: str = None, starter_overlap_pct: float = 100.0,
                      is_rim_protector: bool = False, is_poa_defender: bool = False) -> Dict:
        """
        Process a single player and generate impact object with Vegas modules

        Args:
            player_stats: Dict with player statistics
            team_name: Team name
            position: Player position (optional, for defensive weighting)
            starter_overlap_pct: % of minutes with core starters (0-100)
            is_rim_protector: True if player is a rim protector
            is_poa_defender: True if player is point-of-attack defender

        Returns:
            Player impact object with Vegas adjustments applied
        """
        player_name = player_stats['player_name']
        games_played = player_stats['games_played']
        minutes = player_stats['minutes_played_season']
        mpg = player_stats.get('minutes_per_game', 0)
        usage = player_stats['usage_rate']
        usage_last10 = player_stats['usage_rate_last_10']
        off_rating = player_stats['off_rating_oncourt']
        def_rating = player_stats['def_rating_oncourt']
        net_rating = player_stats['net_rating']

        # Apply filters
        pass_filter_a = self.filter_a_minimum_minutes(minutes)
        pass_filter_b, usage_volatility = self.filter_b_usage_stability(usage_last10, usage)
        pass_filter_c = self.filter_c_onoff_strength(net_rating)

        tier = self.filter_d_tier_classification(usage, minutes, net_rating, games_played)
        pass_filter_d = tier in ["Tier 1", "Tier 2"]

        # Determine eligibility
        eligible = pass_filter_a and pass_filter_b and pass_filter_c and pass_filter_d

        # Calculate base impact if eligible
        if eligible:
            off_impact, def_impact = self.calculate_impact(off_rating, def_rating, tier)

            # Apply Vegas Module #1: Lineup Dependency Weighting
            # If no overlap provided, assume starters get 100%, bench gets 50%
            if starter_overlap_pct is None:
                starter_overlap_pct = 100.0 if mpg >= 25 else 50.0

            lineup_weight = self.vegas_module_1_lineup_dependency(starter_overlap_pct)

            # Apply Vegas Module #2: Position-Based Defensive Weighting
            if position:
                def_role_weight = self.vegas_module_2_defensive_role(
                    position, is_rim_protector, is_poa_defender
                )
            else:
                def_role_weight = 1.0

            # Apply Vegas Module #3: Sample-Size Dampening
            sample_weight = self.vegas_module_3_sample_dampening(games_played)

            # Apply all Vegas adjustments
            off_impact = off_impact * lineup_weight * sample_weight
            def_impact = def_impact * lineup_weight * def_role_weight * sample_weight

            vegas_adjustments = {
                'lineup_weight': round(lineup_weight, 2),
                'def_role_weight': round(def_role_weight, 2),
                'sample_weight': round(sample_weight, 2),
                'total_off_multiplier': round(lineup_weight * sample_weight, 2),
                'total_def_multiplier': round(lineup_weight * def_role_weight * sample_weight, 2)
            }
        else:
            off_impact = 0.0
            def_impact = 0.0
            vegas_adjustments = {}

        # Return clean player impact object
        return {
            'player_name': player_name,
            'team': team_name,
            'games_played': games_played,
            'minutes_played_season': round(minutes, 1),
            'minutes_per_game': round(mpg, 1),
            'usage_rate': round(usage, 1),
            'usage_volatility_10': round(usage_volatility, 1),
            'on_off_net_rating': round(net_rating, 1),
            'tier': tier,
            'eligible': eligible,
            'off_impact': round(off_impact, 1),
            'def_impact': round(def_impact, 1),
            'vegas_adjustments': vegas_adjustments,
            'filter_results': {
                'min_minutes': pass_filter_a,
                'usage_stable': pass_filter_b,
                'strong_onoff': pass_filter_c,
                'tier_eligible': pass_filter_d
            }
        }

    def print_player_impact(self, impact_obj: Dict):
        """Print formatted player impact object"""
        print(f"\n{'='*80}")
        print(f"PLAYER: {impact_obj['player_name']} ({impact_obj['team']})")
        print(f"{'='*80}")

        print(f"\nSTATS:")
        print(f"  Games Played: {impact_obj['games_played']}")
        print(f"  Minutes Played: {impact_obj['minutes_played_season']:.1f} ({impact_obj['minutes_per_game']:.1f} MPG)")
        print(f"  Usage Rate: {impact_obj['usage_rate']}%")
        print(f"  Usage Volatility: {impact_obj['usage_volatility_10']}%")
        print(f"  On/Off Net Rating: {impact_obj['on_off_net_rating']:+.1f}")

        print(f"\nCLASSIFICATION:")
        print(f"  Tier: {impact_obj['tier']}")
        print(f"  Eligible: {'✓ YES' if impact_obj['eligible'] else '✗ NO'}")

        print(f"\nFILTER RESULTS:")
        for filter_name, passed in impact_obj['filter_results'].items():
            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"  {filter_name}: {status}")

        if impact_obj.get('vegas_adjustments'):
            print(f"\nVEGAS ADJUSTMENTS:")
            vegas = impact_obj['vegas_adjustments']
            print(f"  Lineup Weight: {vegas['lineup_weight']}")
            print(f"  Defensive Role Weight: {vegas['def_role_weight']}")
            print(f"  Sample Size Weight: {vegas['sample_weight']}")
            print(f"  Total Offensive Multiplier: {vegas['total_off_multiplier']}")
            print(f"  Total Defensive Multiplier: {vegas['total_def_multiplier']}")

        print(f"\nFINAL IMPACT VALUES:")
        print(f"  Offensive Impact: {impact_obj['off_impact']:.1f}")
        print(f"  Defensive Impact: {impact_obj['def_impact']:.1f}")

        if not impact_obj['eligible']:
            print(f"\n⚠️  Player is INELIGIBLE - Impact set to 0")


if __name__ == "__main__":
    # Test the player stats processor with Vegas modules
    processor = PlayerStatsProcessor(season='2025-26')

    # Test with different scenarios
    test_cases = [
        {
            'player': 'Giannis Antetokounmpo',
            'position': 'C-F',
            'starter_overlap': 100.0,
            'is_rim_protector': True,
            'description': 'Tier 1 Star + Rim Protector'
        },
        {
            'player': 'Stephen Curry',
            'position': 'PG',
            'starter_overlap': 100.0,
            'is_poa_defender': False,
            'description': 'Tier 2 Star (Small Sample < 15 games)'
        },
        {
            'player': 'Damian Lillard',
            'position': 'PG',
            'starter_overlap': 40.0,  # Moderate overlap
            'description': 'Secondary Player - Moderate Lineup Overlap'
        }
    ]

    print("TESTING PLAYER STATS PROCESSOR WITH VEGAS MODULES")
    print("="*80)

    for test_case in test_cases:
        player_name = test_case['player']
        print(f"\n{'='*80}")
        print(f"TEST CASE: {test_case['description']}")
        print(f"{'='*80}")
        print(f"\nProcessing {player_name}...")

        stats = processor.fetch_player_stats(player_name)

        if stats:
            impact_obj = processor.process_player(
                stats,
                "Test Team",
                position=test_case.get('position'),
                starter_overlap_pct=test_case.get('starter_overlap', 100.0),
                is_rim_protector=test_case.get('is_rim_protector', False),
                is_poa_defender=test_case.get('is_poa_defender', False)
            )
            processor.print_player_impact(impact_obj)
