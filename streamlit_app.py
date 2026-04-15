import streamlit as st
import ccxt
import pandas as pd
import numpy as np
import requests
from datetime import datetime
import plotly.graph_objects as go

# ================= 1. 核心配置区 =================
DING_WEBHOOK = "https://oapi.dingtalk.com/robot/send?access_token=4037d68aeb929fa3791713dc4b947565a938776fb2edca1c8040faa144b4e216"
START_CASH = 1000.0
TRADE_RISK = 0.2
# 扫描深度：每次从成交额前多少名中抓取黑马
SCAN_DEPTH = 40 

# ================= 2. 页面与样式 =================
st.set_page_config(page_title="Crypto BlackHorse Hunter", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #0f172a; color: #f8fafc; } /* 深色模式更具科技感 */
    .stMetric { background: #1e293b; padding: 15px; border-radius: 10px; border: 1px solid #334155; }
    .buy-signal { background-color: #064e3b; color: #34d399; padding: 5px; border-radius: 4px; }
    .wait-signal { background-color: #1e293b; color: #94a3b8; padding: 5px; border-radius: 4px; }
</style>
""", unsafe_allow_html=True)

# ================= 3. 状态管理 =================
if 'acc' not in st.session_state:
    st.session_state.acc = {
        "cash": START_CASH,
        "pos": [],
        "history": [],
        "curve": [START_CASH]
    }

# ================= 4. 动态币种获取 =================
@st.cache_resource
def get_api():
    return ccxt.okx({"options": {"defaultType": "swap"}, "enableRateLimit": True})

def get_dynamic_symbols(api):
    """从交易所实时获取成交额最大的活跃币种"""
    try:
        tickers = api.fetch_tickers()
        # 过滤掉非 USDT 结算和非永续合约的对
        df_tickers = pd.DataFrame.from_dict(tickers, orient='index')
        df_tickers = df_tickers[df_tickers['symbol'].str.contains(':USDT')]
        
        # 按成交额 (quoteVolume) 排序，取前 SCAN_DEPTH 名
        top_symbols = df_tickers.sort_values(by='quoteVolume', ascending=False).head(SCAN_DEPTH)
        return top_symbols['symbol'].tolist()
    except Exception as e:
        st.error(f"获取动态币种失败: {e}")
        return ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]

def get_indicators(df):
    df['ema20'] = df['c'].ewm(span=20, adjust=False).mean()
    df['tr'] = np.maximum(df['h']-df['l'], np.maximum(abs(df['h']-df['c'].shift(1)), abs(df['l']-df['c'].shift(1))))
    df['atr'] = df['tr'].rolling(14).mean()
    df['v_ma'] = df['v'].rolling(20).mean()
    return df

def push_msg(msg):
    if "替换" in DING_WEBHOOK: return
    try: requests.post(DING_WEBHOOK, json={"msgtype":"text","text":{"content":f"🔥 黑马猎手提醒：\n{msg}"}}, timeout=5)
    except: pass

# ================= 5. 核心交易引擎 =================
def run_hunter_engine():
    api = get_api()
    acc = st.session_state.acc
    now = datetime.now().strftime("%H:%M:%S")
    
    # 获取当前最火爆的币种
    dynamic_list = get_dynamic_symbols(api)
    
    # --- A. 检查平仓 ---
    still_open = []
    for p in acc['pos']:
        try:
            t = api.fetch_ticker(f"{p['symbol']}/USDT:USDT")
            cur = t['last']
            pnl_p = (cur - p['entry'])/p['entry'] if p['side']=='多' else (p['entry']-cur)/p['entry']
            
            is_close, reason = False, ""
            if cur <= p['sl'] if p['side']=='多' else cur >= p['sl']:
                is_close, reason = True, "🛑 自动止损"
            elif cur >= p['tp'] if p['side']=='多' else cur <= p['tp']:
                is_close, reason = True, "🎯 自动止盈"
            
            if is_close:
                profit = p['margin'] * pnl_p
                acc['cash'] += (p['margin'] + profit)
                acc['history'].append({**p, "exit":cur, "pnl_usd":profit, "pnl_pct":pnl_p, "reason":reason, "end_time":now})
                acc['curve'].append(acc['cash'] + sum(x['margin'] for x in still_open))
                push_msg(f"✅ 平仓结算\n币种：{p['symbol']}\n原因：{reason}\n净盈亏：{profit:.2f} USDT")
            else: still_open.append(p)
        except: still_open.append(p)
    acc['pos'] = still_open

    # --- B. 动态扫描入场 ---
    radar_report = []
    for sym in dynamic_list:
        s_name = sym.split('/')[0]
        if any(p['symbol'] == s_name for p in acc['pos']): continue
        
        try:
            bars = api.fetch_ohlcv(sym, timeframe='15m', limit=50)
            df = get_indicators(pd.DataFrame(bars, columns=['t','o','h','l','c','v']))
            last = df.iloc[-1]
            
            # 黑马突破逻辑：
            # 1. 价格站稳 EMA20
            # 2. 当前成交量 > 过去20周期均值 1.5倍 (代表有人抢筹)
            # 3. 价格创 20 周期新高 (确认暴涨趋势)
            is_high = last['c'] >= df['h'].rolling(20).max().iloc[-1]
            cond_vol = last['v'] > last['v_ma'] * 1.5
            cond_trend = last['c'] > last['ema20']
            
            if is_high and cond_vol and cond_trend:
                margin = acc['cash'] * TRADE_RISK
                if acc['cash'] < margin: continue
                
                entry_p = last['c']
                sl = entry_p - (1.5 * last['atr'])
                tp = entry_p + (3.5 * last['atr'])
                
                acc['cash'] -= margin
                acc['pos'].append({"symbol": s_name, "side": "多", "entry": entry_p, "sl": sl, "tp": tp, "margin": margin, "time": now})
                push_msg(f"🚀 捕获到黑马突破！\n币种：{s_name}\n入场价：{entry_p}\n注意：该币种成交额已进入全网前{SCAN_DEPTH}")
                radar_report.append({"币种": s_name, "成交额排名": "Top", "状态": "🚀 捕捉成功"})
            else:
                radar_report.append({"币种": s_name, "成交额排名": "Top", "状态": "😴 震荡中"})
        except: continue
    
    return radar_report

# ================= 6. UI 渲染 =================
st.markdown('<h1 style="text-align: center; color: #60a5fa;">🦅 CRYPTO 黑马动态捕捉器</h1>', unsafe_allow_html=True)

# 侧边栏：配置
with st.sidebar:
    st.header("⚙️ 猎手设置")
    st.info("系统会自动寻找全市场成交额最大的币种进行实时监控。")
    new_webhook = st.text_input("钉钉 Webhook", value=DING_WEBHOOK, type="password")
    
    st.divider()
    if st.button("🔄 立即全市场扫描", type="primary"):
        st.rerun()
    if st.button("🗑️ 清空账户数据"):
        st.session_state.acc = {"cash": START_CASH, "pos": [], "history": [], "curve": [START_CASH]}
        st.rerun()

# 执行引擎
radar_data = run_hunter_engine()

# 数据看板
acc = st.session_state.acc
equity = acc['cash'] + sum(p['margin'] for p in acc['pos'])
c1, c2, c3, c4 = st.columns(4)
c1.metric("当前总资产", f"${equity:.2f}", delta=f"{(equity-START_CASH)/START_CASH*100:.2f}%")
c2.metric("可用 USDT", f"${acc['cash']:.2f}")
c3.metric("活跃单数", len(acc['pos']))
c4.metric("已捕获次数", len(acc['history']))

# 诊断与展示
t1, t2, t3 = st.tabs(["📡 实时动态雷达", "💼 猎物仓位", "📖 狩猎日志"])

with t1:
    st.subheader(f"当前监控中的 Top {SCAN_DEPTH} 成交量黑马")
    if radar_data:
        st.table(pd.DataFrame(radar_data).head(15)) # 仅展示前15个活跃的
    
    fig = go.Figure(data=go.Scatter(y=acc['curve'], mode='lines', line=dict(color='#60a5fa', width=3)))
    fig.update_layout(title="模拟账户资金曲线", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color="white"))
    st.plotly_chart(fig, use_container_width=True)

with t2:
    if acc['pos']:
        st.write(pd.DataFrame(acc['pos']))
    else:
        st.info("暂未发现满足暴涨突破条件的币种。")

with t3:
    if acc['history']:
        st.write(pd.DataFrame(acc['history']).sort_index(ascending=False))
    else:
        st.write("等待第一笔狩猎完成...")

st.caption(f"系统运行中... 扫描时间: {datetime.now().strftime('%H:%M:%S')}")
