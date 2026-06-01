from flask import Flask, render_template, jsonify, request
import json
import math
import random
from yahooquery import search
import requests
import pandas as pd
import numpy as np
import os

from datetime import datetime, timedelta
from transformers import pipeline
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_absolute_error
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout
from tensorflow.keras.callbacks import EarlyStopping
from flask import Flask, render_template, jsonify, request, redirect, session, url_for
from flask_bcrypt import Bcrypt

app = Flask(__name__)

@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = (
        "no-cache, no-store, must-revalidate"
    )
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

bcrypt = Bcrypt(app)
app.secret_key = "stocksenseai_secret_key"
print("Loading FinBERT...")

finbert = pipeline(
    "sentiment-analysis",
    model="ProsusAI/finbert"
)

print("FinBERT loaded!")

POSITIVE_WORDS = [
    "surge", "rise", "gain", "profit", "growth",
    "record", "beat", "strong", "buy", "upgrade",
    "bullish", "rally", "jump", "soar",
    "outperform", "expand", "revenue",
    "dividend", "positive", "boom",
    "success", "win", "milestone"
]

NEGATIVE_WORDS = [
    "fall", "drop", "loss", "decline",
    "weak", "miss", "sell", "downgrade",
    "bearish", "plunge", "crash",
    "cut", "layoff", "concern",
    "risk", "debt", "lawsuit",
    "investigation", "fraud",
    "warning", "negative", "slump"
]
# ── Yahoo Finance helpers ──────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

def yf_quote(ticker):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d"
    r = requests.get(url, headers=HEADERS, timeout=10)
    r.raise_for_status()
    data = r.json()
    meta = data["chart"]["result"][0]["meta"]
    return meta

def yf_history(ticker, period="1y"):
    range_map = {"1mo": "1mo", "3mo": "3mo", "6mo": "6mo", "1y": "1y", "2y": "2y"}
    rng = range_map.get(period, "1y")
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?interval=1d&range={rng}"
    )
    r = requests.get(url, headers=HEADERS, timeout=10)
    r.raise_for_status()
    data = r.json()
    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    closes = result["indicators"]["quote"][0]["close"]
    opens  = result["indicators"]["quote"][0].get("open", [None]*len(closes))
    highs  = result["indicators"]["quote"][0].get("high", [None]*len(closes))
    lows   = result["indicators"]["quote"][0].get("low",  [None]*len(closes))
    volumes= result["indicators"]["quote"][0].get("volume",[None]*len(closes))
    rows = []
    for i, ts in enumerate(timestamps):
        if closes[i] is not None:
            rows.append({
                "date": datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d"),
                "open":   round(opens[i],  2) if opens[i]  else None,
                "high":   round(highs[i],  2) if highs[i]  else None,
                "low":    round(lows[i],   2) if lows[i]   else None,
                "close":  round(closes[i], 2),
                "volume": volumes[i] if volumes[i] else 0,
            })
    return rows, result["meta"]

def yf_summary(ticker):
    url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}?modules=assetProfile,summaryDetail,defaultKeyStatistics,financialData"
    r = requests.get(url, headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.json().get("quoteSummary", {}).get("result", [{}])[0]

# ── Technical Indicators ───────────────────────────────────────────────────────

def calc_rsi(closes, period=14):
    closes = pd.Series(closes)
    delta = closes.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return round(float(rsi.dropna().iloc[-1]), 2)

def calc_macd(closes):
    closes = pd.Series(closes)
    ema12 = closes.ewm(span=12).mean()
    ema26 = closes.ewm(span=26).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9).mean()
    hist = macd_line - signal_line
    last_macd   = round(float(macd_line.iloc[-1]), 4)
    last_signal = round(float(signal_line.iloc[-1]), 4)
    last_hist   = round(float(hist.iloc[-1]), 4)
    bullish = last_macd > last_signal
    return {
        "macd": last_macd,
        "signal": last_signal,
        "histogram": last_hist,
        "bullish": bullish,
        "label": "Bullish" if bullish else "Bearish",
    }

def calc_ma(closes, window):
    s = pd.Series(closes)
    val = s.rolling(window).mean().dropna()
    return round(float(val.iloc[-1]), 2) if len(val) else None

def calc_bollinger(closes, window=20):
    s = pd.Series(closes)
    mid  = s.rolling(window).mean()
    std  = s.rolling(window).std()
    upper = mid + 2*std
    lower = mid - 2*std
    return {
        "upper": round(float(upper.iloc[-1]), 2),
        "mid":   round(float(mid.iloc[-1]),   2),
        "lower": round(float(lower.iloc[-1]), 2),
    }

def determine_trend(closes, ma50, ma200):
    price = closes[-1]
    if ma50 and ma200:
        if price > ma50 > ma200:
            return "Strong Uptrend"
        elif price < ma50 < ma200:
            return "Strong Downtrend"
        elif ma50 > ma200:
            return "Uptrend"
        else:
            return "Downtrend"
    return "Sideways"

# ── ML Prediction (Linear Regression on scaled data) ──────────────────────────

def predict_prices(closes):
    if len(closes) < 100:
        return None, None, []

    data = np.array(closes).reshape(-1, 1)

    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled_data = scaler.fit_transform(data)

    sequence_length = 60

    X = []
    y = []

    for i in range(sequence_length, len(scaled_data)):
        X.append(scaled_data[i-sequence_length:i, 0])
        y.append(scaled_data[i, 0])

    X = np.array(X)
    y = np.array(y)

    X = X.reshape((X.shape[0], X.shape[1], 1))

    model = Sequential()

    model.add(
        LSTM(
            64,
            return_sequences=True,
            input_shape=(sequence_length, 1)
        )
    )

    model.add(Dropout(0.2))

    model.add(
        LSTM(
            32,
            return_sequences=False
        )
    )

    model.add(Dropout(0.2))

    model.add(Dense(16, activation="relu"))
    model.add(Dense(1))

    model.compile(
        optimizer="adam",
        loss="mean_squared_error"
    )

    early_stop = EarlyStopping(
        monitor="loss",
        patience=3,
        restore_best_weights=True
    )

    model.fit(
        X,
        y,
        epochs=3,
        batch_size=16,
        verbose=0,
        callbacks=[early_stop]
    )

    preds = model.predict(X, verbose=0)

    actual = scaler.inverse_transform(
        y.reshape(-1, 1)
    )

    predicted = scaler.inverse_transform(
        preds
    )

    mae = round(
        mean_absolute_error(actual, predicted),
        2
    )

    rmse = round(
        np.sqrt(
            np.mean(
                (actual - predicted) ** 2
            )
        ),
        2
    )

    last_60_days = scaled_data[-60:]

    X_test = np.array([last_60_days])
    X_test = X_test.reshape((1, 60, 1))

    next_day_scaled = model.predict(
        X_test,
        verbose=0
    )

    next_day_price = scaler.inverse_transform(
        next_day_scaled
    )[0][0]
    forecast_prices = []

    future_window = last_60_days.copy()

    for _ in range(30):

        pred = model.predict(
            future_window.reshape(1, 60, 1),
            verbose=0
        )

        forecast_prices.append(
            round(
                float(
                    scaler.inverse_transform(pred)[0][0]
                ),
                2
            )
        )

        future_window = np.vstack([
            future_window[1:],
            pred
        ])

    next_week_price = forecast_prices[-1]

    return (
    round(float(next_day_price), 2),
    round(float(next_week_price), 2),
    forecast_prices,
    mae,
    rmse
)


def fetch_news_sentiment(ticker):
    # Try Yahoo Finance news
    try:
        url = f"https://query1.finance.yahoo.com/v1/finance/search?q={ticker}&newsCount=10&quotesCount=0"
        r = requests.get(url, headers=HEADERS, timeout=8)
        data = r.json()
        news_items = data.get("news", [])
    except Exception:
        news_items = []

    headlines = [n.get("title", "") for n in news_items[:10]]

    if not headlines:
        # Fallback synthetic headlines
        headlines = [f"{ticker} stock update", f"{ticker} market analysis"]

    results = finbert(headlines)
    print("FinBERT Results:", results[:3])

    scores = []

    for r in results:

        if r["label"].lower() == "positive":
            scores.append(
                50 + r["score"] * 50
            )

        elif r["label"].lower() == "negative":
            scores.append(
                50 - r["score"] * 50
            )

        else:
            scores.append(50)

    sentiment_score = int(
        sum(scores) / len(scores)
    )
    if sentiment_score >= 60:
        label = "Positive"
    elif sentiment_score <= 40:
        label = "Negative"
    else:
        label = "Neutral"

    return {
        "label": label,
        "score": sentiment_score,
        "headlines": headlines[:8],
    }

# ── AI Signal ─────────────────────────────────────────────────────────────────

def generate_signal(rsi, macd, trend, sentiment, pred_day, current_price):

    score = 0
    reasons = []

    lstm_confidence = 0

    # LSTM Component
    if pred_day and current_price:

        gain_pct = (
            (pred_day - current_price)
            / current_price
        ) * 100

        prediction_strength = abs(gain_pct)

        if prediction_strength >= 5:
            lstm_confidence = 95
        elif prediction_strength >= 3:
            lstm_confidence = 85
        elif prediction_strength >= 1:
            lstm_confidence = 75
        else:
            lstm_confidence = 60

        if gain_pct > 1:
            score += 40
            reasons.append(
                f"LSTM predicts +{gain_pct:.1f}% gain tomorrow"
            )

        elif gain_pct > 0:
            score += 25
            reasons.append(
                f"LSTM predicts slight upward movement (+{gain_pct:.1f}%)"
            )

        elif gain_pct < -1:
            score += 5
            reasons.append(
                f"LSTM predicts -{abs(gain_pct):.1f}% drop tomorrow"
            )

        else:
            score += 15
            reasons.append(
                "LSTM predicts flat movement"
            )

        reasons.append(
            f"LSTM confidence: {lstm_confidence}%"
        )

    # Technical Component
    tech_score = 0

    if rsi:

        if 40 < rsi < 70:
            tech_score += 15
            reasons.append(
                f"RSI at {rsi} (healthy zone)"
            )

        elif rsi <= 30:
            tech_score += 20
            reasons.append(
                f"RSI oversold at {rsi}"
            )

        elif rsi >= 70:
            tech_score += 5
            reasons.append(
                f"RSI overbought at {rsi}"
            )

    if macd and macd.get("bullish"):
        tech_score += 15
        reasons.append(
            "MACD bullish crossover"
        )

    score += min(tech_score, 30)

    # Sentiment Component
    sent_score_raw = sentiment.get(
        "score",
        50
    )

    score += int(
        (sent_score_raw / 100) * 30
    )

    reasons.append(
        f"News sentiment: {sentiment.get('label')} ({sent_score_raw}/100)"
    )

    confidence = min(score, 98)

    if confidence >= 65:
        signal = "BUY"

    elif confidence <= 35:
        signal = "SELL"

    else:
        signal = "HOLD"

    return {
        "signal": signal,
        "confidence": confidence,
        "lstm_confidence": lstm_confidence,
        "model": "LSTM Neural Network",
        "reasons": reasons
    }
# ── Routes ─────────────────────────────────────────────────────────────────────

KNOWN_STOCKS = {
    "SUZLON ENERGY": "SUZLON.NS",
    "SUZLON": "SUZLON.NS",
    "RELIANCE": "RELIANCE.NS",
    "TATA CONSULTANCY SERVICES": "TCS.NS",
    "TCS": "TCS.NS",
    "INFOSYS": "INFY.NS",
    "INFY": "INFY.NS",
    "HDFC BANK": "HDFCBANK.NS",
    "HDFCBANK": "HDFCBANK.NS"
}

def find_symbol(query):
    try:
        result = search(query)

        quotes = result.get("quotes", [])

        if quotes:
            return quotes[0]["symbol"]

    except Exception as e:
        print("Search Error:", e)

    return query
def resolve_ticker(symbol):
    symbol = symbol.strip().upper()

    if symbol in KNOWN_STOCKS:
        return KNOWN_STOCKS[symbol]

    if "." in symbol:
        return symbol

    candidates = [
        symbol,
        f"{symbol}.NS",
        f"{symbol}.BO"
    ]

    for candidate in candidates:
        try:
            url = (
                f"https://query1.finance.yahoo.com/v8/finance/chart/"
                f"{candidate}?interval=1d&range=5d"
            )

            r = requests.get(
                url,
                headers=HEADERS,
                timeout=5
            )

            if r.status_code == 200:
                data = r.json()

                if data.get("chart", {}).get("result"):
                    return candidate

        except:
            pass

    return symbol

@app.route("/")
def index():

    if "user" not in session:
        return redirect("/login")

    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        hashed_password = bcrypt.generate_password_hash(
            password
        ).decode("utf-8")

        users = []

        if os.path.exists("users.json"):
            with open("users.json", "r") as f:
                users = json.load(f)

        users.append({
            "username": username,
            "password": hashed_password
        })

        with open("users.json", "w") as f:
            json.dump(users, f, indent=4)

        return redirect("/login")

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        if os.path.exists("users.json"):

            with open("users.json", "r") as f:
                users = json.load(f)

            for user in users:

                if (
                    user["username"] == username
                    and bcrypt.check_password_hash(
                        user["password"],
                        password
                    )
                ):

                    session["user"] = username

                    return redirect("/")

        return "Invalid Username or Password"

    return render_template("login.html")

@app.route("/logout")
def logout():

    session.clear()

    response = redirect("/login")

    response.headers["Cache-Control"] = (
        "no-cache, no-store, must-revalidate"
    )

    return response

@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()

    q = find_symbol(q)

    q = resolve_ticker(find_symbol(q))
    if not q:
        return jsonify({"error": "No ticker provided"}), 400
    try:
        meta = yf_quote(q)
        return jsonify({
            "ticker": q,
            "name": meta.get("longName") or meta.get("shortName") or q,
            "exchange": meta.get("exchangeName", ""),
            "currency": meta.get("currency", "USD"),
            "price": round(meta.get("regularMarketPrice", 0), 2),
            "previous_close": round(meta.get("previousClose") or meta.get("chartPreviousClose") or 0, 2),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/analyze")
def api_analyze():
    ticker = request.args.get("ticker", "").strip()
    print("INPUT TICKER:", ticker)

    ticker = resolve_ticker(find_symbol(ticker))
    print("RESOLVED TICKER:", ticker)

    print("Ticker received:", ticker)


    period = request.args.get("period", "1y")
    if not ticker:
        return jsonify({"error": "No ticker"}), 400

    try:
        rows, meta = yf_history(ticker, period)
        if not rows:
            return jsonify({"error": "No data returned"}), 404

        closes  = [r["close"]  for r in rows]
        volumes = [r["volume"] for r in rows]

        # Indicators
        rsi   = calc_rsi(closes) if len(closes) >= 15 else None
        macd  = calc_macd(closes) if len(closes) >= 30 else None
        ma50  = calc_ma(closes, 50)
        ma200 = calc_ma(closes, 200)
        boll  = calc_bollinger(closes) if len(closes) >= 20 else None
        trend = determine_trend(closes, ma50, ma200)

        # Prediction
        pred_day, pred_week, forecast_prices, mae, rmse = predict_prices(closes)
        # Sentiment
        sentiment = fetch_news_sentiment(ticker)

        # AI Signal
        current_price = closes[-1]
        signal_data = generate_signal(rsi, macd, trend, sentiment, pred_day, current_price)

        # Price change
        prev_close = meta.get("previousClose") or meta.get("chartPreviousClose") or closes[-2]
        change_amt = round(current_price - prev_close, 2)
        change_pct = round((change_amt / prev_close) * 100, 2) if prev_close else 0

        return jsonify({
            "ticker": ticker,
            "name": meta.get("longName") or meta.get("shortName") or ticker,
            "exchange": meta.get("exchangeName", ""),
            "currency": meta.get("currency", "USD"),
            "current_price": current_price,
            "change_amt": change_amt,
            "change_pct": change_pct,
            "history": rows,
            "indicators": {
                "rsi": rsi,
                "macd": macd,
                "ma50": ma50,
                "ma200": ma200,
                "bollinger": boll,
                "trend": trend,
            },
            "prediction": {
                "next_day":  pred_day,
                "next_week": pred_week,
                "forecast_prices": forecast_prices,
                "mae": mae,
                "rmse": rmse,
                "gain_day":  round((pred_day  - current_price) / current_price * 100, 2) if pred_day  else None,
                "gain_week": round((pred_week - current_price) / current_price * 100, 2) if pred_week else None,
            },
            "sentiment": sentiment,
            "signal": signal_data,
        })

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)
