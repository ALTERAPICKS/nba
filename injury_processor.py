"""
ESPN Injury Data Processor
Pure availability pipeline - NO statistical modifications allowed
"""

import requests
from typing import Dict, List, Optional
from datetime import datetime


class InjuryProcessor:
    """
    Processes ESPN injury data into clean availability status
    DOES NOT modify team statistics or projections
    """

    # ESPN Team ID mapping (NBA team name → ESPN ID)
    ESPN_TEAM_MAP = {
        'Atlanta Hawks': 1,
        'Boston Celtics': 2,
        'Brooklyn Nets': 17,
        'Charlotte Hornets': 30,
        'Chicago Bulls': 4,
        'Cleveland Cavaliers': 5,
        'Dallas Mavericks': 6,
        'Denver Nuggets': 7,
        'Detroit Pistons': 8,
        'Golden State Warriors': 9,
        'Houston Rockets': 10,
        'Indiana Pacers': 11,
        'Los Angeles Clippers': 12,
        'Los Angeles Lakers': 13,
        'Memphis Grizzlies': 29,
        'Miami Heat': 14,
        'Milwaukee Bucks': 15,
        'Minnesota Timberwolves': 16,
        'New Orleans Pelicans': 3,
        'New York Knicks': 18,
        'Oklahoma City Thunder': 25,
        'Orlando Magic': 19,
        'Philadelphia 76ers': 20,
        'Phoenix Suns': 21,
        'Portland Trail Blazers': 22,
        'Sacramento Kings': 23,
        'San Antonio Spurs': 24,
        'Toronto Raptors': 28,
        'Utah Jazz': 26,
        'Washington Wizards': 27
    }

    # Status conversion rules (ESPN → Model)
    STATUS_RULES = {
        'OUT': {
            'model_status': 'unavailable',
            'apply_impact': True
        },
        'DOUBTFUL': {
            'model_status': 'unavailable',
            'apply_impact': True
        },
        'QUESTIONABLE': {
            'model_status': 'available',
            'apply_impact': False  # CRITICAL: No impact for questionable
        },
        'PROBABLE': {
            'model_status': 'available',
            'apply_impact': True
        },
        'ACTIVE': {
            'model_status': 'available',
            'apply_impact': True
        }
    }

    def __init__(self):
        """Initialize injury processor"""
        self.base_url = "http://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams"

    def get_espn_team_id(self, nba_team_name: str) -> Optional[int]:
        """
        Get ESPN team ID from NBA team name

        Args:
            nba_team_name: Full NBA team name (e.g., "Boston Celtics")

        Returns:
            ESPN team ID or None if not found
        """
        return self.ESPN_TEAM_MAP.get(nba_team_name)

    def fetch_team_injuries(self, nba_team_name: str) -> List[Dict]:
        """
        Fetch injury data for a team from ESPN API

        Args:
            nba_team_name: Full NBA team name

        Returns:
            List of player injury objects
        """
        espn_id = self.get_espn_team_id(nba_team_name)

        if espn_id is None:
            print(f"Warning: Team '{nba_team_name}' not found in ESPN mapping")
            return []

        url = f"{self.base_url}/{espn_id}/roster"

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            injuries = []

            for player in data.get('athletes', []):
                player_name = player.get('displayName', '')
                player_status = player.get('status', {}).get('name', 'ACTIVE')
                player_injuries = player.get('injuries', [])

                # If player has injury data, use most recent injury status
                if player_injuries:
                    # ESPN injury format: [{'status': 'Out', 'date': '2025-12-06T01:16Z'}]
                    most_recent_injury = player_injuries[0]
                    injury_status = most_recent_injury.get('status', 'ACTIVE').upper()
                    injury_date = most_recent_injury.get('date', '')

                    injuries.append({
                        'player_name': player_name,
                        'espn_status': injury_status,
                        'injury_date': injury_date
                    })

            return injuries

        except requests.RequestException as e:
            print(f"Error fetching injuries for {nba_team_name}: {e}")
            return []

    def process_injury_status(self, espn_status: str) -> Dict[str, any]:
        """
        Convert ESPN injury status to model status

        Args:
            espn_status: ESPN injury status (OUT, DOUBTFUL, QUESTIONABLE, PROBABLE, ACTIVE)

        Returns:
            Dict with model_status and apply_impact
        """
        # Normalize status
        espn_status_upper = espn_status.upper()

        # Handle variations
        if 'OUT' in espn_status_upper:
            espn_status_upper = 'OUT'
        elif 'DAY-TO-DAY' in espn_status_upper or 'DAY TO DAY' in espn_status_upper:
            # Day-to-Day typically means questionable
            espn_status_upper = 'QUESTIONABLE'

        # Get status rule or default to ACTIVE
        rule = self.STATUS_RULES.get(espn_status_upper, self.STATUS_RULES['ACTIVE'])

        return {
            'model_status': rule['model_status'],
            'apply_impact': rule['apply_impact']
        }

    def generate_injury_report(self, nba_team_name: str) -> Dict:
        """
        Generate clean injury availability report for a team

        Args:
            nba_team_name: Full NBA team name

        Returns:
            Clean injury report with availability status
        """
        injuries = self.fetch_team_injuries(nba_team_name)

        injury_report = []

        for injury in injuries:
            player_name = injury['player_name']
            espn_status = injury['espn_status']

            # Process status
            status_info = self.process_injury_status(espn_status)

            injury_report.append({
                'player_name': player_name,
                'espn_status': espn_status,
                'model_status': status_info['model_status'],
                'apply_impact': status_info['apply_impact']
            })

        return {
            'team': nba_team_name,
            'injury_report': injury_report,
            'report_timestamp': datetime.now().isoformat()
        }

    def get_unavailable_players(self, nba_team_name: str) -> List[str]:
        """
        Get list of unavailable player names for a team

        Args:
            nba_team_name: Full NBA team name

        Returns:
            List of player names who are unavailable
        """
        report = self.generate_injury_report(nba_team_name)

        unavailable = [
            player['player_name']
            for player in report['injury_report']
            if player['model_status'] == 'unavailable'
        ]

        return unavailable

    def print_injury_report(self, nba_team_name: str):
        """
        Print formatted injury report

        Args:
            nba_team_name: Full NBA team name
        """
        report = self.generate_injury_report(nba_team_name)

        print(f"\n{'='*80}")
        print(f"INJURY REPORT: {report['team']}")
        print(f"Timestamp: {report['report_timestamp']}")
        print(f"{'='*80}")

        if not report['injury_report']:
            print("✓ No injuries reported")
            return

        for player in report['injury_report']:
            status_icon = "❌" if player['model_status'] == 'unavailable' else "✓"
            impact_text = "IMPACT" if player['apply_impact'] else "NO IMPACT"

            print(f"\n{status_icon} {player['player_name']}")
            print(f"   ESPN Status: {player['espn_status']}")
            print(f"   Model Status: {player['model_status'].upper()}")
            print(f"   Apply Impact: {impact_text}")

        print(f"\n{'='*80}\n")


if __name__ == "__main__":
    # Test the injury processor
    processor = InjuryProcessor()

    # Test with teams that had injuries today
    test_teams = [
        'Milwaukee Bucks',
        'New Orleans Pelicans',
        'Boston Celtics',
        'Golden State Warriors'
    ]

    print("TESTING INJURY PROCESSOR")
    print("="*80)

    for team in test_teams:
        processor.print_injury_report(team)

        # Show unavailable players
        unavailable = processor.get_unavailable_players(team)
        if unavailable:
            print(f"Unavailable players: {', '.join(unavailable)}\n")
