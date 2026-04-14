import streamlit as st
import ccxt
import pandas as pd
import numpy as np
import requests
import time
import json
import os
from datetime import datetime
import plotly.graph_objects as go

# ================= 页面配置 =================
st.set_page_config(
    page_title="Crypto Signal Pro",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ================= 极致 UI 美化 CSS =================
st.markdown("""
<style>
    /* 全局背景与字体优化 */
    .stApp { background-color: #f4f7f9; }
    .main-header { font-size: 2.8rem; font-weight: 800; color: #1E3A8A; margin-bottom: 0.5rem; text-align: center; }
    .sub-header { color: #64748b; margin-top: 0; text-align: center; margin-bottom: 2rem; }
    
    /* 指标卡片美化 */
    [data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: 700; color: #1e293b; }
    .metric-container { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); }
    
    /* 侧边栏样式 */
    section[data-testid="stSidebar"] { background-color: #1e293b; color: white; }
    section[data-testid="stSidebar"] .stMarkdown { color: #cbd5e1; }
    
    /* 状态标签样式 */
    .signal-high { background-color: #dcfce7; color: #166534; padding: 4px 12px; border-radius: 20px; font-weight: 600; font-size: 0.8rem; }
    .signal-low { background-color: #fef9c3; color: #854d0e; padding: 4px 12px; border-radius: 20px; font-weight: 600; font-size: 0.8rem; }
    
    /* 自定义按钮 */
    .stButton button { width: 100%; border-radius: 8px; background-color: #2563eb; color: white; border: none; padding: 0.5rem; transition: all 0.3s; }
    .stButton button:hover { background-color: #1d4ed8; transform: translateY(-1px); }
</style>
""", unsafe_allow_html=True)

# ================= 常量与持久化 =================
CACHE_FILE = "/tmp/signal_cache.json"
PORTFOLIO_FILE = "/tmp/portfolio.json"
HISTORY_FILE = "/tmp/history.json"

def load_json(filepath, default):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f: return json.load(f)
        except: return default
    return default

def save_json(filepath, data):
    try:
        with open(filepath, "w") as f: json.dump(data, f)
    except: pass

# ================= 初始化状态 =================
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

# ================= 交易所逻辑 =================
@st.cache_resource
def get_exchange():
    try:
        # 尝试连接 OKX
        ex = ccxt.okx({"options": {"defaultType": "swap"}, "enableRateLimit": True, "timeout": 15000})
        ex.fetch_ticker("BTC/USDT:USDT")
        return ex, "OKX"
    except:
        try:
            # 备选 Binance
            ex = ccxt.binance({"options": {"defaultType": "swap"}, "enableRateLimit": True, "timeout": 15000})
            return ex, "Binance"
        except:
            return None, "Connection Failed"

EXCHANGE, EXCHANGE_NAME = get_exchange()

# ================= 核心币种 =================
SYMBOLS = [
    "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT", "XRP/USDT:USDT",
    "DOGE/USDT:USDT", "ADA/USDT:USDT", "AVAX/USDT:USDT", "LINK/USDT:USDT", "SUI/USDT:USDT",
    "ORDI/USDT:USDT", "PEPE/USDT:USDT", "WIF/USDT:USDT", "FET/USDT:USDT", "TIA/USDT:USDT",
    "NEAR/USDT:USDT", "OP/USDT:USDT", "ARB/USDT:USDT", "APT/USDT:USDT", "PENDLE/USDT:USDT"
] # 这里可以根据需要继续添加

# ================= 策略逻辑函数 =================
def fmt_price(p):
    if p < 0.0001: return f"{p:.8f}"
    if p < 1: return f"{p:.4f}"
    return f"{p:.2f}"

def send_push(webhook, text):
    if not webhook or "在此粘贴" in webhook: return
    try:
        requests.post(webhook, json={"msgtype":"text","text":{"content":f"【Signal Pro】\n{text}"}}, timeout=5)
    except: pass

def calculate_indicators(df):
    df = df.copy()
    # 均线系统
    df['EMA50'] = df['c'].ewm(span=50, adjust=False).mean()
    df['EMA200'] = df['c'].ewm(span=200, adjust=False).mean()
    # MACD
    e12 = df['c'].ewm(span=12, adjust=False).mean()
    e26 = df['c'].ewm(span=26, adjust=False).mean()
    df['MACD'] = e12 - e26
    df['MACD_signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_H'] = 2 * (df['MACD'] - df['MACD_signal'])
    # 成交量
    df['Vol_MA20'] = df['v'].rolling(20).mean()
    # ATR & ADX
    df['TR'] = np.maximum(df['h'] - df['l'], 
                          np.maximum(abs(df['h'] - df['l'].shift(1)), abs(df['l'] - df['c'].shift(1))))
    df['ATR14'] = df['TR'].rolling(14).mean()
    
    up = df['h'] - df['h'].shift(1)
    dn = df['l'].shift(1) - df['l']
    plus_dm = np.where((up > dn) & (up > 0), up, 0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0)
    
    tr_sum = df['TR'].rolling(14).sum()
    df['plus_di'] = 100 * (pd.Series(plus_dm).rolling(14).sum() / tr_sum)
    df['minus_di'] = 100 * (pd.Series(minus_dm).rolling(14).sum() / tr_sum)
    df['dx'] = 100 * abs(df['plus_di'] - df['minus_di']) / (df['plus_di'] + df['minus_di'])
    df['ADX'] = df['dx'].rolling(14).mean()
    
    df['HH20'] = df['h'].rolling(20).max().shift(1)
    df['Change'] = df['c'].pct_change()
    return df

def get_big_trend(symbol, tf):
    big_tf = '1h' if tf in ['5m', '15m'] else '4h'
    try:
        ohlcv = EXCHANGE.fetch_ohlcv(symbol, timeframe=big_tf, limit=100)
        df = pd.DataFrame(ohlcv, columns=["ts","o","h","l","c","v"])
        ema50 = df['c'].ewm(span=50, adjust=False).mean().iloc[-1]
        ema200 = df['c'].ewm(span=200, adjust=False).mean().iloc[-1]
        return 'up' if ema50 > ema200 else 'down'
    except: return 'neutral'

# ================= 核心扫描引擎 =================
def run_scanner(tf, cfg, mode, webhook):
    new_signals = []
    logs = {"total": 0, "closed": 0}
    
    # 1. 检查持仓 (模拟平仓逻辑)
    for p in st.session_state.portfolio:
        if p['status'] != 'open': continue
        try:
            ticker = EXCHANGE.fetch_ticker(f"{p['symbol']}/USDT:USDT")
            curr_p = ticker['last']
            exit_p, reason = None, ""
            
            if p['direction'] == 'long':
                if curr_p <= p['sl']: exit_p, reason = p['sl'], "Stop Loss"
                elif curr_p >= p['tp']: exit_p, reason = p['tp'], "Take Profit"
            else:
                if curr_p >= p['sl']: exit_p, reason = p['sl'], "Stop Loss"
                elif curr_p <= p['tp']: exit_p, reason = p['tp'], "Take Profit"
            
            if exit_p:
                pnl = (exit_p - p['entry'])/p['entry'] if p['direction']=='long' else (p['entry'] - exit_p)/p['entry']
                p['status'] = 'closed'
                st.session_state.history.insert(0, {**p, "exit": exit_p, "pnl": pnl, "reason": reason, "time": datetime.now().strftime("%m-%d %H:%M")})
                logs["closed"] += 1
                send_push(webhook, f"🔔 {p['symbol']} 平仓: {reason}\n盈亏: {pnl*100:.2f}%")
        except: continue
    
    st.session_state.portfolio = [p for p in st.session_state.portfolio if p['status'] == 'open']

    # 2. 扫描新信号
    with st.status("🚀 引擎加速扫描中...", expanded=True) as status:
        for sym in SYMBOLS:
            try:
                ohlcv = EXCHANGE.fetch_ohlcv(sym, timeframe=tf, limit=200)
                df = calculate_indicators(pd.DataFrame(ohlcv, columns=["ts","o","h","l","c","v"]))
                last, prev = df.iloc[-1], df.iloc[-2]
                logs["total"] += 1
                
                # 过滤已持仓币种
                sym_name = sym.split("/")[0]
                if any(p['symbol'] == sym_name for p in st.session_state.portfolio): continue
                
                big_trend = get_big_trend(sym, tf)
                atr = last['ATR14']
                
                # --- 趋势策略 ---
                if cfg['enable_trend']:
                    key = f"T_{sym_name}_{tf}_{last['ts']}"
                    if key not in st.session_state.cache_data:
                        # 逻辑：EMA金叉/多头 + MACD柱状图反转 + ADX强趋势
                        up_cond = last['c'] > last['EMA200'] and last['EMA50'] > last['EMA200']
                        macd_cross = prev['MACD_H'] < 0 and last['MACD_H'] > 0
                        adx_ok = last['ADX'] > 20
                        
                        if up_cond and macd_cross and adx_ok and (mode=="激进" or big_trend=="up"):
                            sl = last['c'] - (2 * atr)
                            tp = last['c'] + (4 * atr)
                            new_signals.append({"币种": sym_name, "策略": "趋势", "方向": "多", "价格": last['c'], "SL": sl, "TP": tp})
                            st.session_state.portfolio.append({"symbol":sym_name,"direction":"long","entry":last['c'],"sl":sl,"tp":tp,"status":"open","time":datetime.now().strftime("%H:%M")})
                            st.session_state.cache_data[key] = time.time()
                            send_push(webhook, f"📈 {sym_name} 趋势看多\n入场: {fmt_price(last['c'])}\n止损: {fmt_price(sl)}")

                # --- 异动策略 ---
                if cfg['enable_pump']:
                    key = f"P_{sym_name}_{tf}_{last['ts']}"
                    if key not in st.session_state.cache_data:
                        vol_ok = last['v'] > last['Vol_MA20'] * cfg['vol_mult']
                        breakout = last['c'] > last['HH20']
                        pump_ok = last['Change'] > cfg['pump_pct']
                        
                        if breakout and vol_ok and pump_ok:
                            sl = last['c'] - (1.5 * atr)
                            tp = last['c'] * 1.1 # 异动通常博取10%波动
                            new_signals.append({"币种": sym_name, "策略": "异动", "方向": "突破", "价格": last['c'], "SL": sl, "TP": tp})
                            st.session_state.portfolio.append({"symbol":sym_name,"direction":"long","entry":last['c'],"sl":sl,"tp":tp,"status":"open","time":datetime.now().strftime("%H:%M")})
                            st.session_state.cache_data[key] = time.time()
                            send_push(webhook, f"🚀 {sym_name} 暴力突破\n涨幅: {last['Change']*100:.1f}%")

            except: continue
        status.update(label="✅ 扫描任务完成", state="complete")
    
    save_all_states()
    return pd.DataFrame(new_signals), logs

# ================= 侧边栏交互 =================
with st.sidebar:
    st.title("🛠️ 策略控制台")
    mode = st.radio("选择运行模式", ["保守 (同步大周期)", "激进 (忽略大周期)"])
    tf = st.selectbox("监控周期", ["5m", "15m", "1h", "4h"], index=1)
    
    with st.expander("🔔 推送设置", expanded=True):
        webhook = st.text_input("Webhook 地址", placeholder="在此粘贴钉钉/企微链接")
        if st.button("🧪 测试推送"):
            send_push(webhook, "测试信息：监控系统已连接成功！")
            st.toast("已发送测试消息")

    st.divider()
    st.subheader("⚙️ 阈值微调")
    enable_t = st.toggle("开启趋势策略", value=True)
    enable_p = st.toggle("开启异动策略", value=True)
    
    pump_val = st.slider("异动起步涨幅 (%)", 1.0, 10.0, 3.0) / 100
    vol_mult = st.slider("成交量倍数", 1.5, 5.0, 2.5)
    
    cfg = {"enable_trend": enable_t, "enable_pump": enable_p, "pump_pct": pump_val, "vol_mult": vol_mult}

# ================= 主界面布局 =================
st.markdown('<div class="main-header">CRYPTO SIGNAL PRO</div>', unsafe_allow_html=True)
st.markdown(f'<div class="sub-header">当前数据源: {EXCHANGE_NAME} | 监控中: {len(SYMBOLS)} 币种</div>', unsafe_allow_html=True)

if not EXCHANGE:
    st.error("无法连接交易所 API，请检查网络或代理设置。")
    st.stop()

# 核心执行
df_sig, log_info = run_scanner(tf, cfg, mode, webhook)

# 看板数据
c1, c2, c3, c4 = st.columns(4)
total_h = st.session_state.history
wins = [h for h in total_h if h['pnl'] > 0]
win_rate = (len(wins)/len(total_h)*100) if total_h else 0
total_pnl = sum(h['pnl'] for h in total_h) * 100

with c1: st.metric("胜率", f"{win_rate:.1f}%", delta=f"{len(wins)} 胜")
with c2: st.metric("累计盈亏", f"{total_pnl:.2f}%")
with c3: st.metric("活跃持仓", len(st.session_state.portfolio))
with c4: st.metric("总交易次数", len(total_h))

# 标签页布局
t1, t2, t3 = st.tabs(["🔥 实时信号", "📊 当前持仓", "📜 历史对账"])

with t1:
    if df_sig.empty:
        st.info("当前市场波动平稳，暂无符合策略的信号。")
    else:
        # 使用自定义表格显示新信号
        for _, row in df_sig.iterrows():
            with st.container():
                st.markdown(f"""
                <div style="background: white; border-left: 5px solid #2563eb; padding: 15px; border-radius: 8px; margin-bottom: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                    <span class="signal-high">{row['策略']}</span> 
                    <strong style="font-size: 1.2rem; margin-left: 10px;">{row['币种']} {row['方向']}</strong>
                    <div style="margin-top: 10px; display: flex; gap: 20px; color: #475569;">
                        <span>入场: <b>{fmt_price(row['价格'])}</b></span>
                        <span style="color: #dc2626;">止损: {fmt_price(row['SL'])}</span>
                        <span style="color: #16a34a;">止盈: {fmt_price(row['TP'])}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

with t2:
    if not st.session_state.portfolio:
        st.write("目前没有空闲仓位")
    else:
        pos_df = pd.DataFrame(st.session_state.portfolio)
        st.dataframe(pos_df[['symbol','direction','entry','sl','tp','time']], use_container_width=True)

with t3:
    if not st.session_state.history:
        st.write("等待第一笔交易完成...")
    else:
        h_df = pd.DataFrame(st.session_state.history)
        h_df['盈亏%'] = h_df['pnl'].apply(lambda x: f"{x*100:.2f}%")
        st.dataframe(h_df[['symbol','direction','entry','exit','盈亏%','reason','time']], use_container_width=True)

# 底部扫描日志
with st.expander("📋 扫描日志"):
    st.caption(f"最后更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    st.write(f"本轮扫描币种: {log_info['total']} | 平仓处理: {log_info['closed']}")

st.divider()
st.caption("免责声明：本工具仅供技术交流及模拟测试，数字货币投资具有极高风险，请务必谨慎操作。")
