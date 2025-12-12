"""
NBA Model Performance Logger
=============================

Minimal performance tracking system that logs model correctness WITHOUT storing
game scores or outcomes. Runs independently from prediction pipeline.

Usage:
    from model_performance.performance_logger import log_model_performance

    log_model_performance({
        "date": "2025-12-11",
        "game_id": "BOS@MIL",
        "pick_type": "spread_big_edge",
        "edge_points": 4.5,
        "model_line": -7.1,
        "market_line": -2.6,
        "result_correct": True,
        "variance_flag": "normal",
        "injury_flag": "major",
        "notes": "Giannis OUT"
    })
"""

import os
import csv
from pathlib import Path
from typing import Dict, Any


class PerformanceLogger:
    """Logs model performance without storing game outcomes"""

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

    # Valid flags
    VALID_VARIANCE_FLAGS = {'normal', 'high_variance'}
    VALID_INJURY_FLAGS = {'none', 'minor', 'major'}

    # CSV header
    CSV_HEADER = [
        'date',
        'game_id',
        'pick_type',
        'edge_points',
        'model_line',
        'market_line',
        'result_correct',
        'confidence_band',
        'variance_flag',
        'injury_flag',
        'notes'
    ]

    def __init__(self, csv_path: str = None):
        """
        Initialize performance logger

        Args:
            csv_path: Path to CSV file (default: model_performance/model_performance_log.csv)
        """
        if csv_path is None:
            # Get directory of this file
            module_dir = Path(__file__).parent
            csv_path = module_dir / 'model_performance_log.csv'

        self.csv_path = Path(csv_path)
        self._ensure_csv_exists()

    def _ensure_csv_exists(self):
        """Create CSV with headers if it doesn't exist (never overwrite)"""
        if not self.csv_path.exists():
            # Create parent directories if needed
            self.csv_path.parent.mkdir(parents=True, exist_ok=True)

            # Write header row
            with open(self.csv_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(self.CSV_HEADER)

            print(f"✓ Created performance log: {self.csv_path}")

    def _calculate_confidence_band(self, edge_points: float) -> str:
        """
        Calculate confidence band based on edge size

        Args:
            edge_points: Edge in points

        Returns:
            Confidence band: 'low', 'medium', 'high', or 'elite'
        """
        edge_abs = abs(edge_points)

        if edge_abs < 2.0:
            return 'low'
        elif edge_abs < 4.0:
            return 'medium'
        elif edge_abs < 6.0:
            return 'high'
        else:
            return 'elite'

    def _validate_game_id(self, game_id: str) -> bool:
        """
        Validate game_id format

        Args:
            game_id: Game ID string

        Returns:
            True if valid format (TEAM1@TEAM2)
        """
        if '@' not in game_id:
            return False

        parts = game_id.split('@')
        if len(parts) != 2:
            return False

        # Check both parts are uppercase and non-empty
        return all(part.isupper() and len(part) > 0 for part in parts)

    def _validate_row(self, row_dict: Dict[str, Any]) -> None:
        """
        Validate all required fields in row_dict

        Args:
            row_dict: Dictionary with row data

        Raises:
            ValueError: If validation fails
        """
        # Check required fields
        required_fields = [
            'date', 'game_id', 'pick_type', 'edge_points',
            'model_line', 'market_line', 'result_correct',
            'variance_flag', 'injury_flag'
        ]

        for field in required_fields:
            if field not in row_dict:
                raise ValueError(f"Missing required field: {field}")

        # Validate pick_type
        if row_dict['pick_type'] not in self.VALID_PICK_TYPES:
            raise ValueError(
                f"Invalid pick_type: {row_dict['pick_type']}. "
                f"Must be one of: {', '.join(self.VALID_PICK_TYPES)}"
            )

        # Validate game_id format
        if not self._validate_game_id(row_dict['game_id']):
            raise ValueError(
                f"Invalid game_id format: {row_dict['game_id']}. "
                f"Must be TEAM1@TEAM2 (uppercase, no spaces)"
            )

        # Validate variance_flag
        if row_dict['variance_flag'] not in self.VALID_VARIANCE_FLAGS:
            raise ValueError(
                f"Invalid variance_flag: {row_dict['variance_flag']}. "
                f"Must be one of: {', '.join(self.VALID_VARIANCE_FLAGS)}"
            )

        # Validate injury_flag
        if row_dict['injury_flag'] not in self.VALID_INJURY_FLAGS:
            raise ValueError(
                f"Invalid injury_flag: {row_dict['injury_flag']}. "
                f"Must be one of: {', '.join(self.VALID_INJURY_FLAGS)}"
            )

        # Validate numeric fields
        try:
            float(row_dict['edge_points'])
            float(row_dict['model_line'])
            float(row_dict['market_line'])
        except (ValueError, TypeError):
            raise ValueError("edge_points, model_line, and market_line must be numeric")

        # Validate boolean
        if not isinstance(row_dict['result_correct'], bool):
            raise ValueError("result_correct must be a boolean (True/False)")

    def log_performance(self, row_dict: Dict[str, Any]) -> None:
        """
        Log model performance to CSV

        Args:
            row_dict: Dictionary with required fields:
                - date (str): YYYY-MM-DD
                - game_id (str): TEAM1@TEAM2
                - pick_type (str): One of VALID_PICK_TYPES
                - edge_points (float): Edge in points
                - model_line (float): Model's line
                - market_line (float): Market line
                - result_correct (bool): Was prediction correct
                - variance_flag (str): 'normal' or 'high_variance'
                - injury_flag (str): 'none', 'minor', or 'major'
                - notes (str, optional): Additional notes

        Raises:
            ValueError: If validation fails
        """
        # Validate all fields
        self._validate_row(row_dict)

        # Calculate confidence band
        confidence_band = self._calculate_confidence_band(row_dict['edge_points'])

        # Convert boolean to string
        result_correct_str = 'TRUE' if row_dict['result_correct'] else 'FALSE'

        # Prepare row for CSV
        csv_row = [
            row_dict['date'],
            row_dict['game_id'],
            row_dict['pick_type'],
            round(row_dict['edge_points'], 2),
            round(row_dict['model_line'], 2),
            round(row_dict['market_line'], 2),
            result_correct_str,
            confidence_band,
            row_dict['variance_flag'],
            row_dict['injury_flag'],
            row_dict.get('notes', '')  # Optional field
        ]

        # Append to CSV (never overwrite)
        with open(self.csv_path, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(csv_row)

        print(f"✓ Logged performance: {row_dict['game_id']} - {row_dict['pick_type']} ({confidence_band})")


# Global logger instance
_logger = None


def get_logger() -> PerformanceLogger:
    """Get or create global logger instance"""
    global _logger
    if _logger is None:
        _logger = PerformanceLogger()
    return _logger


def log_model_performance(row_dict: Dict[str, Any]) -> None:
    """
    Public API: Log model performance

    Args:
        row_dict: Dictionary with performance data (see PerformanceLogger.log_performance)

    Example:
        log_model_performance({
            "date": "2025-12-11",
            "game_id": "BOS@MIL",
            "pick_type": "spread_big_edge",
            "edge_points": 4.5,
            "model_line": -7.1,
            "market_line": -2.6,
            "result_correct": True,
            "variance_flag": "normal",
            "injury_flag": "major",
            "notes": "Giannis OUT"
        })
    """
    logger = get_logger()
    logger.log_performance(row_dict)


if __name__ == "__main__":
    # Test the logger
    print("Testing Performance Logger")
    print("=" * 80)

    # Example log entry
    test_entry = {
        "date": "2025-12-11",
        "game_id": "BOS@MIL",
        "pick_type": "spread_big_edge",
        "edge_points": 4.5,
        "model_line": -7.1,
        "market_line": -2.6,
        "result_correct": True,
        "variance_flag": "normal",
        "injury_flag": "major",
        "notes": "Giannis OUT - system test"
    }

    log_model_performance(test_entry)

    print("\nTest complete! Check model_performance_log.csv")
