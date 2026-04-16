import streamlit as st
import ccxt
import pandas as pd
import numpy as np
import requests
from datetime import datetime
import plotly.graph_objects as go

# ================= 1. 核心参数 (在此配置) =================
# 钉钉 Token 请务必填在这里
DING_TOKEN = "https://oapi.dingtalk.com/robot/send?access_token=4037d68aeb929fa3791713dc4b947565a938776fb2edca1c8040faa144b4e216"
DING_WEBHOOK = f"https://oapi.dingtalk.com/robot/send?access_token={DING_TOKEN}"

START_CASH = 1000.0   # 初始本金
TRADE_RISK = 0.25      # 单笔仓位 (25%)
SCAN_COUNT = 50        # 全市场扫描前50名成交量的币

# ================= 2. 极致清晰 UI 样式 =================
st.set_page_config(page_title="黑马猎手 V3.4", layout="wide")

st.markdown("""
<style>
    /* 全局背景和文字颜色强制清晰 */
    .stApp { background-color: #FFFFFF !important; color: #1E293B !important; }
    h1, h2, h3 { color: #0F172A !important; font-weight: 800 !important; }
    
    /* 指标卡片美化 */
    [data-testid="stMetricValue"] { color: #2563EB !important; font-size: 2.2rem !important; font-weight: 700 !important; }
    [data-testid="stMetricLabel"] { color: #64748B !important; font-size: 1rem !important; }
    
    /* 表格清晰度 */
    .styled-table { width: 100%; border-collapse: collapse; font-size: 1rem; }
    
    /* 侧边栏样式 */
    section[data-testid="stSidebar"] { background-color: #F8FAFC !important; border-right: 1px solid #E2E8F0; }
    
    /* 信号灯 */
    .heartbeat { color: #10B981; font-weight: bold; animation: blinker 1.5s linear infinite; }
    @keyframes blinker { 50% { opacity: 0; } }
</style>
""", unsafe_allow_html=True)

# ================= 3. 状态与资产管理 =================
if 'acc' not in st.session_state:
    st.session_state.acc = {
        "cash": START_CASH,
        "pos": [],      # {symbol, side, entry, sl, tp, margin, time}
        "history": [],  # {symbol, pnl_usd, pnl_pct, reason, time}
        "curve": [START_CASH],
        "last_scan": "从未"
    }

# ================= 4. 核心功能函数 =================
@st.cache_resource
def get_api():
    # 自动选择最稳的 OKX 接口
    return ccxt.okx({"options": {"defaultType": "swap"}, "enableRateLimit": True})

def push_ding(content):
    if "替换" in DING_TOKEN or not DING_TOKEN: return
    try:
        requests.post(DING_WEBHOOK, json={"msgtype":"text","text":{"content":f"🔔 猎手指令：\n{content}"}}, timeout=5)
    except: pass

def get_market_data(api):
    """抓取全市场成交额前 N 的活跃币种"""
    try:
        tickers = api.fetch_tickers()
        df = pd.DataFrame.from_dict(tickers, orient='index')
        # 仅限 USDT 永续合约
        df = df[df['symbol'].str.contains(':USDT')]
        # 按 24h 成交额排序
        top_list = df.sort_values(by='quoteVolume', ascending=False).head(SCAN_COUNT)
        return top_list['symbol'].tolist()
    except: return []

# ================= 5. 交易策略逻辑 (大幅降压版) =================
def run_strategy():
    api = get_api()
    acc = st.session_state.acc
    now = datetime.now().strftime("%H:%M:%S")
    acc['last_scan'] = now
    
    # 获取最火爆的市场名单
    symbols = get_market_data(api)
    
    # --- A. 自动持仓管理 ---
    active_pos = []
    for p in acc['pos']:
        try:
            t = api.fetch_ticker(f"{p['symbol']}/USDT:USDT")
            cur = t['last']
            pnl_p = (cur - p['entry'])/p['entry'] if p['side']=='多' else (p['entry']-cur)/p['entry']
            
            # 止损止盈
            is_exit = False
            reason = ""
            if cur <= p['sl'] if p['side']=='多' else cur >= p['sl']:
                is_exit, reason = True, "🛑 止损退出"
            elif cur >= p['tp'] if p['side']=='多' else cur <= p['tp']:
                is_exit, reason = True, "🎯 止盈退出"
            
            if is_exit:
                profit = p['margin'] * pnl_p
                acc['cash'] += (p['margin'] + profit)
                acc['history'].append({**p, "exit":cur, "pnl_usd":profit, "pnl_pct":pnl_p, "reason":reason, "end_time":now})
                acc['curve'].append(acc['cash'])
                push_ding(f"【交易结束】\n币种：{p['symbol']}\n净盈亏：{profit:.2f} USDT")
            else:
                active_pos.append(p)
        except: active_pos.append(p)
    acc['pos'] = active_pos

    # --- B. 极速黑马捕捉 ---
    scan_logs = []
    for sym in symbols:
        s_name = sym.split('/')[0]
        if any(x['symbol'] == s_name for x in acc['pos']): continue
        
        try:
            # 缩短 K 线长度，只看最近趋势
            bars = api.fetch_ohlcv(sym, timeframe='15m', limit=30)
            df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
            
            # --- 核心降压策略 ---
            # 1. 动量：当前价格比上一根高 (代表在涨)
            # 2. 趋势：价格在短期均线 EMA10 之上
            # 3. 量能：成交量是 15 周期均值的 1.1 倍 (微幅放量即可)
            ema10 = df['c'].ewm(span=10).mean().iloc[-1]
            vol_ma = df['v'].rolling(15).mean().iloc[-1]
            last = df.iloc[-1]
            
            cond_trend = last['c'] > ema10
            cond_vol = last['v'] > vol_ma * 1.1
            cond_surge = last['c'] > df['c'].iloc[-2] # 正在向上冲
            
            if cond_trend and cond_vol and cond_surge:
                # 进场
                margin = acc['cash'] * TRADE_RISK
                if acc['cash'] < 10: continue
                
                # 动态计算止盈止损 (基于价格 3% 和 6%)
                entry = last['c']
                sl = entry * 0.97
                tp = entry * 1.06
                
                acc['cash'] -= margin
                acc['pos'].append({
                    "symbol": s_name, "side": "多", "entry": entry,
                    "sl": sl, "tp": tp, "margin": margin, "time": now
                })
                push_ding(f"🚀 捕获黑马入场！\n币种：{s_name}\n价格：{entry}\n目标：{tp:.4f}")
                scan_logs.append({"币种": s_name, "结果": "✅ 触发入场"})
            else:
                scan_logs.append({"币种": s_name, "结果": "⏳ 观察中"})
        except: continue
    return scan_logs

# ================= 6. 界面渲染 =================
st.markdown(f'# 🦅 CRYPTO 猎手 Pro <span class="heartbeat">● 系统已就绪</span>', unsafe_allow_html=True)

# 顶部数据看板
acc = st.session_state.acc
equity = acc['cash'] + sum(p['margin'] for p in acc['pos'])
c1, c2, c3, c4 = st.columns(4)
c1.metric("账户净资产", f"${equity:.2f} USDT")
c2.metric("可用资金", f"${acc['cash']:.2f}")
c3.metric("当前仓位", f"{len(acc['pos'])} 单")
c4.metric("最后扫描", acc['last_scan'])

# 自动运行扫描
radar_results = run_strategy()

# 主界面布局
tab1, tab2, tab3 = st.tabs(["🎯 实时监控雷达", "💼 活跃仓位", "📜 成交历史"])

with tab1:
    st.subheader("🔥 市场动向报告 (前15名活跃品种)")
    if radar_results:
        # 只展示前15个最有希望的
        st.table(pd.DataFrame(radar_results).head(15))
    
    # 资金曲线
    if len(acc['curve']) > 1:
        fig = go.Figure(data=go.Scatter(y=acc['curve'], mode='lines+markers', line=dict(color='#2563EB', width=4)))
        fig.update_layout(title="收益增长曲线", plot_bgcolor="white", height=300)
        st.plotly_chart(fig, use_container_width=True)

with tab2:
    if acc['pos']:
        st.write("### 当前正在追踪的猎物")
        st.dataframe(pd.DataFrame(acc['pos']), use_container_width=True)
    else:
        st.info("雷达扫描中，暂时没有符合“起飞”条件的币种入场。")

with tab3:
    if acc['history']:
        st.write("### 狩猎成果")
        st.dataframe(pd.DataFrame(acc['history']).sort_index(ascending=False), use_container_width=True)
    else:
        st.write("暂无历史记录。一旦有平仓，数据会出现在这里。")

# 侧边栏
with st.sidebar:
    st.header("⚙️ 猎手后台")
    st.write("建议使用白天的 Light 模式查看，文字效果最佳。")
    if st.button("🔄 强制重扫市场", type="primary"):
        st.rerun()
    if st.button("🧹 重置所有数据"):
        st.session_state.acc = {"cash": START_CASH, "pos": [], "history": [], "curve": [START_CASH], "last_scan": "从未"}
        st.rerun()
    st.divider()
    st.caption("策略：EMA10 趋势 + 1.1x 放量突破")
