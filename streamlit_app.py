import streamlit as st
import ccxt
import pandas as pd
import numpy as np
import requests
import time
import os
import json
from datetime import datetime
import plotly.graph_objects as go

# ================= 核心配置区 =================
# 请在此填入你的钉钉 Webhook Token
DEFAULT_WEBHOOK = "https://oapi.dingtalk.com/robot/send?access_token=4037d68aeb929fa3791713dc4b947565a938776fb2edca1c8040faa144b4e216"
STARTING_CAPITAL = 1000.0  
RISK_PER_TRADE = 0.2       
SYMBOLS = [
    "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT", 
    "SUI/USDT:USDT", "DOGE/USDT:USDT", "ORDI/USDT:USDT", "PEPE/USDT:USDT"
]

# ================= 页面初始化 =================
st.set_page_config(page_title="Crypto Simulator Pro v3.1", layout="wide")

# 自定义 CSS 样式
st.markdown("""
<style>
    .stApp { background-color: #f8fafc; }
    .main-header { font-size: 2.5rem; font-weight: 800; color: #1e3a8a; text-align: center; margin-bottom: 20px; }
    .card { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }
    .stButton button { width: 100%; border-radius: 8px; transition: all 0.2s; }
    .stButton button:hover { transform: scale(1.02); }
</style>
""", unsafe_allow_html=True)

# 模拟账户持久化
if 'account' not in st.session_state:
    st.session_state.account = {
        "balance": STARTING_CAPITAL,
        "positions": [],
        "history": [],
        "equity_curve": [STARTING_CAPITAL]
    }

# ================= 钉钉推送与测试工具 =================
def ding_push(content, webhook_url=DEFAULT_WEBHOOK):
    """发送钉钉通知并返回结果状态"""
    if "替换" in webhook_url or not webhook_url:
        return False, "未配置有效的 Webhook 地址"
    
    data = {
        "msgtype": "text",
        "text": {"content": f"🤖 模拟器实战提醒：\n{content}"}
    }
    try:
        response = requests.post(webhook_url, json=data, timeout=5)
        res_json = response.json()
        if res_json.get("errcode") == 0:
            return True, "推送成功"
        else:
            return False, f"钉钉返回错误: {res_json.get('errmsg')}"
    except Exception as e:
        return False, f"网络请求失败: {str(e)}"

# ================= 核心计算引擎 =================
@st.cache_resource
def get_ex():
    return ccxt.okx({"options": {"defaultType": "swap"}, "enableRateLimit": True})

def calc_indicators(df):
    df['ema50'] = df['c'].ewm(span=50).mean()
    df['ema200'] = df['c'].ewm(span=200).mean()
    df['tr'] = np.maximum(df['h']-df['l'], np.maximum(abs(df['h']-df['c'].shift(1)), abs(df['l']-df['c'].shift(1))))
    df['atr'] = df['tr'].rolling(14).mean()
    df['vol_ma'] = df['v'].rolling(20).mean()
    return df

def run_engine():
    ex = get_ex()
    acc = st.session_state.account
    now = datetime.now().strftime("%H:%M:%S")
    
    # 1. 自动平仓检查
    active = []
    for pos in acc['positions']:
        try:
            ticker = ex.fetch_ticker(f"{pos['symbol']}/USDT:USDT")
            curr_p = ticker['last']
            pnl_pct = (curr_p - pos['entry']) / pos['entry'] if pos['side'] == '多' else (pos['entry'] - curr_p) / pos['entry']
            
            exit_flag, reason = False, ""
            if curr_p <= pos['sl'] if pos['side'] == '多' else curr_p >= pos['sl']:
                exit_flag, reason = True, "🛑 止损平仓"
            elif curr_p >= pos['tp'] if pos['side'] == '多' else curr_p <= pos['tp']:
                exit_flag, reason = True, "🎯 止盈平仓"
            
            if exit_flag:
                profit = pos['margin'] * pnl_pct
                acc['balance'] += (pos['margin'] + profit)
                pos.update({"exit": curr_p, "pnl_usd": profit, "pnl_pct": pnl_pct, "reason": reason, "close_time": now})
                acc['history'].append(pos)
                acc['equity_curve'].append(acc['balance'])
                ding_push(f"【平仓成功】\n币种：{pos['symbol']}\n结果：{reason}\n盈亏：{profit:.2f} USDT")
            else:
                active.append(pos)
        except: active.append(pos)
    acc['positions'] = active

    # 2. 自动入场扫描
    for sym in SYMBOLS:
        sym_name = sym.split('/')[0]
        if any(p['symbol'] == sym_name for p in acc['positions']): continue
        try:
            ohlcv = ex.fetch_ohlcv(sym, timeframe='15m', limit=100)
            df = calc_indicators(pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v']))
            last = df.iloc[-1]
            
            # 策略条件：EMA多头趋势 + 成交量爆发
            if last['c'] > last['ema50'] and last['v'] > last['vol_ma'] * 2.5:
                entry = last['c']
                sl = entry - (1.5 * last['atr'])
                tp = entry + (3.0 * last['atr'])
                margin = acc['balance'] * RISK_PER_TRADE
                
                acc['balance'] -= margin
                acc['positions'].append({"symbol": sym_name, "side": "多", "entry": entry, "margin": margin, "sl": sl, "tp": tp, "time": now})
                ding_push(f"【入场提醒】\n币种：{sym_name}\n价格：{entry}\n止损位：{sl:.4f}")
        except: continue

# ================= UI 界面 =================
st.markdown('<div class="main-header">⚡ CRYPTO SIMULATOR PRO</div>', unsafe_allow_html=True)

# 侧边栏：配置与测试工具
with st.sidebar:
    st.header("⚙️ 系统配置")
    webhook_input = st.text_input("钉钉 Webhook", value=DEFAULT_WEBHOOK, type="password")
    
    st.subheader("🧪 联调测试")
    if st.button("发送测试提醒", help="点击向钉钉发送一条测试消息"):
        with st.spinner("正在通信..."):
            success, msg = ding_push("这是一条来自模拟器的连通性测试消息。如果你看到这条信息，说明配置正确！", webhook_url=webhook_input)
            if success:
                st.success("✅ 推送成功！请检查钉钉群。")
            else:
                st.error(f"❌ {msg}")

    st.divider()
    if st.button("🚀 立即刷新行情", type="primary"):
        run_engine()
    
    if st.button("♻️ 重置模拟账户"):
        st.session_state.account = {"balance": STARTING_CAPITAL, "positions": [], "history": [], "equity_curve": [STARTING_CAPITAL]}
        st.rerun()

# 主看板
acc = st.session_state.account
equity = acc['balance'] + sum(p['margin'] for p in acc['positions'])
roi = (equity - STARTING_CAPITAL) / STARTING_CAPITAL * 100

c1, c2, c3 = st.columns(3)
with c1:
    st.metric("账户净值 (Equity)", f"${equity:.2f}", delta=f"{roi:.2f}%")
with c2:
    st.metric("可用资金", f"${acc['balance']:.2f}")
with c3:
    st.metric("总交易单数", len(acc['history']))

# 标签页展示
tab1, tab2, tab3 = st.tabs(["📈 收益曲线", "🏹 当前持仓", "📜 历史记录"])

with tab1:
    fig = go.Figure(data=go.Scatter(y=acc['equity_curve'], mode='lines+markers', line=dict(color='#2563eb', width=3)))
    fig.update_layout(title="资产增长轨迹 (USDT)", height=350, margin=dict(l=20, r=20, t=50, b=20))
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    if not acc['positions']:
        st.info("监控中... 暂无入场信号。")
    else:
        st.dataframe(pd.DataFrame(acc['positions']), use_container_width=True)

with tab3:
    if not acc['history']:
        st.write("暂无历史成交记录。")
    else:
        st.dataframe(pd.DataFrame(acc['history']).sort_index(ascending=False), use_container_width=True)

st.caption("注：本模拟器基于 15m K线进行趋势追踪，数据实时取自 OKX。")
