"""
NBA Model Outcome Fetcher
==========================

Observational script that evaluates model prediction correctness AFTER games complete.
Does NOT modify or influence the model in any way.

Usage:
    python3 model_performance/outcome_fetcher.py

This will:
1. Fetch yesterday's completed NBA games from ESPN
2. Get final scores and closing odds
3. Load model predictions
4. Evaluate correctness
5. Log results to performance tracker
"""

import requests
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Import logger - handle both direct execution and module import
try:
    from .performance_logger import log_model_performance
except ImportError:
    from performance_logger import log_model_performance


class OutcomeFetcher:
    """Fetches game outcomes and evaluates model predictions"""

    ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
    ESPN_ODDS_URL = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/events/{event_id}/competitions/{comp_id}/odds"

    # Team abbreviation mapping (ESPN full name → abbreviation)
    TEAM_ABBREV_MAP = {
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
        'LA Clippers': 'LAC',
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

    def __init__(self, project_root: str = None):
        """
        Initialize outcome fetcher

        Args:
            project_root: Path to project root (default: parent of this file)
        """
        if project_root is None:
            project_root = Path(__file__).parent.parent

        self.project_root = Path(project_root)
        self.output_dir = self.project_root / 'model_output'

    def get_team_abbrev(self, full_name: str) -> str:
        """Get team abbreviation from full name"""
        return self.TEAM_ABBREV_MAP.get(full_name, full_name[:3].upper())

    def fetch_yesterdays_games(self) -> List[Dict]:
        """
        Fetch yesterday's completed NBA games from ESPN

        Returns:
            List of game dictionaries with scores and metadata
        """
        yesterday = datetime.now() - timedelta(days=1)
        date_str = yesterday.strftime('%Y%m%d')

        url = f"{self.ESPN_SCOREBOARD_URL}?dates={date_str}"

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            games = []

            for event in data.get('events', []):
                # Only process completed games
                status = event.get('status', {}).get('type', {}).get('name', '')
                if status != 'STATUS_FINAL':
                    print(f"  Skipping {event.get('name', 'Unknown')} - Status: {status}")
                    continue

                competition = event.get('competitions', [{}])[0]
                competitors = competition.get('competitors', [])

                if len(competitors) != 2:
                    continue

                # Extract teams and scores
                home_team = next((c for c in competitors if c.get('homeAway') == 'home'), None)
                away_team = next((c for c in competitors if c.get('homeAway') == 'away'), None)

                if not home_team or not away_team:
                    continue

                home_name = home_team.get('team', {}).get('displayName', '')
                away_name = away_team.get('team', {}).get('displayName', '')
                home_score = int(home_team.get('score', 0))
                away_score = int(away_team.get('score', 0))

                game_info = {
                    'event_id': event.get('id'),
                    'comp_id': competition.get('id'),
                    'home_team': home_name,
                    'away_team': away_name,
                    'home_score': home_score,
                    'away_score': away_score,
                    'game_id': f"{self.get_team_abbrev(away_name)}@{self.get_team_abbrev(home_name)}",
                    'date': yesterday.strftime('%Y-%m-%d')
                }

                games.append(game_info)

            return games

        except requests.RequestException as e:
            print(f"Error fetching scoreboard: {e}")
            return []

    def fetch_game_odds(self, event_id: str, comp_id: str) -> Optional[Dict]:
        """
        Fetch closing odds for a game from ESPN

        Args:
            event_id: ESPN event ID
            comp_id: ESPN competition ID

        Returns:
            Dict with closing spread and total, or None if unavailable
        """
        url = self.ESPN_ODDS_URL.format(event_id=event_id, comp_id=comp_id)

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            # ESPN odds format: data['items'][0] contains odds providers
            items = data.get('items', [])

            if not items:
                return None

            # Try to find consensus or first available odds
            for item in items:
                # Get actual spread and total (not betting juice)
                spread = item.get('spread', None)  # Actual spread line
                over_under = item.get('overUnder', None)  # Actual total

                if spread is not None and over_under is not None:
                    return {
                        'spread': float(spread),  # Negative = home favored
                        'total': float(over_under)
                    }

            return None

        except (requests.RequestException, ValueError, KeyError) as e:
            print(f"  Warning: Could not fetch odds - {str(e)[:50]}")
            return None

    def load_model_predictions(self, date: str) -> Optional[Dict]:
        """
        Load model predictions from JSON file

        Args:
            date: Date string in YYYY-MM-DD format

        Returns:
            Dict with predictions or None if file not found
        """
        prediction_file = self.output_dir / f"{date}_projections.json"

        if not prediction_file.exists():
            print(f"  Prediction file not found: {prediction_file}")
            return None

        try:
            with open(prediction_file, 'r') as f:
                return json.load(f)

        except (json.JSONDecodeError, IOError) as e:
            print(f"  Error loading predictions: {e}")
            return None

    def determine_spread_correctness(self, game_info: Dict, model_spread: float,
                                     market_spread: float) -> Tuple[bool, str]:
        """
        Determine if spread prediction was correct

        Args:
            game_info: Game info dict with scores
            model_spread: Model's projected spread (negative = home favored)
            market_spread: Market spread (negative = home favored)

        Returns:
            Tuple of (was_correct, notes)
        """
        home_score = game_info['home_score']
        away_score = game_info['away_score']

        # Actual margin (home perspective)
        actual_margin = home_score - away_score

        # ATS result against market spread
        # If market spread is -5, home needs to win by MORE than 5 to cover
        ats_margin = actual_margin + market_spread

        # Determine market side
        if market_spread < 0:
            # Home was favored in market
            market_pick = 'home'
            ats_covered = ats_margin > 0  # Home covered if they beat the spread
        else:
            # Away was favored in market
            market_pick = 'away'
            ats_covered = ats_margin < 0  # Away covered if margin is negative

        # Determine model pick based on edge
        model_edge = market_spread - model_spread

        if abs(model_edge) < 1.0:
            # Edge too small - no clear pick
            return False, f"Edge too small ({model_edge:.1f})"

        # Model pick
        if model_spread < market_spread:
            # Model has home MORE favored than market (or away LESS favored)
            model_pick = 'home'
        else:
            # Model has away MORE favored than market (or home LESS favored)
            model_pick = 'away'

        # Was model correct?
        if model_pick == 'home':
            correct = ats_margin > 0
        else:
            correct = ats_margin < 0

        notes = f"Actual: {actual_margin:+d}, ATS vs market: {ats_margin:+.1f}"

        return correct, notes

    def determine_total_correctness(self, game_info: Dict, model_total: float,
                                    market_total: float) -> Tuple[bool, str]:
        """
        Determine if total prediction was correct

        Args:
            game_info: Game info dict with scores
            model_total: Model's projected total
            market_total: Market total

        Returns:
            Tuple of (was_correct, notes)
        """
        home_score = game_info['home_score']
        away_score = game_info['away_score']
        actual_total = home_score + away_score

        # Model edge
        model_edge = model_total - market_total

        if abs(model_edge) < 2.0:
            # Edge too small - no clear pick
            return False, f"Edge too small ({model_edge:.1f})"

        # Model pick
        if model_total > market_total:
            # Model projects HIGHER than market → OVER
            model_pick = 'over'
        else:
            # Model projects LOWER than market → UNDER
            model_pick = 'under'

        # Was model correct?
        if model_pick == 'over':
            correct = actual_total > market_total
        else:
            correct = actual_total < market_total

        notes = f"Actual: {actual_total}, vs market {market_total} ({actual_total - market_total:+.1f})"

        return correct, notes

    def classify_pick_type(self, edge: float, is_spread: bool,
                          model_line: float, market_line: float) -> str:
        """
        Classify pick type based on edge size and direction

        Args:
            edge: Edge in points (abs value)
            is_spread: True if spread, False if total
            model_line: Model's line
            market_line: Market line

        Returns:
            Pick type string
        """
        edge_abs = abs(edge)

        if is_spread:
            # Check if favorite flipped
            model_fav_home = model_line < 0
            market_fav_home = market_line < 0

            if model_fav_home != market_fav_home:
                return 'flipped_favorite'

            # Big edge
            if edge_abs >= 4.0:
                return 'spread_big_edge'

            # Small favorite or underdog value
            if edge_abs >= 2.0:
                if market_line > 0:  # Market has this team as dog
                    return 'spread_dog_value'
                else:
                    return 'spread_fav_small'

            return 'spread_dog_value'  # Default for spreads

        else:  # Total
            model_over = model_line > market_line

            if edge_abs >= 4.0:
                return 'total_over_big_edge' if model_over else 'total_under_big_edge'
            else:
                return 'total_over_value' if model_over else 'total_under_value'

    def determine_variance_flag(self, game_info: Dict) -> str:
        """
        Determine variance flag based on game characteristics

        Args:
            game_info: Game info dict

        Returns:
            'normal' or 'high_variance'
        """
        home_score = game_info['home_score']
        away_score = game_info['away_score']
        margin = abs(home_score - away_score)
        total = home_score + away_score

        # High variance indicators:
        # - Very close game (≤3 points)
        # - Very high scoring (≥260)
        # - Overtime (total ≥ 260 AND close)

        if margin <= 3:
            return 'high_variance'

        if total >= 260:
            return 'high_variance'

        return 'normal'

    def determine_injury_flag(self, prediction: Dict) -> str:
        """
        Determine injury flag from model prediction data

        Args:
            prediction: Model prediction dict

        Returns:
            'none', 'minor', or 'major'
        """
        # Check if prediction includes injury impact data
        injury_impact = prediction.get('injury_impact', {})

        home_impact = abs(injury_impact.get('home_total_adjustment', 0))
        away_impact = abs(injury_impact.get('away_total_adjustment', 0))
        max_impact = max(home_impact, away_impact)

        if max_impact >= 2.0:
            return 'major'
        elif max_impact >= 0.5:
            return 'minor'
        else:
            return 'none'

    def evaluate_game(self, game_info: Dict, prediction: Dict, odds: Dict) -> Optional[List[Dict]]:
        """
        Evaluate a single game and prepare performance log entries

        Args:
            game_info: Game result info
            prediction: Model prediction
            odds: Market odds

        Returns:
            List of row_dicts ready for logging (one for spread, one for total)
        """
        rows = []

        # Extract model predictions
        model_spread = prediction.get('spread', {}).get('rest_adjusted',
                                      prediction.get('spread', {}).get('baseline', None))
        model_total = prediction.get('total', {}).get('pace_adjusted',
                                     prediction.get('total', {}).get('baseline', None))

        if model_spread is None or model_total is None:
            print(f"  Missing model prediction for {game_info['game_id']}")
            return None

        # Market odds
        market_spread = odds.get('spread')
        market_total = odds.get('total')

        if market_spread is None or market_total is None:
            print(f"  Missing market odds for {game_info['game_id']}")
            return None

        # Common fields
        variance_flag = self.determine_variance_flag(game_info)
        injury_flag = self.determine_injury_flag(prediction)

        # Evaluate SPREAD
        spread_edge = market_spread - model_spread
        if abs(spread_edge) >= 1.0:  # Only log if meaningful edge
            spread_correct, spread_notes = self.determine_spread_correctness(
                game_info, model_spread, market_spread
            )

            pick_type = self.classify_pick_type(spread_edge, True, model_spread, market_spread)

            rows.append({
                'date': game_info['date'],
                'game_id': game_info['game_id'],
                'pick_type': pick_type,
                'edge_points': round(abs(spread_edge), 2),
                'model_line': round(model_spread, 1),
                'market_line': round(market_spread, 1),
                'result_correct': spread_correct,
                'variance_flag': variance_flag,
                'injury_flag': injury_flag,
                'notes': spread_notes
            })

        # Evaluate TOTAL
        total_edge = model_total - market_total
        if abs(total_edge) >= 2.0:  # Only log if meaningful edge
            total_correct, total_notes = self.determine_total_correctness(
                game_info, model_total, market_total
            )

            pick_type = self.classify_pick_type(total_edge, False, model_total, market_total)

            rows.append({
                'date': game_info['date'],
                'game_id': game_info['game_id'],
                'pick_type': pick_type,
                'edge_points': round(abs(total_edge), 2),
                'model_line': round(model_total, 1),
                'market_line': round(market_total, 1),
                'result_correct': total_correct,
                'variance_flag': variance_flag,
                'injury_flag': injury_flag,
                'notes': total_notes
            })

        return rows if rows else None

    def get_existing_entries(self) -> set:
        """
        Load existing entries from CSV to avoid duplicates

        Returns:
            Set of tuples (date, game_id, pick_type) already logged
        """
        csv_path = self.project_root / 'model_performance' / 'model_performance_log.csv'

        if not csv_path.exists():
            return set()

        existing = set()
        try:
            import csv
            with open(csv_path, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    key = (row['date'], row['game_id'], row['pick_type'])
                    existing.add(key)
        except Exception:
            pass

        return existing

    def update_performance_log(self):
        """
        Main function: Fetch yesterday's games, evaluate predictions, log results
        """
        print("="*80)
        print("NBA MODEL OUTCOME FETCHER")
        print("="*80)

        # Load existing entries to avoid duplicates
        existing_entries = self.get_existing_entries()
        if existing_entries:
            print(f"\n[0] Found {len(existing_entries)} existing entries in performance log")

        # Fetch yesterday's games
        print("\n[1] Fetching yesterday's completed games...")
        games = self.fetch_yesterdays_games()

        if not games:
            print("  No completed games found for yesterday")
            return

        print(f"  ✓ Found {len(games)} completed game(s)")

        # Get yesterday's date for prediction file
        yesterday = datetime.now() - timedelta(days=1)
        date_str = yesterday.strftime('%Y-%m-%d')

        # Load model predictions
        print(f"\n[2] Loading model predictions for {date_str}...")
        predictions = self.load_model_predictions(date_str)

        if not predictions:
            print("  No prediction file found - cannot evaluate")
            return

        print(f"  ✓ Loaded predictions for {len(predictions.get('games', []))} game(s)")

        # Process each game
        print(f"\n[3] Evaluating model performance...")
        total_logged = 0
        total_skipped = 0

        for game in games:
            print(f"\n  Processing: {game['game_id']}")
            print(f"    Final Score: {game['away_team']} {game['away_score']} @ "
                  f"{game['home_team']} {game['home_score']}")

            # Find matching prediction
            prediction = None
            for pred in predictions.get('games', []):
                pred_game_id = f"{self.get_team_abbrev(pred.get('away_team', ''))}@" \
                              f"{self.get_team_abbrev(pred.get('home_team', ''))}"
                if pred_game_id == game['game_id']:
                    prediction = pred
                    break

            if not prediction:
                print(f"    ⚠ No prediction found")
                continue

            # Fetch odds
            odds = self.fetch_game_odds(game['event_id'], game['comp_id'])

            if not odds:
                print(f"    ⚠ No odds available")
                continue

            print(f"    Market: Spread={odds['spread']:+.1f}, Total={odds['total']:.1f}")

            # Evaluate and log
            rows = self.evaluate_game(game, prediction, odds)

            if rows:
                for row in rows:
                    # Check if this entry already exists
                    entry_key = (row['date'], row['game_id'], row['pick_type'])

                    if entry_key in existing_entries:
                        total_skipped += 1
                        print(f"    ⊘ Skipped: {row['pick_type']} (already logged)")
                    else:
                        log_model_performance(row)
                        existing_entries.add(entry_key)  # Track it
                        total_logged += 1
                        print(f"    ✓ Logged: {row['pick_type']} "
                              f"({'CORRECT' if row['result_correct'] else 'INCORRECT'})")
            else:
                print(f"    ⚠ No edges met threshold")

        print(f"\n{'='*80}")
        print(f"SUMMARY: Logged {total_logged} pick(s) to performance tracker")
        if total_skipped > 0:
            print(f"         Skipped {total_skipped} duplicate(s)")
        print(f"{'='*80}\n")


def main():
    """Run outcome fetcher"""
    fetcher = OutcomeFetcher()
    fetcher.update_performance_log()


if __name__ == "__main__":
    main()
