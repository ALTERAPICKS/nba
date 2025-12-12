"""
NBA Model Recommendation Engine
================================

Analyzes historical model performance to identify recommended picks.
Does NOT influence model predictions - purely observational analysis layer.

Usage:
    from model_performance.recommendation_engine import evaluate_recommendation

    result = evaluate_recommendation('spread_big_edge', 4.5)
    if result['recommended']:
        print(f"RECOMMEND: {result['reason']}")
        print(f"Historical win rate: {result['historical_win_rate']:.1%}")
"""

import csv
from pathlib import Path
from typing import Dict, Optional


class RecommendationEngine:
    """Evaluates picks based on historical performance data"""

    # Valid pick types
    VALID_PICK_TYPES = {
        'spread_dog_value',
        'spread_fav_small',
        'spread_big_edge',
        'flipped_favorite',
        'total_over_value',
        'total_over_big_edge',
        'total_under_value',
        'total_under_big_edge'
    }

    # Recommendation thresholds
    MIN_EDGE_POINTS = 3.0
    MIN_WIN_RATE = 0.57
    MIN_SAMPLE_SIZE = 5

    def __init__(self, csv_path: str = None):
        """
        Initialize recommendation engine

        Args:
            csv_path: Path to performance CSV (default: model_performance_log.csv)
        """
        if csv_path is None:
            module_dir = Path(__file__).parent
            csv_path = module_dir / 'model_performance_log.csv'

        self.csv_path = Path(csv_path)
        self.historical_stats = self._load_historical_stats()

    def _load_historical_stats(self) -> Dict[str, Dict]:
        """
        Load historical win rates by pick type from CSV

        Returns:
            Dict mapping pick_type to {win_rate, total, wins}
        """
        stats = {}

        if not self.csv_path.exists():
            return stats

        try:
            with open(self.csv_path, 'r') as f:
                reader = csv.DictReader(f)

                for row in reader:
                    pick_type = row.get('pick_type')
                    result_correct = row.get('result_correct', '').upper()

                    if not pick_type or pick_type not in self.VALID_PICK_TYPES:
                        continue

                    # Initialize if first time seeing this pick type
                    if pick_type not in stats:
                        stats[pick_type] = {'wins': 0, 'total': 0}

                    stats[pick_type]['total'] += 1

                    if result_correct == 'TRUE':
                        stats[pick_type]['wins'] += 1

            # Calculate win rates
            for pick_type, data in stats.items():
                total = data['total']
                wins = data['wins']

                if total >= self.MIN_SAMPLE_SIZE:
                    data['win_rate'] = wins / total
                else:
                    data['win_rate'] = None

        except Exception as e:
            print(f"Warning: Could not load historical stats - {str(e)[:50]}")

        return stats

    def evaluate_recommendation(self, pick_type: str, edge_points: float) -> Dict:
        """
        Evaluate if a pick should be recommended based on historical performance

        Args:
            pick_type: Type of pick (e.g., 'spread_big_edge')
            edge_points: Edge size in points

        Returns:
            Dict with:
                - recommended (bool): Should this pick be recommended?
                - reason (str): Explanation for recommendation decision
                - historical_win_rate (float or None): Win rate for this pick type
                - sample_size (int): Number of historical picks of this type
        """
        # Validate pick type
        if pick_type not in self.VALID_PICK_TYPES:
            return {
                'recommended': False,
                'reason': 'invalid pick type',
                'historical_win_rate': None,
                'sample_size': 0
            }

        # Get historical stats for this pick type
        stats = self.historical_stats.get(pick_type, {'wins': 0, 'total': 0, 'win_rate': None})

        sample_size = stats['total']
        win_rate = stats['win_rate']

        # Insufficient data
        if sample_size < self.MIN_SAMPLE_SIZE:
            return {
                'recommended': False,
                'reason': 'insufficient historical data',
                'historical_win_rate': None,
                'sample_size': sample_size
            }

        # Edge too small
        if edge_points < self.MIN_EDGE_POINTS:
            return {
                'recommended': False,
                'reason': 'edge too small',
                'historical_win_rate': win_rate,
                'sample_size': sample_size
            }

        # Category underperforms
        if win_rate < self.MIN_WIN_RATE:
            return {
                'recommended': False,
                'reason': 'category underperforms',
                'historical_win_rate': win_rate,
                'sample_size': sample_size
            }

        # Recommend!
        return {
            'recommended': True,
            'reason': 'edge and historical success aligned',
            'historical_win_rate': win_rate,
            'sample_size': sample_size
        }

    def get_all_stats(self) -> Dict[str, Dict]:
        """
        Get all historical statistics

        Returns:
            Dict mapping pick_type to stats
        """
        return self.historical_stats.copy()

    def reload_stats(self):
        """Reload historical stats from CSV (use after new data is logged)"""
        self.historical_stats = self._load_historical_stats()


# Global engine instance
_engine = None


def get_engine() -> RecommendationEngine:
    """Get or create global recommendation engine instance"""
    global _engine
    if _engine is None:
        _engine = RecommendationEngine()
    return _engine


def evaluate_recommendation(pick_type: str, edge_points: float) -> Dict:
    """
    Public API: Evaluate if a pick should be recommended

    Args:
        pick_type: Type of pick (e.g., 'spread_big_edge')
        edge_points: Edge size in points

    Returns:
        Dict with recommendation decision and historical stats

    Example:
        result = evaluate_recommendation('spread_big_edge', 4.5)
        if result['recommended']:
            print(f"✓ RECOMMEND ({result['historical_win_rate']:.1%} win rate)")
        else:
            print(f"✗ SKIP: {result['reason']}")
    """
    engine = get_engine()
    return engine.evaluate_recommendation(pick_type, edge_points)


def reload_historical_stats():
    """Reload historical stats from CSV (call after new data is logged)"""
    engine = get_engine()
    engine.reload_stats()


def get_all_historical_stats() -> Dict[str, Dict]:
    """
    Get all historical statistics by pick type

    Returns:
        Dict mapping pick_type to {wins, total, win_rate}

    Example:
        stats = get_all_historical_stats()
        for pick_type, data in stats.items():
            print(f"{pick_type}: {data['win_rate']:.1%} ({data['wins']}/{data['total']})")
    """
    engine = get_engine()
    return engine.get_all_stats()


if __name__ == "__main__":
    # Test the recommendation engine
    print("="*80)
    print("NBA RECOMMENDATION ENGINE - TEST")
    print("="*80)

    # Show all historical stats
    print("\nHistorical Statistics by Pick Type:")
    print("-"*80)

    stats = get_all_historical_stats()

    if not stats:
        print("No historical data found in CSV")
    else:
        for pick_type in sorted(stats.keys()):
            data = stats[pick_type]
            total = data['total']
            wins = data['wins']
            win_rate = data['win_rate']

            if win_rate is not None:
                print(f"{pick_type:25} {wins:2}/{total:2} = {win_rate:5.1%}")
            else:
                print(f"{pick_type:25} {wins:2}/{total:2} = N/A (insufficient data)")

    # Test recommendations
    print("\n" + "="*80)
    print("Testing Recommendations:")
    print("-"*80)

    test_cases = [
        ('spread_big_edge', 4.5),
        ('spread_dog_value', 2.0),
        ('total_over_big_edge', 5.0),
        ('flipped_favorite', 1.5),
    ]

    for pick_type, edge in test_cases:
        result = evaluate_recommendation(pick_type, edge)

        print(f"\n{pick_type} (edge: {edge:.1f})")

        if result['recommended']:
            print(f"  ✓ RECOMMEND")
            print(f"    Reason: {result['reason']}")
            print(f"    Historical: {result['historical_win_rate']:.1%} ({result['sample_size']} picks)")
        else:
            print(f"  ✗ SKIP")
            print(f"    Reason: {result['reason']}")
            if result['historical_win_rate'] is not None:
                print(f"    Historical: {result['historical_win_rate']:.1%} ({result['sample_size']} picks)")
            else:
                print(f"    Historical: N/A ({result['sample_size']} picks)")

    print("\n" + "="*80)
    print("Test complete!")
    print("="*80)
