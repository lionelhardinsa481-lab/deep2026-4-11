import streamlit as st
import ccxt
import pandas as pd
import numpy as np
import requests
from datetime import datetime
import plotly.graph_objects as go

# ================= 1. 核心配置 =================
# 建议直接修改这里的 Token，或者在侧边栏输入
DEFAULT_TOKEN = "https://oapi.dingtalk.com/robot/send?access_token=4037d68aeb929fa3791713dc4b947565a938776fb2edca1c8040faa144b4e216"
START_CASH = 1000.0   
TRADE_RISK = 0.25      
SCAN_COUNT = 50        

# ================= 2. 极致清晰 UI 指令 =================
st.set_page_config(page_title="黑马猎手 V3.5", layout="wide")

st.markdown("""
<style>
    /* 强制高对比度：白底黑字 */
    .stApp { background-color: #FFFFFF !important; color: #1E293B !important; }
    h1, h2, h3, p, span, label { color: #0F172A !important; font-weight: 600 !important; }
    
    /* 指标卡片 */
    [data-testid="stMetricValue"] { color: #2563EB !important; font-size: 2.5rem !important; font-weight: 800 !important; }
    [data-testid="stMetricLabel"] { color: #475569 !important; font-size: 1.1rem !important; }
    
    /* 侧边栏 */
    section[data-testid="stSidebar"] { background-color: #F1F5F9 !important; border-right: 2px solid #CBD5E1; }
    
    /* 信号灯效果 */
    .status-active { color: #10B981; font-weight: bold; animation: blink 2s infinite; }
    @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.3; } 100% { opacity: 1; } }
</style>
""", unsafe_allow_html=True)

# ================= 3. 账户状态记录 =================
if 'acc' not in st.session_state:
    st.session_state.acc = {
        "cash": START_CASH,
        "pos": [],
        "history": [],
        "curve": [START_CASH],
        "last_update": "尚未开始"
    }

# ================= 4. 功能逻辑 =================
def push_ding(content, token):
    """发送钉钉消息"""
    if not token or "替换" in token:
        return False, "未配置有效的 Token"
    url = f"https://oapi.dingtalk.com/robot/send?access_token={token}"
    try:
        res = requests.post(url, json={"msgtype":"text","text":{"content":f"🚀 猎手提醒：\n{content}"}}, timeout=5)
        data = res.json()
        if data.get("errcode") == 0:
            return True, "发送成功"
        return False, data.get("errmsg")
    except Exception as e:
        return False, str(e)

@st.cache_resource
def get_api():
    return ccxt.okx({"options": {"defaultType": "swap"}, "enableRateLimit": True})

def fetch_top_symbols(api):
    try:
        tickers = api.fetch_tickers()
        df = pd.DataFrame.from_dict(tickers, orient='index')
        df = df[df['symbol'].str.contains(':USDT')]
        return df.sort_values(by='quoteVolume', ascending=False).head(SCAN_COUNT)['symbol'].tolist()
    except: return []

# ================= 5. 核心扫描引擎 =================
def run_engine(token):
    api = get_api()
    acc = st.session_state.acc
    now = datetime.now().strftime("%H:%M:%S")
    acc['last_update'] = now
    
    symbols = fetch_top_symbols(api)
    
    # A. 检查平仓
    still_active = []
    for p in acc['pos']:
        try:
            t = api.fetch_ticker(f"{p['symbol']}/USDT:USDT")
            cur = t['last']
            pnl = (cur - p['entry'])/p['entry'] if p['side']=='多' else (p['entry']-cur)/p['entry']
            
            if cur <= p['sl'] or cur >= p['tp']:
                profit = p['margin'] * pnl
                acc['cash'] += (p['margin'] + profit)
                acc['history'].append({**p, "exit":cur, "pnl":profit, "time_end":now})
                acc['curve'].append(acc['cash'])
                push_ding(f"【平仓成功】\n币种：{p['symbol']}\n盈亏：{profit:.2f} USDT", token)
            else: still_active.append(p)
        except: still_active.append(p)
    acc['pos'] = still_active

    # B. 入场扫描 (低门槛策略)
    radar_logs = []
    for sym in symbols:
        s_name = sym.split('/')[0]
        if any(x['symbol'] == s_name for x in acc['pos']): continue
        
        try:
            bars = api.fetch_ohlcv(sym, timeframe='15m', limit=20)
            df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
            last = df.iloc[-1]
            
            # 策略：价格在5周期线上 & 成交量比平时多20%
            ma5 = df['c'].rolling(5).mean().iloc[-1]
            v_avg = df['v'].rolling(10).mean().iloc[-1]
            
            if last['c'] > ma5 and last['v'] > v_avg * 1.2:
                margin = acc['cash'] * TRADE_RISK
                if acc['cash'] < 10: continue
                
                entry = last['c']
                acc['cash'] -= margin
                acc['pos'].append({
                    "symbol": s_name, "side": "多", "entry": entry,
                    "sl": entry * 0.96, "tp": entry * 1.08, "margin": margin, "time": now
                })
                push_ding(f"【入场信号】\n币种：{s_name}\n价格：{entry}", token)
                radar_logs.append({"币种": s_name, "结果": "✅ 已入场"})
            else:
                radar_logs.append({"币种": s_name, "结果": "⏳ 观察"})
        except: continue
    return radar_logs

# ================= 6. 界面展示 =================
st.markdown(f'# 🦅 CRYPTO 猎手 Pro <span class="status-active">● 自动扫描中</span>', unsafe_allow_html=True)

# --- 侧边栏 ---
with st.sidebar:
    st.header("🛠️ 猎手配置")
    token = st.text_input("钉钉 Token", value=DEFAULT_TOKEN, type="password")
    
    # 重新加入的测试按钮
    st.subheader("🧪 联调工具")
    if st.button("发送测试提醒", type="secondary"):
        with st.spinner("发送中..."):
            ok, msg = push_ding("这是一条测试消息，看到说明钉钉配置成功！", token)
            if ok: st.success("✅ 推送成功，请检查钉钉群")
            else: st.error(f"❌ 失败: {msg}")
    
    st.divider()
    if st.button("🚀 手动刷新扫描", type="primary"):
        st.rerun()
    if st.button("🧹 重置所有数据"):
        st.session_state.acc = {"cash": START_CASH, "pos": [], "history": [], "curve": [START_CASH], "last_update": "从未"}
        st.rerun()

# --- 主看板 ---
acc = st.session_state.acc
radar_results = run_engine(token)

equity = acc['cash'] + sum(p['margin'] for p in acc['pos'])
c1, c2, c3, c4 = st.columns(4)
c1.metric("账户总资产", f"${equity:.2f}")
c2.metric("可用 USDT", f"${acc['cash']:.2f}")
c3.metric("活跃持仓", f"{len(acc['pos'])} 单")
c4.metric("最后更新", acc['last_update'])

t1, t2, t3 = st.tabs(["🎯 实时监控雷达", "💼 猎物仓位", "📜 历史对账"])

with t1:
    st.subheader("🔥 市场动向报告 (Top 15)")
    if radar_results:
        st.table(pd.DataFrame(radar_results).head(15))
    
    # 资金曲线
    fig = go.Figure(data=go.Scatter(y=acc['curve'], mode='lines+markers', line=dict(color='#2563EB', width=4)))
    fig.update_layout(title="收益增长轨迹", paper_bgcolor="white", height=300)
    st.plotly_chart(fig, use_container_width=True)

with t2:
    if acc['pos']:
        st.dataframe(pd.DataFrame(acc['pos']), use_container_width=True)
    else:
        st.info("正在寻找符合起飞条件的币种...")

with t3:
    if acc['history']:
        st.dataframe(pd.DataFrame(acc['history']).sort_index(ascending=False), use_container_width=True)
    else:
        st.write("暂无成交历史。")

st.caption("注：请确保开启了页面的自动刷新插件。系统当前每分钟全市场扫描一次。")
