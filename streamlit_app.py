import streamlit as st
import ccxt
import pandas as pd
import numpy as np
import requests
from datetime import datetime
import plotly.graph_objects as go

# ================= 1. 核心配置区 =================
# 建议在这里直接修改你的钉钉 Webhook
DING_WEBHOOK = "https://oapi.dingtalk.com/robot/send?access_token=4037d68aeb929fa3791713dc4b947565a938776fb2edca1c8040faa144b4e216"
START_CASH = 1000.0
TRADE_RISK = 0.2  # 单笔占用 20% 资金

# 监控名单（增加了波动较大的热门币种）
SYMBOLS = [
    "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "ORDI/USDT:USDT",
    "PEPE/USDT:USDT", "SUI/USDT:USDT", "WIF/USDT:USDT", "FET/USDT:USDT",
    "TIA/USDT:USDT", "OP/USDT:USDT", "ARB/USDT:USDT", "APT/USDT:USDT"
]

# ================= 2. 页面与样式 =================
st.set_page_config(page_title="Crypto AI Trader", layout="wide")

st.markdown("""
<style>
    .stMetric { background: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
    .status-box { padding: 10px; border-radius: 5px; margin: 5px 0; }
    .buy-signal { background-color: #dcfce7; color: #166534; border-left: 5px solid #22c55e; }
    .no-signal { background-color: #f1f5f9; color: #475569; border-left: 5px solid #cbd5e1; }
</style>
""", unsafe_allow_html=True)

# ================= 3. 状态管理 =================
if 'acc' not in st.session_state:
    st.session_state.acc = {
        "cash": START_CASH,
        "pos": [],      # 持仓: {symbol, side, entry, sl, tp, margin, time}
        "history": [],  # 历史: {symbol, pnl_usd, pnl_pct, reason, time}
        "curve": [START_CASH]
    }

# ================= 4. 工具函数 =================
def push_msg(msg):
    if "替换" in DING_WEBHOOK: return
    try:
        requests.post(DING_WEBHOOK, json={"msgtype":"text","text":{"content":f"🚀 模拟器提醒：\n{msg}"}}, timeout=5)
    except: pass

@st.cache_resource
def get_api():
    # 优先使用 OKX，若环境限制可改用 binance
    return ccxt.okx({"options": {"defaultType": "swap"}, "enableRateLimit": True})

def get_indicators(df):
    """策略指标计算"""
    # 趋势线：EMA20 (更灵敏)
    df['ema20'] = df['c'].ewm(span=20, adjust=False).mean()
    # 波动率：ATR14 (用于止损)
    df['tr'] = np.maximum(df['h']-df['l'], np.maximum(abs(df['h']-df['c'].shift(1)), abs(df['l']-df['c'].shift(1))))
    df['atr'] = df['tr'].rolling(14).mean()
    # 量能：MA20成交量
    df['v_ma'] = df['v'].rolling(20).mean()
    # 动量：RSI
    delta = df['c'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    return df

# ================= 5. 核心交易引擎 =================
def execute_cycle():
    api = get_api()
    acc = st.session_state.acc
    now = datetime.now().strftime("%H:%M:%S")
    
    # --- A. 检查持仓 (平仓逻辑) ---
    still_open = []
    for p in acc['pos']:
        try:
            t = api.fetch_ticker(f"{p['symbol']}/USDT:USDT")
            cur = t['last']
            pnl_p = (cur - p['entry'])/p['entry'] if p['side']=='多' else (p['entry']-cur)/p['entry']
            
            # 止损止盈触发
            is_close = False
            reason = ""
            if cur <= p['sl'] if p['side']=='多' else cur >= p['sl']:
                is_close, reason = True, "🛑 止损平仓"
            elif cur >= p['tp'] if p['side']=='多' else cur <= p['tp']:
                is_close, reason = True, "🎯 止盈平仓"
            
            if is_close:
                profit = p['margin'] * pnl_p
                acc['cash'] += (p['margin'] + profit)
                acc['history'].append({**p, "exit":cur, "pnl_usd":profit, "pnl_pct":pnl_p, "reason":reason, "end_time":now})
                acc['curve'].append(acc['cash'] + sum(x['margin'] for x in still_open))
                push_msg(f"【平仓成功】\n币种：{p['symbol']}\n盈亏：{profit:.2f} USDT ({pnl_p*100:.2f}%)")
            else:
                still_open.append(p)
        except: still_open.append(p)
    acc['pos'] = still_open

    # --- B. 扫描入场 (新策略逻辑) ---
    radar_logs = []
    for sym in SYMBOLS:
        s_name = sym.split('/')[0]
        # 排除已持仓
        if any(p['symbol'] == s_name for p in acc['pos']): continue
        
        try:
            bars = api.fetch_ohlcv(sym, timeframe='15m', limit=50)
            df = get_indicators(pd.DataFrame(bars, columns=['t','o','h','l','c','v']))
            last = df.iloc[-1]
            
            # --- 优化后的宽松策略 ---
            cond_trend = last['c'] > last['ema20']       # 价格在均线上方
            cond_vol = last['v'] > last['v_ma'] * 1.3     # 成交量是均值的1.3倍 (原2.5倍太严)
            cond_rsi = last['rsi'] > 50                  # 强势区域
            
            if cond_trend and cond_vol and cond_rsi:
                # 符合条件，入场
                margin = acc['cash'] * TRADE_RISK
                if acc['cash'] < margin: continue
                
                entry_p = last['c']
                sl = entry_p - (2 * last['atr']) # 2倍ATR止损
                tp = entry_p + (4 * last['atr']) # 4倍ATR止盈
                
                acc['cash'] -= margin
                acc['pos'].append({
                    "symbol": s_name, "side": "多", "entry": entry_p, 
                    "sl": sl, "tp": tp, "margin": margin, "time": now
                })
                push_msg(f"【入场提醒】\n币种：{s_name}\n价格：{entry_p}\n止损：{sl:.4f}")
                radar_logs.append({"币种": s_name, "状态": "🚀 已买入", "详情": "三项指标全达标"})
            else:
                # 记录为何不买
                fail_reason = []
                if not cond_trend: fail_reason.append("趋势向下")
                if not cond_vol: fail_reason.append(f"量能不足({last['v']/last['v_ma']:.1f}x)")
                if not cond_rsi: fail_reason.append("RSI偏弱")
                radar_logs.append({"币种": s_name, "状态": "😴 观察中", "详情": " & ".join(fail_reason)})
        except: continue
    
    return radar_logs

# ================= 6. UI 布局 =================
st.title("⚡ Crypto Simulator Pro V3.2")

# 侧边栏
with st.sidebar:
    st.header("🔧 系统设置")
    test_webhook = st.text_input("钉钉 Webhook", value=DING_WEBHOOK, type="password")
    if st.button("🧪 测试推送"):
        res = requests.post(test_webhook, json={"msgtype":"text","text":{"content":"模拟器联调：测试成功！"}})
        st.write(res.json())
    
    st.divider()
    if st.button("🔄 手动强制刷新", type="primary"):
        st.rerun()
    
    if st.button("🗑️ 重置账户历史"):
        st.session_state.acc = {"cash": START_CASH, "pos": [], "history": [], "curve": [START_CASH]}
        st.rerun()

# 核心计算与雷达报告
radar_data = execute_cycle()

# 顶部指标看板
acc = st.session_state.acc
cur_equity = acc['cash'] + sum(p['margin'] for p in acc['pos'])
roi = (cur_equity - START_CASH) / START_CASH * 100

c1, c2, c3, c4 = st.columns(4)
c1.metric("账户总净值", f"${cur_equity:.2f}", delta=f"{roi:.2f}%")
c2.metric("可用余额", f"${acc['cash']:.2f}")
c3.metric("当前持仓", f"{len(acc['pos'])} 单")
c4.metric("已完成交易", f"{len(acc['history'])} 单")

# 标签页
tab1, tab2, tab3 = st.tabs(["🎯 实时诊断雷达", "🏹 仓位管理", "📜 历史对账"])

with tab1:
    st.subheader("策略雷达 (每分钟更新)")
    # 展示为什么没交易
    df_radar = pd.DataFrame(radar_data)
    if not df_radar.empty:
        st.table(df_radar)
    
    # 收益曲线
    fig = go.Figure(data=go.Scatter(y=acc['curve'], mode='lines+markers', line=dict(color='#10b981')))
    fig.update_layout(title="资产增长曲线", height=300)
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    if acc['pos']:
        st.dataframe(pd.DataFrame(acc['pos']), use_container_width=True)
    else:
        st.info("当前无持仓，等待信号中...")

with tab3:
    if acc['history']:
        st.dataframe(pd.DataFrame(acc['history']).sort_index(ascending=False), use_container_width=True)
    else:
        st.write("暂无成交记录")

st.caption(f"最后刷新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
