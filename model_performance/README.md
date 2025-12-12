# NBA Model Performance Tracking System

Complete observational system for tracking model prediction correctness over time.

## 🎯 Purpose

Track your NBA model's performance WITHOUT storing game scores or interfering with prediction logic. This system runs **independently** and **after games complete** to evaluate pick accuracy.

## 📁 Files Created

```
/model_performance/
├── performance_logger.py          (Core logging module)
├── outcome_fetcher.py             (Automatic game evaluation)
├── save_predictions_helper.py     (Helper for saving predictions)
├── model_performance_log.csv      (Performance data - auto-created)
├── USAGE_GUIDE.txt               (Logger usage guide)
├── OUTCOME_FETCHER_GUIDE.txt     (Fetcher usage guide)
├── INTEGRATION_EXAMPLE.txt       (Integration examples)
└── README.md                     (This file)

/model_output/
└── YYYY-MM-DD_projections.json   (Your model's predictions)
```

## 🚀 Quick Start

### Step 1: Save Predictions (Game Day)

After running your model, save predictions to JSON:

```bash
python3 master_projection_engine.py
# → Saves to: model_output/2025-12-11_projections.json
```

See `INTEGRATION_EXAMPLE.txt` for how to integrate prediction saving.

### Step 2: Evaluate Results (Next Day)

After games complete, run:

```bash
python3 model_performance/outcome_fetcher.py
```

This will:
- ✅ Fetch yesterday's completed games
- ✅ Get final scores from ESPN
- ✅ Get closing odds from ESPN
- ✅ Load your predictions
- ✅ Evaluate correctness
- ✅ Log results to CSV

## 📊 What Gets Tracked

### Spreads
- Edge ≥ 1.0 points → Evaluated
- Pick types: `spread_dog_value`, `spread_fav_small`, `spread_big_edge`, `flipped_favorite`

### Totals
- Edge ≥ 2.0 points → Evaluated
- Pick types: `total_over_value`, `total_under_value`, `total_over_big_edge`, `total_under_big_edge`

### Auto-Calculated
- **Confidence bands**: low (0-1.9), medium (2.0-3.9), high (4.0-5.9), elite (6.0+)
- **Variance flag**: high_variance (close/OT games) or normal
- **Injury flag**: major (≥2.0 impact), minor (≥0.5 impact), none

## 📈 CSV Output

All results logged to `model_performance_log.csv`:

```csv
date,game_id,pick_type,edge_points,model_line,market_line,result_correct,confidence_band,variance_flag,injury_flag,notes
2025-12-11,BOS@MIL,spread_big_edge,4.5,-7.1,-2.6,TRUE,high,normal,major,Giannis OUT
2025-12-11,POR@NOP,total_over_value,3.1,240.6,237.5,TRUE,medium,normal,minor,Fast pace game
```

## 🔧 Manual Logging (Optional)

You can also manually log individual picks:

```python
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
```

## 📚 Documentation

- **USAGE_GUIDE.txt** - Complete logger API reference
- **OUTCOME_FETCHER_GUIDE.txt** - How to use automatic evaluation
- **INTEGRATION_EXAMPLE.txt** - Code examples for integration

## ⚠️ Important Notes

- ✅ Does NOT modify model logic
- ✅ Does NOT change predictions
- ✅ Runs independently after games complete
- ✅ Purely observational tracking layer

## 🧪 Testing

Test the logger:
```bash
python3 model_performance/performance_logger.py
```

Test outcome fetcher (requires prediction file + completed games):
```bash
python3 model_performance/outcome_fetcher.py
```

## 📊 Analysis Ideas

Once you have data, analyze:
- Win rate by pick type
- Win rate by confidence band
- Win rate by injury flag
- ROI by edge size
- Spread vs total accuracy
- Home vs away performance

## 🛡️ Data Safety

- CSV is append-only (never overwrites)
- Auto-creates files/folders if missing
- Validates all data before logging
- Handles API errors gracefully

---

**Ready to track your model's performance over time!** 🚀
