"""
NBA Rest Adjustment Module
===========================

Purpose: Adjust spread projections based on each team's rest days.
This module runs ONLY after the baseline projection is produced.
This module does NOT modify any other model inputs or weights.

Key Features:
- Dynamically fetches each team's last game from NBA API
- Never stores data locally or reuses stale data
- Applies rest-based adjustments to baseline spread
- Uses nba_api library for reliable data fetching
"""

from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional
from nba_api.stats.endpoints import teamgamelog


class RestAdjustmentModule:
    """
    Rest Adjustment Module for NBA game projections
    """

    def __init__(self, season: str = '2025-26'):
        """
        Initialize the rest adjustment module

        Args:
            season: NBA season in format 'YYYY-YY'
        """
        self.season = season

    def fetch_last_game_nba_api(self, team_id: int) -> Optional[Dict]:
        """
        Fetch last game data from NBA API using nba_api library

        Args:
            team_id: NBA team ID

        Returns:
            Dict with last_game_date, home_or_away, opponent_id or None if failed
        """
        try:
            # Fetch team game log using nba_api
            game_log = teamgamelog.TeamGameLog(
                team_id=team_id,
                season=self.season,
                season_type_all_star='Regular Season'
            )

            df = game_log.get_data_frames()[0]

            if len(df) == 0:
                return None

            # Get the most recent game (first row)
            last_game = df.iloc[0]

            # Parse game date (format: 'DEC 07, 2025')
            game_date_str = last_game['GAME_DATE']
            game_date = datetime.strptime(game_date_str, '%b %d, %Y')

            # Determine home or away ('vs.' = home, '@' = away)
            matchup = last_game['MATCHUP']
            home_or_away = 'home' if 'vs.' in matchup else 'away'

            return {
                'last_game_date': game_date,
                'home_or_away': home_or_away,
                'opponent_id': None  # Not used in calculations
            }

        except Exception as e:
            print(f"      NBA API failed: {str(e)[:50]}")
            return None

    def get_rest_days(self, team_id: int, current_game_date: datetime) -> Tuple[int, str]:
        """
        Get rest days for a team

        Args:
            team_id: NBA team ID
            current_game_date: Date of current game

        Returns:
            Tuple of (rest_days, previous_home_or_away)
        """
        # Fetch last game data
        last_game_data = self.fetch_last_game_nba_api(team_id)

        # If API fails, default to 2 rest days
        if last_game_data is None:
            print(f"      ⚠ API failed, defaulting to 2 rest days")
            return 2, 'unknown'

        # Calculate rest days
        rest_days = (current_game_date - last_game_data['last_game_date']).days

        # Handle season opener case (more than 30 days = season opener)
        if rest_days > 30:
            rest_days = 5

        return rest_days, last_game_data['home_or_away']

    def calculate_rest_adjustment(self, rest_days: int, previous_location: str,
                                   current_location: str) -> float:
        """
        Calculate rest adjustment based on rest days and home/away transitions

        Args:
            rest_days: Number of days of rest
            previous_location: 'home' or 'away' for previous game
            current_location: 'home' or 'away' for current game

        Returns:
            Rest adjustment value
        """
        # Base rest adjustment
        if rest_days == 0:
            rest_adj = -1.5  # Back-to-back
        elif rest_days == 1:
            rest_adj = 0.0
        elif rest_days == 2:
            rest_adj = +0.5
        elif rest_days >= 3:
            rest_adj = +1.0
        else:
            rest_adj = 0.0

        # Additional home/away adjustments for 4+ days rest
        if rest_days >= 4:
            if previous_location == 'away' and current_location == 'home':
                rest_adj += 0.25  # Coming home after long road trip
            elif previous_location == 'home' and current_location == 'away':
                rest_adj -= 0.25  # Going on road after long homestand

        return rest_adj

    def apply_rest_adjustment(self, baseline_spread: float, home_team_id: int,
                              away_team_id: int, game_date: datetime,
                              rest_adjustment_enabled: bool = True) -> Dict:
        """
        Apply rest adjustment to baseline spread

        Args:
            baseline_spread: Baseline spread from core model (negative = home favored)
            home_team_id: Home team ID
            away_team_id: Away team ID
            game_date: Date of current game
            rest_adjustment_enabled: Toggle for rest adjustment

        Returns:
            Dict with rest adjustment details and adjusted spread
        """
        # If toggle is False, return baseline unchanged
        if not rest_adjustment_enabled:
            return {
                'rest_adjustment_enabled': False,
                'rest_days_home': None,
                'rest_days_away': None,
                'rest_adj_home': 0.0,
                'rest_adj_away': 0.0,
                'rest_module_spread': baseline_spread,
                'baseline_spread': baseline_spread
            }

        # Get rest days for both teams
        rest_days_home, prev_location_home = self.get_rest_days(home_team_id, game_date)
        rest_days_away, prev_location_away = self.get_rest_days(away_team_id, game_date)

        # Calculate rest adjustments
        rest_adj_home = self.calculate_rest_adjustment(
            rest_days_home, prev_location_home, 'home'
        )
        rest_adj_away = self.calculate_rest_adjustment(
            rest_days_away, prev_location_away, 'away'
        )

        # Apply adjustment to spread
        # Formula: adjusted_spread = baseline_spread + (rest_adj_away - rest_adj_home)
        # Positive spread favors away, negative favors home
        adjusted_spread = baseline_spread + (rest_adj_away - rest_adj_home)

        return {
            'rest_adjustment_enabled': True,
            'rest_days_home': rest_days_home,
            'rest_days_away': rest_days_away,
            'rest_adj_home': round(rest_adj_home, 2),
            'rest_adj_away': round(rest_adj_away, 2),
            'rest_module_spread': round(adjusted_spread, 1),
            'baseline_spread': baseline_spread,
            'rest_diff': round(rest_adj_away - rest_adj_home, 2)
        }
