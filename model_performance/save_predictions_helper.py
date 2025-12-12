"""
Helper script to save model predictions to JSON for later evaluation

Add this to your master_projection_engine.py after projections complete:

from model_performance.save_predictions_helper import save_predictions

# After running all games
save_predictions(date, games_list)
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict


def save_predictions(date: str, games: List[Dict], output_dir: str = None):
    """
    Save model predictions to JSON file

    Args:
        date: Date string (YYYY-MM-DD)
        games: List of game prediction dicts
        output_dir: Output directory (default: model_output/)
    """
    if output_dir is None:
        # Get project root (two levels up from this file)
        project_root = Path(__file__).parent.parent
        output_dir = project_root / 'model_output'
    else:
        output_dir = Path(output_dir)

    # Create output directory if needed
    output_dir.mkdir(parents=True, exist_ok=True)

    # Prepare output structure
    output = {
        'date': date,
        'timestamp': datetime.now().isoformat(),
        'games': games
    }

    # Save to JSON
    output_file = output_dir / f"{date}_projections.json"

    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"✓ Saved predictions to: {output_file}")


def format_game_prediction(home_team: str, away_team: str, projection_result: Dict) -> Dict:
    """
    Format a single game prediction for saving

    Args:
        home_team: Home team name
        away_team: Away team name
        projection_result: Result dict from run_full_pipeline()

    Returns:
        Formatted game dict
    """
    return {
        'home_team': home_team,
        'away_team': away_team,
        'spread': {
            'baseline': projection_result.get('baseline_spread'),
            'rest_adjusted': projection_result.get('rest_module_spread')
        },
        'total': {
            'baseline': projection_result.get('baseline_total'),
            'pace_adjusted': projection_result.get('pace_module_total')
        },
        'injury_impact': {
            'home_total_adjustment': projection_result.get('home_total_adjustment', 0),
            'away_total_adjustment': projection_result.get('away_total_adjustment', 0)
        }
    }


# Example usage:
if __name__ == "__main__":
    # Example of how to use this in master_projection_engine.py
    print("""
    Add this to master_projection_engine.py:

    # At the top
    from model_performance.save_predictions_helper import save_predictions, format_game_prediction

    # After running all games
    games_to_save = []
    for game in tonight_games:
        result = engine.run_full_pipeline(game['home'], game['away'], ...)
        games_to_save.append(format_game_prediction(game['home'], game['away'], result))

    save_predictions(today_date, games_to_save)
    """)
