# 13F Hedge Fund Tracker

A comprehensive 13F holdings tracking and analytics system for 50+ active hedge funds.

## Features

- **ETL Pipeline**: Automated data fetching from SEC EDGAR (submissions JSON + 13F XML infoTable)
- **Delta Engine**: Track NEW / SOLD / ADD / REDUCE positions quarter-over-quarter
- **Jaccard Analysis**: Measure stock-picking similarity between funds
- **Crowding Score**: Identify consensus trades and crowded positions
- **Sector Weights**: GICS sector allocation analysis
- **Streamlit Dashboard**: Interactive heatmap, fund drill-down, and stock drill-down views

## Quick Start

### 1. Setup Environment

```bash
# Install dependencies
pip install -e ".[dev]"

# Copy environment file
cp .env.example .env
# Edit .env with your SEC User-Agent (required for EDGAR access)
```

### 2. Initialize Database

```bash
# SQLite (default — DATABASE_URL=sqlite:///./hedge_fund.db in .env)
python scripts/init_db.py
python scripts/seed_funds.py
```

For PostgreSQL, uncomment the `DATABASE_URL` line in `.env` (or run `docker-compose up -d`).

### 3. Load Data

```bash
# Option A: Use mock data for demonstration (no network needed)
python scripts/backfill.py --mock

# Option B: Fetch real data from SEC EDGAR (requires SEC User-Agent)
python scripts/backfill.py
```

### 4. Run Analytics

```bash
python -c "from analytics.runner import run_analytics; run_analytics()"
```

### 5. Launch Dashboard

```bash
streamlit run dashboard/app.py
```

## One-Command Setup

```bash
python scripts/run_full_pipeline.py --mock
```

## Project Structure

```
hedge_fund_tracker/
├── config/           # Configuration and fund list
├── db/               # SQLAlchemy models and engine
├── etl/              # Data fetching, parsing, and pipeline
├── analytics/        # Delta, Jaccard, Crowding, Sector analysis
├── dashboard/        # Streamlit UI
├── scheduler/        # Cron job for auto-updates
├── scripts/          # One-off scripts
└── tests/            # pytest suite
```

## Data Sources

1. **Primary**: SEC EDGAR
   - Submissions JSON: `https://data.sec.gov/submissions/CIK{cik_padded}.json` — for filing list
   - 13F XML infoTable: `https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{infotable.xml}` — for holdings detail
2. **Optional**: Financial Modeling Prep API (for sector data)

## Notes

- **SOLD != Liquidation**: 13F has a disclosure threshold. A "SOLD" position may simply be below the reporting threshold.
- **Report Date vs Filing Date**: Report date is quarter-end; filing date is typically ~45 days later.
- **All values are in $K** (thousands of dollars) as per 13F specification.

## License

MIT
