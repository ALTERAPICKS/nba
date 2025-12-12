"""
NBA Pace Adjustment Module
===========================

Purpose: Adjust projected TOTALS based on team pace interaction.
This module does NOT modify spreads - it ONLY adjusts totals.
Runs AFTER the baseline total is produced.

Key Features:
- Calculates pace delta between matchup pace and league average
- Applies conservative adjustments to avoid overfitting
- Only affects total points, never the spread
"""

from typing import Dict


class PaceAdjustmentModule:
    """
    Pace Adjustment Module for NBA game totals
    """

    def __init__(self, league_avg_pace: float = 98.5):
        """
        Initialize the pace adjustment module

        Args:
            league_avg_pace: League average pace (possessions per game)
        """
        self.league_avg_pace = league_avg_pace

    def calculate_pace_delta(self, team_a_pace: float, team_b_pace: float) -> float:
        """
        Calculate the pace interaction effect of the matchup

        Args:
            team_a_pace: Team A's pace rating
            team_b_pace: Team B's pace rating

        Returns:
            Pace delta (positive = faster than average, negative = slower)
        """
        pace_delta = (team_a_pace + team_b_pace) - (2 * self.league_avg_pace)
        return pace_delta

    def calculate_pace_adjustment(self, pace_delta: float) -> float:
        """
        Assign pace adjustment based on strict conservative rules

        Args:
            pace_delta: The pace delta from calculate_pace_delta

        Returns:
            Pace total adjustment value
        """
        if pace_delta > 4:
            return +4.0
        elif pace_delta > 2:
            return +2.0
        elif pace_delta < -4:
            return -4.0
        elif pace_delta < -2:
            return -2.0
        else:
            return 0.0

    def apply_pace_adjustment(self, baseline_total: float, home_pace: float,
                              away_pace: float, pace_adjustment_enabled: bool = True) -> Dict:
        """
        Apply pace adjustment to baseline total

        Args:
            baseline_total: Baseline total from core model
            home_pace: Home team's pace rating
            away_pace: Away team's pace rating
            pace_adjustment_enabled: Toggle for pace adjustment

        Returns:
            Dict with pace adjustment details and adjusted total
        """
        # If toggle is False, return baseline unchanged
        if not pace_adjustment_enabled:
            return {
                'pace_adjustment_enabled': False,
                'pace_delta': 0.0,
                'pace_total_adj': 0.0,
                'baseline_total': baseline_total,
                'pace_module_total': baseline_total
            }

        # Calculate pace delta
        pace_delta = self.calculate_pace_delta(home_pace, away_pace)

        # Calculate pace adjustment
        pace_total_adj = self.calculate_pace_adjustment(pace_delta)

        # Apply adjustment to total
        pace_module_total = baseline_total + pace_total_adj

        return {
            'pace_adjustment_enabled': True,
            'pace_delta': round(pace_delta, 2),
            'pace_total_adj': round(pace_total_adj, 1),
            'baseline_total': baseline_total,
            'pace_module_total': round(pace_module_total, 1)
        }
