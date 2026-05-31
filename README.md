# StockSense AI

AI-powered stock analysis dashboard — 5-phase pipeline:
**Historical Data → Technical Indicators → ML Prediction → News Sentiment → BUY/SELL/HOLD Signal**

---

## Setup

```bash
cd stock-ai
pip install -r requirements.txt
python app.py
```

Then open: **http://localhost:5000**

---

## Features

| Phase | What it does |
|-------|-------------|
| 1 — Data | Fetches real-time price & 1–2 year history via Yahoo Finance API |
| 2 — Technical | RSI, MACD, 50/200-day MA, Bollinger Bands, Trend detection |
| 3 — Prediction | Linear Regression (scikit-learn) on scaled price history → Next Day & Next Week price |
| 4 — Sentiment | Keyword-based scoring of Yahoo Finance news headlines (0–100) |
| 5 — AI Signal | Weighted BUY/SELL/HOLD: LSTM 40% + Technical 30% + Sentiment 30% |

---

## Supported Tickers

| Indian Stocks | US Stocks |
|---------------|-----------|
| RELIANCE.NS   | AAPL      |
| TCS.NS        | TSLA      |
| INFY.NS       | MSFT      |
| ETERNAL.NS    | GOOGL     |
| HDFC.NS       | AMZN      |
| WIPRO.NS      | NVDA      |

Any Yahoo Finance ticker works (append `.NS` for NSE, `.BO` for BSE).

---

## Tech Stack

- **Backend**: Flask + Python
- **Data**: Yahoo Finance public API (no key required)
- **ML**: scikit-learn `LinearRegression` + `MinMaxScaler`
- **Frontend**: HTML/CSS/JS + Chart.js
- **Indicators**: pandas / numpy (custom implementation)

---

## Notes

- No API key needed — uses Yahoo Finance's public endpoints
- Prediction is educational only — not financial advice
- To upgrade: replace `LinearRegression` with TensorFlow LSTM model in `predict_prices()`
- To add FinBERT: replace `fetch_news_sentiment()` with HuggingFace transformers pipeline
