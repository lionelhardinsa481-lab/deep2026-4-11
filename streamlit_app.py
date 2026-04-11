import streamlit as st
import ccxt
import pandas as pd
import numpy as np
import requests
import time
import json
import os
from datetime import datetime

# ================= 页面配置 =================
st.set_page_config(
    page_title="Crypto 实战信号监控 Pro",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ================= 自定义 CSS（美化界面） =================
st.markdown("""
<style>
    .main-header { font-size: 2.5rem; font-weight: 700; color: #0F52BA; margin-bottom: 0; }
    .sub-header { color: #666; margin-top: 0; }
    .metric-card { background: #f8f9fa; border-radius: 10px; padding: 15px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
    .stButton button { width: 100%; border-radius: 8px; font-weight: 600; }
    .signal-bull { color: #00C853; font-weight: bold; }
    .signal-bear { color: #FF1744; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ================= 配置区 =================
DINGTALK_WEBHOOK = "https://oapi.dingtalk.com/robot/send?access_token=4037d68aeb929fa3791713dc4b947565a938776fb2edca1c8040faa144b4e216"
WECOM_WEBHOOK = "在此粘贴你的企微 Webhook"
CACHE_FILE = "/tmp/signal_cache.json"
PORTFOLIO_FILE = "/tmp/portfolio.json"
HISTORY_FILE = "/tmp/history.json"

# ================= 持久化辅助函数 =================
def load_json(filepath, default):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                return json.load(f)
        except:
            return default
    return default

def save_json(filepath, data):
    try:
        with open(filepath, "w") as f:
            json.dump(data, f)
    except:
        pass

# ================= 初始化 Session State =================
if "cache_data" not in st.session_state:
    st.session_state.cache_data = load_json(CACHE_FILE, {})
if "portfolio" not in st.session_state:
    st.session_state.portfolio = load_json(PORTFOLIO_FILE, [])
if "history" not in st.session_state:
    st.session_state.history = load_json(HISTORY_FILE, [])

def save_all_states():
    save_json(CACHE_FILE, st.session_state.cache_data)
    save_json(PORTFOLIO_FILE, st.session_state.portfolio)
    save_json(HISTORY_FILE, st.session_state.history)

# 清理过期缓存（1小时）
now_ts = time.time()
st.session_state.cache_data = {k: v for k, v in st.session_state.cache_data.items() if now_ts - v < 3600}

# ================= 交易所连接 =================
@st.cache_resource
def get_smart_exchange():
    # 尝试 OKX
    try:
        ex = ccxt.okx({
            "options": {"defaultType": "swap"},
            "enableRateLimit": True,
            "timeout": 10000
        })
        ex.fetch_ticker("BTC/USDT:USDT")
        return ex, "OKX"
    except:
        pass
    # 尝试 Binance
    try:
        ex = ccxt.binance({
            "options": {"defaultType": "swap"},
            "enableRateLimit": True,
            "timeout": 10000,
            "urls": {"api": {"public": "https://api.binance.vision"}}
        })
        ex.fetch_ticker("BTC/USDT:USDT")
        return ex, "Binance"
    except:
        return None, "连接失败"

EXCHANGE, EXCHANGE_NAME = get_smart_exchange()

# ================= 核心币种列表（Top120 主流合约） =================
CORE_SYMBOLS = [
    "BTC/USDT:USDT", "ETH/USDT:USDT", "BNB/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT",
    "DOGE/USDT:USDT", "ADA/USDT:USDT", "TRX/USDT:USDT", "AVAX/USDT:USDT", "LINK/USDT:USDT",
    "TON/USDT:USDT", "DOT/USDT:USDT", "MATIC/USDT:USDT", "SHIB/USDT:USDT", "LTC/USDT:USDT",
    "UNI/USDT:USDT", "ATOM/USDT:USDT", "ETC/USDT:USDT", "FIL/USDT:USDT", "AAVE/USDT:USDT",
    "NEAR/USDT:USDT", "OP/USDT:USDT", "APT/USDT:USDT", "ARB/USDT:USDT", "STX/USDT:USDT",
    "WIF/USDT:USDT", "PEPE/USDT:USDT", "FET/USDT:USDT", "RENDER/USDT:USDT", "IMX/USDT:USDT",
    "SUI/USDT:USDT", "SEI/USDT:USDT", "TIA/USDT:USDT", "INJ/USDT:USDT", "RUNE/USDT:USDT",
    "FTM/USDT:USDT", "ALGO/USDT:USDT", "SAND/USDT:USDT", "MANA/USDT:USDT", "AXS/USDT:USDT",
    "GALA/USDT:USDT", "EOS/USDT:USDT", "XLM/USDT:USDT", "VET/USDT:USDT", "THETA/USDT:USDT",
    "ICP/USDT:USDT", "EGLD/USDT:USDT", "FLOW/USDT:USDT", "CHZ/USDT:USDT", "ENJ/USDT:USDT",
    "JUP/USDT:USDT", "W/USDT:USDT", "TAO/USDT:USDT", "AR/USDT:USDT", "BLUR/USDT:USDT",
    "SSV/USDT:USDT", "LDO/USDT:USDT", "GRT/USDT:USDT", "PENDLE/USDT:USDT", "PYTH/USDT:USDT",
    "JTO/USDT:USDT", "NOT/USDT:USDT", "BONK/USDT:USDT", "FLOKI/USDT:USDT", "BOME/USDT:USDT",
    "ORDI/USDT:USDT", "SATS/USDT:USDT", "ACE/USDT:USDT", "NFP/USDT:USDT", "AI/USDT:USDT",
    "ALT/USDT:USDT", "JASMY/USDT:USDT", "ONDO/USDT:USDT", "STRK/USDT:USDT", "MEME/USDT:USDT",
    "PIXEL/USDT:USDT", "PORTAL/USDT:USDT", "AEVO/USDT:USDT", "ETHFI/USDT:USDT", "TNSR/USDT:USDT",
    "OM/USDT:USDT", "REZ/USDT:USDT", "ZETA/USDT:USDT", "IO/USDT:USDT", "ZK/USDT:USDT",
    "ZRO/USDT:USDT", "TLM/USDT:USDT", "KAVA/USDT:USDT", "ROSE/USDT:USDT", "CRO/USDT:USDT",
    "DASH/USDT:USDT", "ZEC/USDT:USDT", "COMP/USDT:USDT", "MKR/USDT:USDT", "SNX/USDT:USDT",
    "LRC/USDT:USDT", "1INCH/USDT:USDT", "SXP/USDT:USDT", "HOT/USDT:USDT", "BTT/USDT:USDT",
    "WIN/USDT:USDT", "STORJ/USDT:USDT", "SKL/USDT:USDT", "CTSI/USDT:USDT", "DENT/USDT:USDT",
    "OCEAN/USDT:USDT", "TRB/USDT:USDT", "HIGH/USDT:USDT", "MAGIC/USDT:USDT", "YGG/USDT:USDT",
    "DYDX/USDT:USDT", "GMX/USDT:USDT", "API3/USDT:USDT", "COTI/USDT:USDT", "HBAR/USDT:USDT",
    "ALICE/USDT:USDT"
]
SYMBOLS = CORE_SYMBOLS

# ================= 辅助函数 =================
def fmt_price(p):
    if p < 0.01: return f"{p:.6f}"
    if p < 1: return f"{p:.4f}"
    if p < 100: return f"{p:.2f}"
    return f"{p:.1f}"

def send_push(text):
    webhooks = [w for w in [DINGTALK_WEBHOOK, WECOM_WEBHOOK] if w and "在此粘贴" not in w]
    for wh in webhooks:
        try:
            requests.post(wh, json={"msgtype":"text","text":{"content":f"【Crypto Pro】\n{text}"}}, timeout=5)
        except:
            pass

# ================= 技术指标计算 =================
def calculate_indicators(df):
    """计算所需全部技术指标"""
    df = df.copy()
    df['EMA50'] = df['c'].ewm(span=50, adjust=False).mean()
    df['EMA200'] = df['c'].ewm(span=200, adjust=False).mean()

    # MACD
    e12 = df['c'].ewm(span=12, adjust=False).mean()
    e26 = df['c'].ewm(span=26, adjust=False).mean()
    df['MACD'] = e12 - e26
    df['MACD_signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_H'] = 2 * (df['MACD'] - df['MACD_signal'])

    # 成交量均线
    df['Vol_MA20'] = df['v'].rolling(20).mean()

    # ATR 和 ADX
    df['TR'] = np.maximum(df['h'] - df['l'],
                          np.maximum(abs(df['h'] - df['c'].shift(1)),
                                     abs(df['l'] - df['c'].shift(1))))
    df['ATR14'] = df['TR'].rolling(14).mean()
    df['up_move'] = df['h'] - df['h'].shift(1)
    df['down_move'] = df['l'].shift(1) - df['l']
    df['plus_dm'] = np.where((df['up_move'] > df['down_move']) & (df['up_move'] > 0), df['up_move'], 0)
    df['minus_dm'] = np.where((df['down_move'] > df['up_move']) & (df['down_move'] > 0), df['down_move'], 0)
    df['plus_di'] = 100 * (df['plus_dm'].rolling(14).mean() / df['ATR14'])
    df['minus_di'] = 100 * (df['minus_dm'].rolling(14).mean() / df['ATR14'])
    df['dx'] = 100 * abs(df['plus_di'] - df['minus_di']) / (df['plus_di'] + df['minus_di'])
    df['ADX'] = df['dx'].rolling(14).mean()

    # 突破用指标
    df['HH20'] = df['h'].rolling(20).max().shift(1)
    df['Change'] = df['c'].pct_change()
    return df

def get_ohlcv(sym, tf, limit=300):
    try:
        if not EXCHANGE:
            return pd.DataFrame()
        ohlcv = EXCHANGE.fetch_ohlcv(sym, timeframe=tf, limit=limit)
        if not ohlcv:
            return pd.DataFrame()
        df = pd.DataFrame(ohlcv, columns=["ts","o","h","l","c","v"])
        df['dt'] = pd.to_datetime(df['ts'], unit='ms')
        return df
    except Exception:
        return pd.DataFrame()

# ================= 多时间框架趋势判断 =================
def get_big_trend(symbol, small_tf):
    """根据小周期选择合适的大周期进行趋势确认"""
    if small_tf in ['5m', '15m']:
        big_tf = '1h'
    elif small_tf == '1h':
        big_tf = '4h'
    else:
        big_tf = '1d'

    df_big = get_ohlcv(symbol, big_tf, 200)
    if df_big.empty or len(df_big) < 50:
        return 'neutral'

    df_big = calculate_indicators(df_big)
    last = df_big.iloc[-1]
    if last['EMA50'] > last['EMA200']:
        return 'up'
    elif last['EMA50'] < last['EMA200']:
        return 'down'
    else:
        return 'neutral'

# ================= 核心扫描与模拟盘管理 =================
def scan_and_manage(tf, cfg, enable_trend, enable_pump):
    new_signals = []
    logs = {"total": 0, "trend": 0, "pump": 0, "closed": 0}
    if not EXCHANGE:
        return pd.DataFrame(), logs

    # 获取所有需要检查的币种（包括持仓中的币种，防止漏网）
    pos_symbols = [f"{p['symbol']}/USDT:USDT" for p in st.session_state.portfolio if p['status'] == 'open']
    scan_list = list(set(SYMBOLS + pos_symbols))

    with st.status(f"🔍 正在扫描 {len(scan_list)} 个币种...", expanded=True) as status:
        # 先处理持仓的平仓检查
        for p in st.session_state.portfolio:
            if p['status'] != 'open':
                continue
            sym_full = f"{p['symbol']}/USDT:USDT"
            df = get_ohlcv(sym_full, tf, 100)
            if df.empty:
                continue
            df = calculate_indicators(df)
            last = df.iloc[-1]
            c, h, l = float(last['c']), float(last['h']), float(last['l'])

            exit_price = None
            reason = ""
            if p['direction'] == 'long':
                if l <= p['sl']:
                    exit_price, reason = p['sl'], "止损"
                elif h >= p['tp']:
                    exit_price, reason = p['tp'], "止盈"
            else:  # short
                if h >= p['sl']:
                    exit_price, reason = p['sl'], "止损"
                elif l <= p['tp']:
                    exit_price, reason = p['tp'], "止盈"

            if exit_price:
                pnl_pct = (exit_price - p['entry']) / p['entry'] if p['direction'] == 'long' else (p['entry'] - exit_price) / p['entry']
                p['status'] = 'closed'
                p['exit_price'] = exit_price
                p['pnl_pct'] = pnl_pct
                p['close_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                p['reason'] = reason

                # 移入历史
                st.session_state.history.insert(0, {
                    "symbol": p['symbol'],
                    "direction": p['direction'],
                    "entry": p['entry'],
                    "exit": exit_price,
                    "pnl_pct": pnl_pct,
                    "reason": reason,
                    "time": p['close_time']
                })

                logs["closed"] += 1
                emoji = "🎉" if pnl_pct > 0 else "💔"
                send_push(f"{emoji} {p['symbol']} {p['direction'].upper()} 平仓\n{reason}\n盈亏: {pnl_pct*100:.2f}%")

        # 过滤掉已平仓的持仓
        st.session_state.portfolio = [p for p in st.session_state.portfolio if p['status'] == 'open']

        # 开始扫描新信号
        for i, sym in enumerate(scan_list):
            if i % 20 == 0:
                status.update(label=f"扫描进度: {i}/{len(scan_list)} ({sym.split('/')[0]})")

            df = get_ohlcv(sym, tf, 250)
            if df.empty or len(df) < 100:
                continue
            df = calculate_indicators(df)
            logs["total"] += 1

            sym_name = sym.split("/")[0]
            last = df.iloc[-1]
            prev = df.iloc[-2]
            c, h, l = float(last['c']), float(last['h']), float(last['l'])
            candle_ts = int(last['ts'])

            # 检查是否已有持仓
            has_position = any(p['symbol'] == sym_name and p['status'] == 'open' for p in st.session_state.portfolio)
            if has_position:
                continue

            # 获取大周期趋势
            big_trend = get_big_trend(sym, tf)

            # 过滤极小波动
            volatility = (h - l) / c
            if volatility < 0.005:
                continue

            # --- 趋势策略 ---
            if enable_trend:
                key_t = f"T_{sym_name}_{tf}_{candle_ts}"
                if key_t not in st.session_state.cache_data:
                    ema50 = float(last['EMA50'])
                    ema200 = float(last['EMA200'])
                    macd_curr = float(last['MACD_H'])
                    macd_prev = float(prev['MACD_H'])
                    vol_curr = float(last['v'])
                    vol_ma = float(last['Vol_MA20'])
                    adx_curr = float(last['ADX'])
                    adx_prev = float(prev['ADX'])

                    # ADX 过滤 + 趋势增强
                    adx_ok = adx_curr > 20 and adx_curr > adx_prev

                    # 多头信号
                    uptrend = c > ema200 and ema50 > ema200
                    macd_cross_up = macd_prev < 0 and macd_curr > 0
                    vol_ok = vol_curr > vol_ma * cfg['trend_vol']

                    if uptrend and macd_cross_up and vol_ok and adx_ok:
                        # 大周期过滤
                        if big_trend == 'down':
                            continue
                        sl = l - 1.5 * (h - l)
                        tp = c + 2.0 * (c - sl)
                        vol_ratio = vol_curr / vol_ma

                        new_signals.append({
                            "币种": sym_name, "策略": "趋势", "方向": "多",
                            "入场": fmt_price(c), "止损": fmt_price(sl), "止盈": fmt_price(tp)
                        })
                        st.session_state.portfolio.append({
                            "symbol": sym_name, "direction": "long",
                            "entry": c, "sl": sl, "tp": tp,
                            "time": datetime.now().strftime("%H:%M"), "status": "open"
                        })
                        st.session_state.cache_data[key_t] = now_ts
                        logs["trend"] += 1
                        send_push(f"{sym_name} 🟢趋势多\nADX:{adx_curr:.1f} 量比:{vol_ratio:.1f}\n入:{fmt_price(c)} 损:{fmt_price(sl)}")

                    # 空头信号
                    downtrend = c < ema200 and ema50 < ema200
                    macd_cross_down = macd_prev > 0 and macd_curr < 0
                    if downtrend and macd_cross_down and vol_ok and adx_ok:
                        if big_trend == 'up':
                            continue
                        sl = h + 1.5 * (h - l)
                        tp = c - 2.0 * (sl - c)
                        vol_ratio = vol_curr / vol_ma

                        new_signals.append({
                            "币种": sym_name, "策略": "趋势", "方向": "空",
                            "入场": fmt_price(c), "止损": fmt_price(sl), "止盈": fmt_price(tp)
                        })
                        st.session_state.portfolio.append({
                            "symbol": sym_name, "direction": "short",
                            "entry": c, "sl": sl, "tp": tp,
                            "time": datetime.now().strftime("%H:%M"), "status": "open"
                        })
                        st.session_state.cache_data[key_t] = now_ts
                        logs["trend"] += 1
                        send_push(f"{sym_name} 🔴趋势空\nADX:{adx_curr:.1f} 量比:{vol_ratio:.1f}\n入:{fmt_price(c)} 损:{fmt_price(sl)}")

            # --- 异动策略 ---
            if enable_pump:
                key_p = f"P_{sym_name}_{tf}_{candle_ts}"
                if key_p not in st.session_state.cache_data:
                    hh20 = float(last['HH20'])
                    vol_curr = float(last['v'])
                    vol_ma = float(last['Vol_MA20'])
                    change = float(last['Change'])

                    breakout = c > hh20
                    vol_surge = vol_curr > vol_ma * cfg['vol_mult']
                    pump_ok = change > cfg['pump_pct']

                    if breakout and vol_surge and pump_ok:
                        # 大周期过滤
                        if big_trend == 'down':
                            continue
                        sl = l * 0.92
                        tp = c * 1.15
                        vol_ratio = vol_curr / vol_ma

                        new_signals.append({
                            "币种": sym_name, "策略": "异动", "方向": "突破",
                            "入场": fmt_price(c), "止损": fmt_price(sl), "止盈": fmt_price(tp)
                        })
                        st.session_state.portfolio.append({
                            "symbol": sym_name, "direction": "long",
                            "entry": c, "sl": sl, "tp": tp,
                            "time": datetime.now().strftime("%H:%M"), "status": "open"
                        })
                        st.session_state.cache_data[key_p] = now_ts
                        logs["pump"] += 1
                        send_push(f"{sym_name} 🚀异动突破\n涨幅:{change*100:.1f}% 量比:{vol_ratio:.1f}\n现:{fmt_price(c)} 损:{fmt_price(sl)}")

        status.update(label=f"✅ 扫描完成！总检测 {logs['total']} 币种，信号 {len(new_signals)} 个", state="complete")

    save_all_states()
    df_sig = pd.DataFrame(new_signals) if new_signals else pd.DataFrame(columns=["币种","策略","方向","入场","止损","止盈"])
    return df_sig, logs

# ================= 侧边栏 =================
st.sidebar.markdown("## ⚙️ 策略配置")
tf = st.sidebar.selectbox("🕰️ K线周期", ["5m", "15m", "1h", "4h"], index=1)
enable_trend = st.sidebar.checkbox("📈 趋势策略 (ADX增强)", value=True)
enable_pump = st.sidebar.checkbox("🚀 异动策略 (突破追涨)", value=True)

TF_THRESHOLDS = {
    "5m": {"pump_pct": 0.03, "vol_mult": 3.0, "trend_vol": 1.5},
    "15m": {"pump_pct": 0.04, "vol_mult": 2.5, "trend_vol": 1.5},
    "1h": {"pump_pct": 0.06, "vol_mult": 2.0, "trend_vol": 1.3},
    "4h": {"pump_pct": 0.08, "vol_mult": 1.8, "trend_vol": 1.2}
}
cfg = TF_THRESHOLDS[tf]

with st.sidebar.expander("📊 当前阈值", expanded=False):
    st.markdown(f"- 异动涨幅 ≥ **{cfg['pump_pct']*100:.0f}%**")
    st.markdown(f"- 异动量能 ≥ **{cfg['vol_mult']}x** 均量")
    st.markdown(f"- 趋势量能 ≥ **{cfg['trend_vol']}x** 均量")
    st.markdown(f"- ADX 过滤: **>20 且上升**")
    st.markdown(f"- 大周期过滤: **顺势开仓**")

st.sidebar.divider()
if st.sidebar.button("🧪 测试推送", use_container_width=True):
    send_push("【测试】通道正常，监控已就绪。")
    st.sidebar.success("已发送")

# ================= 主界面 =================
st.markdown('<p class="main-header">📊 币安/OKX 合约实战监控 Pro</p>', unsafe_allow_html=True)
st.markdown(f'<p class="sub-header">数据源: {EXCHANGE_NAME} | 监控: {len(SYMBOLS)} 币种 | 策略: ADX趋势 + 异动突破 + 多周期过滤</p>', unsafe_allow_html=True)

if not EXCHANGE:
    st.error("❌ 无法连接交易所，请稍后刷新。")
    st.stop()

# 执行扫描
df_sig, log_data = scan_and_manage(tf, cfg, enable_trend, enable_pump)

# --- 模拟盘战绩卡片 ---
st.subheader("💰 模拟盘战绩")
col1, col2, col3, col4 = st.columns(4)
total_trades = len(st.session_state.history)
wins = sum(1 for h in st.session_state.history if h['pnl_pct'] > 0)
win_rate = wins / total_trades if total_trades > 0 else 0
total_pnl = sum(h['pnl_pct'] for h in st.session_state.history) * 100
avg_pnl = total_pnl / total_trades if total_trades > 0 else 0

col1.metric("总交易", total_trades)
col2.metric("胜率", f"{win_rate*100:.1f}%")
col3.metric("总收益率", f"{total_pnl:.2f}%")
col4.metric("当前持仓", len(st.session_state.portfolio))

# --- 持仓与历史 Tab ---
tab1, tab2 = st.tabs(["📌 当前持仓", "📜 历史记录"])

with tab1:
    if not st.session_state.portfolio:
        st.info("暂无持仓")
    else:
        pos_data = []
        for p in st.session_state.portfolio:
            pos_data.append({
                "币种": p['symbol'],
                "方向": "🟢 多" if p['direction'] == 'long' else "🔴 空",
                "入场价": fmt_price(p['entry']),
                "止损": fmt_price(p['sl']),
                "止盈": fmt_price(p['tp']),
                "开仓时间": p['time']
            })
        st.dataframe(pd.DataFrame(pos_data), use_container_width=True, hide_index=True)

with tab2:
    if not st.session_state.history:
        st.info("暂无历史记录")
    else:
        hist_df = pd.DataFrame(st.session_state.history)
        hist_df['盈亏%'] = hist_df['pnl_pct'].apply(lambda x: f"{x*100:.2f}%")
        hist_df['结果'] = hist_df['pnl_pct'].apply(lambda x: "✅ 盈利" if x > 0 else "❌ 亏损")
        hist_df = hist_df[['symbol', 'direction', 'entry', 'exit', '盈亏%', '结果', 'reason', 'time']]
        st.dataframe(hist_df.head(20), use_container_width=True, hide_index=True)

# --- 本轮信号看板 ---
st.divider()
st.subheader("📡 本轮新信号")
if df_sig.empty:
    st.info("本轮未产生新信号，系统仍在监控中。")
else:
    # 样式美化
    def highlight_direction(val):
        if '多' in val or '突破' in val:
            return 'color: #00C853; font-weight: bold'
        elif '空' in val:
            return 'color: #FF1744; font-weight: bold'
        return ''
    styled = df_sig.style.applymap(highlight_direction, subset=['方向'])
    st.dataframe(styled, use_container_width=True, hide_index=True)

# --- 日志折叠栏 ---
with st.expander("📋 扫描详情", expanded=False):
    st.write(f"- 数据源: `{EXCHANGE_NAME}`")
    st.write(f"- 检测币种: `{log_data['total']}`")
    st.write(f"- 趋势策略触发: `{log_data['trend']}`")
    st.write(f"- 异动策略触发: `{log_data['pump']}`")
    st.write(f"- 平仓单数: `{log_data['closed']}`")

st.divider()
st.caption("⚠️ 模拟盘仅供策略验证，不构成投资建议。杠杆交易风险极高，请谨慎操作。")
