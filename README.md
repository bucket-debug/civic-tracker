# civic-tracker

A daily-updated US government transparency website that aggregates public data from federal sources to make civic information more accessible.

## Data Sources

- **congress.gov** — legislative activity, bill tracking, and voting records
- **FEC (Federal Election Commission)** — campaign finance and donor data
- **NewsAPI** — news coverage of government and policy topics

## Project Structure

```
civic-tracker/
├── data/        # JSON files storing fetched and processed data
├── scripts/     # Python scripts for fetching and processing data
└── site/        # Static HTML website files
```

## Configuration

API keys are read from environment variables. Copy `.env.example` to `.env` and fill in your keys:

| Variable           | Source                          |
|--------------------|---------------------------------|
| `CONGRESS_API_KEY` | https://api.congress.gov/sign-up |
| `FEC_API_KEY`      | https://api.open.fec.gov/developers |
| `NEWS_API_KEY`     | https://newsapi.org/register    |

## Setup

```bash
pip install -r requirements.txt
```

Set the required environment variables (or use a `.env` file with `python-dotenv`), then run the data fetch scripts to populate `data/` before opening the site.
