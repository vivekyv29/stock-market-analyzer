/* ── State ── */
let currentTicker = null;
let currentData   = null;
let priceChart    = null;

/* ── Nav routing ── */
document.querySelectorAll(".nav-link").forEach(link => {
  link.addEventListener("click", e => {
    e.preventDefault();
    const view = link.dataset.view;
    switchView(view);
    document.querySelectorAll(".nav-link").forEach(l => l.classList.remove("active"));
    link.classList.add("active");
  });
});

function switchView(name) {
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  document.getElementById(`view-${name}`).classList.add("active");
}

/* ── Search ── */
document.getElementById("searchBtn").addEventListener("click", doSearch);
document.getElementById("searchInput").addEventListener("keydown", e => {
  if (e.key === "Enter") doSearch();
});
document.querySelectorAll(".qp-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.getElementById("searchInput").value = btn.dataset.ticker;
    doSearch();
  });
});

function doSearch() {
  const ticker = document.getElementById("searchInput").value.trim().toUpperCase();
  if (!ticker) return;
  runAnalysis(ticker, "1y");
}

/* ── Period buttons ── */
document.querySelectorAll(".period-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".period-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    if (currentTicker) runAnalysis(currentTicker, btn.dataset.period);
  });
});

/* ── Core: fetch + render ── */
async function runAnalysis(ticker, period = "1y") {
  currentTicker = ticker;

  // Switch to analysis view
  switchView("analysis");
  document.querySelectorAll(".nav-link").forEach(l => l.classList.remove("active"));
  document.querySelector('[data-view="analysis"]').classList.add("active");

  // Show loading
  showLoading();

  try {
    const res = await fetch(`/api/analyze?ticker=${encodeURIComponent(ticker)}&period=${period}`);
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    currentData = data;
    hideLoading();
    renderAnalysis(data);
    renderPrediction(data);
  } catch (err) {
    hideLoading();
    showError(err.message || "Failed to fetch data. Check ticker and try again.");
  }
}

function showLoading() {
  document.getElementById("loadingOverlay").classList.remove("hidden");
  document.getElementById("analysisContent").classList.add("hidden");
  const steps = ["lstep1","lstep2","lstep3","lstep4"];
  let i = 0;
  steps.forEach(id => document.getElementById(id).classList.remove("active"));
  const iv = setInterval(() => {
    if (i < steps.length) {
      document.getElementById(steps[i]).classList.add("active");
      i++;
    } else {
      clearInterval(iv);
    }
  }, 700);
}

function hideLoading() {
  document.getElementById("loadingOverlay").classList.add("hidden");
  document.getElementById("analysisContent").classList.remove("hidden");
}

function showError(msg) {
  const toast = document.getElementById("errorToast");
  toast.textContent = "⚠ " + msg;
  toast.classList.remove("hidden");
  setTimeout(() => toast.classList.add("hidden"), 5000);
}

/* ── Render Analysis ── */
function renderAnalysis(d) {
  // Header
  document.getElementById("shTicker").textContent = d.ticker;
  document.getElementById("shName").textContent   = d.name;
  document.getElementById("shExchange").textContent = d.exchange;

  const sym  = d.currency === "INR" ? "₹" : d.currency === "USD" ? "$" : (d.currency || "");
  const price = fmt(d.current_price, sym);
  document.getElementById("shPrice").textContent = price;

  const changeEl = document.getElementById("shChange");
  const sign = d.change_amt >= 0 ? "+" : "";
  changeEl.textContent = `${sign}${fmt(d.change_amt, sym)} (${sign}${d.change_pct}%)`;
  changeEl.className = "sh-change " + (d.change_amt >= 0 ? "positive" : "negative");

  // Chart
buildPriceChart(
    d.history,
    sym,
    d.prediction.forecast_prices
);
  // Indicators
  const ind = d.indicators;

  // RSI
  const rsi = ind.rsi;
  document.getElementById("indRsi").textContent = rsi !== null ? rsi : "--";
  if (rsi !== null) {
    document.getElementById("rsiGauge").style.width = rsi + "%";
    let rsiLabel = "Neutral";
    if (rsi <= 30) rsiLabel = "Oversold";
    else if (rsi >= 70) rsiLabel = "Overbought";
    document.getElementById("indRsiLabel").textContent = rsiLabel;
  }

  // MACD
  if (ind.macd) {
    document.getElementById("indMacd").textContent = ind.macd.macd;
    const badge = document.getElementById("indMacdBadge");
    badge.textContent = ind.macd.label;
    badge.className = "ind-signal-badge " + (ind.macd.bullish ? "badge-bull" : "badge-bear");
  }

  // MAs
  document.getElementById("indMa50").textContent  = ind.ma50  ? fmt(ind.ma50,  sym) : "--";
  document.getElementById("indMa200").textContent = ind.ma200 ? fmt(ind.ma200, sym) : "--";
  document.getElementById("indTrend").textContent = ind.trend || "--";

  // Bollinger
  if (ind.bollinger) {
    document.getElementById("indBollU").textContent = fmt(ind.bollinger.upper, sym);
  }

  // Prediction
  document.getElementById("predCurrent").textContent = fmt(d.current_price, sym);
  if (d.prediction.next_day) {
    document.getElementById("predDay").textContent    = fmt(d.prediction.next_day,  sym);
    const gd = d.prediction.gain_day;
    const gainDayEl = document.getElementById("predDayGain");
    gainDayEl.textContent = (gd >= 0 ? "+" : "") + gd + "%";
    gainDayEl.className = "pred-gain " + (gd >= 0 ? "positive" : "negative");
  }
  if (d.prediction.next_week) {
    document.getElementById("predWeek").textContent   = fmt(d.prediction.next_week, sym);
    const gw = d.prediction.gain_week;
    const gainWkEl = document.getElementById("predWeekGain");
    gainWkEl.textContent = (gw >= 0 ? "+" : "") + gw + "%";
    gainWkEl.className = "pred-gain " + (gw >= 0 ? "positive" : "negative");
  }

  // Sentiment ring
  const sent = d.sentiment;
  const ringEl = document.getElementById("sentRing");
  const circumference = 201;
  const offset = circumference - (sent.score / 100) * circumference;
  ringEl.style.strokeDashoffset = offset;
  ringEl.style.stroke = sent.score >= 60 ? "var(--green)" : sent.score <= 40 ? "var(--red)" : "var(--yellow)";
  document.getElementById("sentScore").textContent = sent.score + "/100";
  document.getElementById("sentLabel").textContent = sent.label;

  // Sentiment sub-headlines
  const sentHl = document.getElementById("sentHeadlines");
  sentHl.innerHTML = "";
  (sent.headlines || []).slice(0, 2).forEach(h => {
    const el = document.createElement("div");
    el.textContent = "• " + h.substring(0, 80) + (h.length > 80 ? "…" : "");
    sentHl.appendChild(el);
  });

  // News list
  const nl = document.getElementById("newsList");
  nl.innerHTML = "";
  (sent.headlines || []).forEach(h => {
    const item = document.createElement("div");
    item.className = "news-item";
    const score = scoreSentiment(h);
    const badgeCls = score > 0 ? "nb-pos" : score < 0 ? "nb-neg" : "nb-neu";
    const badgeTxt = score > 0 ? "POS" : score < 0 ? "NEG" : "NEU";
    item.innerHTML = `<span class="news-badge ${badgeCls}">${badgeTxt}</span>${h}`;
    nl.appendChild(item);
  });
}
/* ── Build Chart ── */
function buildPriceChart(history, sym, forecastPrices = []) {

    console.log("Forecast Prices:", forecastPrices);

const closes = history.map(r => r.close);

    // Dynamic forecast labels
    const forecastLabels = [];
    for (let i = 1; i <= forecastPrices.length; i++) {
        forecastLabels.push("Day+" + i);
    }

    const labels = [
        ...history.map(r => r.date),
        ...forecastLabels
    ];

    if (priceChart) {
        priceChart.destroy();
        priceChart = null;
    }

    const ctx = document.getElementById("priceChart").getContext("2d");

    const gradient = ctx.createLinearGradient(0, 0, 0, 320);
    gradient.addColorStop(0, "rgba(0,229,255,.25)");
    gradient.addColorStop(1, "rgba(0,229,255,0)");

    priceChart = new Chart(ctx, {
        type: "line",
        data: {
            labels,
            datasets: [

                {
                    label: "Historical",
                    data: [
                        ...closes,
                        ...Array(forecastPrices.length).fill(null)
                    ],
                    borderColor: "rgba(0,229,255,1)",
                    borderWidth: 2,
                    pointRadius: 0,
                    fill: true,
                    backgroundColor: gradient,
                    tension: 0.3
                },

                {
                  label: "AI Forecast",
                  data: [
                    ...Array(closes.length - 1).fill(null),
                    closes[closes.length - 1],
                    ...forecastPrices
                ],
                    borderColor: "#ff6b35",
                    backgroundColor: "rgba(255,107,53,0.2)",
                    borderWidth: 15,
                    borderDash: [12, 6],
                    pointRadius: 12,
                    pointHoverRadius: 15,
                    pointBackgroundColor: "#ff0000",
                    pointBorderColor: "#ffffff",
                    pointBorderWidth: 2,
                    spanGaps: true,
                    showLine: true,
                    fill: false,
                    tension: 0
                }

            ]
        },

        options: {
            responsive: true,
            maintainAspectRatio: false,

            interaction: {
                mode: "index",
                intersect: false
            },

            plugins: {
                legend: {
                    display: true,
                    labels: {
                        color: "#ffffff"
                    }
                },

                tooltip: {
                    backgroundColor: "rgba(15,21,32,.95)",
                    titleColor: "#6b7794",
                    bodyColor: "#e8eaf0",
                    borderColor: "rgba(0,229,255,.2)",
                    borderWidth: 1,
                    callbacks: {
                        label: ctx =>
                            sym +
                            ctx.parsed.y.toLocaleString("en-IN", {
                                minimumFractionDigits: 2
                            })
                    }
                }
            },

            scales: {
                x: {
                    ticks: {
                        color: "#6b7794",
                        maxTicksLimit: 10,
                        font: {
                            family: "'Space Mono'"
                        }
                    },
                    grid: {
                        color: "rgba(255,255,255,.04)"
                    }
                },

                y: {
                    beginAtZero: false,

                    suggestedMin:
                        Math.min(...closes, ...forecastPrices) - 20,

                    suggestedMax:
                        Math.max(...closes, ...forecastPrices) + 20,

                    ticks: {
                        color: "#6b7794",
                        font: {
                            family: "'Space Mono'"
                        },
                        callback: v =>
                            sym + v.toLocaleString("en-IN")
                    },

                    grid: {
                        color: "rgba(255,255,255,.04)"
                    }
                }
            }
        }
    });

    console.log("Chart Created Successfully");
    console.log(priceChart.data.datasets);

    window.stockChart = priceChart;
}

/* ── Render Prediction View ── */
function renderPrediction(d) {

  document.getElementById("maeValue").textContent =
    d.prediction.mae;

document.getElementById("rmseValue").textContent =
    d.prediction.rmse;
    
  const sig = d.signal;
  document.getElementById("pvTicker").textContent = d.ticker + " — " + d.name;
  document.getElementById("signalText").textContent = sig.signal;

  const box = document.getElementById("signalBox");
  box.className = "signal-box " + sig.signal.toLowerCase();

  const pct = sig.confidence;
  document.getElementById("confBar").style.width = pct + "%";
  document.getElementById("confPct").textContent = pct + "%";

  // Weight bars (animate in)
  setTimeout(() => {
    document.getElementById("wbLstm").style.width = "100%";
    document.getElementById("wbTech").style.width = "100%";
    document.getElementById("wbSent").style.width = "100%";
  }, 300);

  // Reasons
  const rl = document.getElementById("reasonsList");
  rl.innerHTML = "";
  (sig.reasons || []).forEach(r => {
    const li = document.createElement("li");
    li.textContent = r;
    rl.appendChild(li);
  });
}

/* ── Helpers ── */
function fmt(n, sym = "") {
  if (n == null) return "--";
  return sym + n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const POS_WORDS = ["surge","rise","gain","profit","growth","record","beat","strong","buy","upgrade","bullish","rally","jump","soar","outperform","expand","revenue","dividend","positive","boom","success","win","milestone"];
const NEG_WORDS = ["fall","drop","loss","decline","weak","miss","sell","downgrade","bearish","plunge","crash","cut","layoff","concern","risk","debt","lawsuit","investigation","fraud","warning","negative","slump"];

function scoreSentiment(text) {
  const t = text.toLowerCase();
  const pos = POS_WORDS.filter(w => t.includes(w)).length;
  const neg = NEG_WORDS.filter(w => t.includes(w)).length;
  return pos - neg;
}
