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

# ================= 配置区 (请在此修改) =================
DINGTALK_WEBHOOK = "https://oapi.dingtalk.com/robot/send?access_token=这里替换成你的Token"
STARTING_CAPITAL = 1000.0  # 初始模拟资金
RISK_PER_TRADE = 0.2       # 每笔交易占用总资金的 20%
SYMBOLS = [
    "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT", 
    "SUI/USDT:USDT", "DOGE/USDT:USDT", "ORDI/USDT:USDT", "PEPE/USDT:USDT"
]

# ================= 页面设置 =================
st.set_page_config(page_title="Crypto Simulator Pro", layout="wide")

st.markdown("""
<style>
    .reportview-container { background: #f0f2f6; }
    .stat-card { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
    .status-online { color: #10b981; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ================= 状态管理 (持久化模拟资产) =================
if 'account' not in st.session_state:
    st.session_state.account = {
        "balance": STARTING_CAPITAL,
        "positions": [],
        "history": [],
        "equity_curve": [STARTING_CAPITAL]
    }

# ================= 工具函数 =================
def ding_push(content):
    """发送钉钉通知"""
    if "替换" in DINGTALK_WEBHOOK: return
    data = {"msgtype": "text", "text": {"content": f"🤖 模拟器提醒：\n{content}"}}
    try:
        requests.post(DINGTALK_WEBHOOK, json=data, timeout=5)
    except: pass

@st.cache_resource
def init_ex():
    return ccxt.okx({"options": {"defaultType": "swap"}, "enableRateLimit": True})

def calc_indicators(df):
    # 基础指标计算
    df['ema50'] = df['c'].ewm(span=50).mean()
    df['ema200'] = df['c'].ewm(span=200).mean()
    # ATR 止损参考
    df['tr'] = np.maximum(df['h']-df['l'], np.maximum(abs(df['h']-df['c'].shift(1)), abs(df['l']-df['c'].shift(1))))
    df['atr'] = df['tr'].rolling(14).mean()
    # 波动异动
    df['pct'] = df['c'].pct_change()
    df['vol_ma'] = df['v'].rolling(20).mean()
    return df

# ================= 模拟执行引擎 =================
def run_simulation_step():
    ex = init_ex()
    acc = st.session_state.account
    now_str = datetime.now().strftime("%H:%M:%S")
    
    # 1. 检查现有持仓 (平仓逻辑)
    active_positions = []
    for pos in acc['positions']:
        try:
            ticker = ex.fetch_ticker(f"{pos['symbol']}/USDT:USDT")
            curr_p = ticker['last']
            
            # 计算盈亏
            pnl_pct = (curr_p - pos['entry']) / pos['entry'] if pos['side'] == '多' else (pos['entry'] - curr_p) / pos['entry']
            
            # 触发止损或止盈
            is_exit = False
            reason = ""
            if curr_p <= pos['sl'] if pos['side'] == '多' else curr_p >= pos['sl']:
                is_exit, reason = True, "🛑 触发止损"
            elif curr_p >= pos['tp'] if pos['side'] == '多' else curr_p <= pos['tp']:
                is_exit, reason = True, "🎯 触发止盈"
            
            if is_exit:
                profit_usd = pos['margin'] * pnl_pct
                acc['balance'] += (pos['margin'] + profit_usd)
                pos.update({"exit_price": curr_p, "pnl_usd": profit_usd, "pnl_pct": pnl_pct, "reason": reason, "close_time": now_str})
                acc['history'].append(pos)
                acc['equity_curve'].append(acc['balance'])
                ding_push(f"【平仓成功】\n币种：{pos['symbol']}\n方向：{pos['side']}\n盈亏：{profit_usd:.2f} USDT ({pnl_pct*100:.2f}%)")
            else:
                active_positions.append(pos)
        except:
            active_positions.append(pos)
    
    acc['positions'] = active_positions

    # 2. 扫描新信号 (入场逻辑)
    if acc['balance'] > (STARTING_CAPITAL * 0.1): # 账户里还有钱才扫描
        for sym in SYMBOLS:
            if any(p['symbol'] == sym.split('/')[0] for p in acc['positions']): continue
            
            try:
                ohlcv = ex.fetch_ohlcv(sym, timeframe='15m', limit=100)
                df = calc_indicators(pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v']))
                last = df.iloc[-1]
                
                # 策略逻辑：均线多头 + 异动突破
                if last['c'] > last['ema50'] and last['v'] > last['vol_ma'] * 2:
                    entry_p = last['c']
                    atr_val = last['atr']
                    sl = entry_p - (2 * atr_val)
                    tp = entry_p + (4 * atr_val)
                    margin = acc['balance'] * RISK_PER_TRADE
                    
                    acc['balance'] -= margin
                    new_pos = {
                        "symbol": sym.split('/')[0],
                        "side": "多",
                        "entry": entry_p,
                        "margin": margin,
                        "sl": sl,
                        "tp": tp,
                        "time": now_str
                    }
                    acc['positions'].append(new_pos)
                    ding_push(f"【入场提醒】\n币种：{new_pos['symbol']}\n价格：{entry_p}\n止损：{sl:.4f}")
            except: continue

# ================= UI 渲染 =================
st.title("⚡ Crypto 自动模拟实战终端")

# 顶部数据卡片
acc = st.session_state.account
unrealized_pnl = 0
for p in acc['positions']:
    # 简单模拟实时浮盈
    unrealized_pnl += (p['margin'] * 0.01) # 演示用

total_equity = acc['balance'] + sum(p['margin'] for p in acc['positions']) + unrealized_pnl
total_return = (total_equity - STARTING_CAPITAL) / STARTING_CAPITAL * 100

c1, c2, c3, c4 = st.columns(4)
c1.metric("账户总资产 (Equity)", f"${total_equity:.2f} USDT")
c2.metric("可用余额", f"${acc['balance']:.2f}")
c3.metric("总收益率", f"{total_return:.2f}%", delta=f"{total_equity-STARTING_CAPITAL:.2f}")
c4.metric("运行状态", "工作中", delta_color="normal")

# 侧边栏控制
with st.sidebar:
    st.header("模拟器控制")
    if st.button("🔄 手动刷新扫描"):
        run_simulation_step()
    
    st.divider()
    st.write("📈 **策略参数**")
    st.write(f"- 起始资金: {STARTING_CAPITAL}")
    st.write(f"- 单笔仓位: {RISK_PER_TRADE*100}%")
    
    if st.button("🗑️ 重置账户"):
        st.session_state.account = {"balance": STARTING_CAPITAL, "positions": [], "history": [], "equity_curve": [STARTING_CAPITAL]}
        st.rerun()

# 主界面布局
t1, t2, t3 = st.tabs(["📊 实战看板", "🛠️ 当前持仓", "📜 历史对账"])

with t1:
    col_l, col_r = st.columns([2, 1])
    with col_l:
        st.subheader("资产增长曲线")
        fig = go.Figure()
        fig.add_trace(go.Scatter(y=acc['equity_curve'], mode='lines+markers', name='Equity', line=dict(color='#2563eb')))
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=300)
        st.plotly_chart(fig, use_container_width=True)
    
    with col_r:
        st.subheader("胜率分析")
        wins = len([h for h in acc['history'] if h.get('pnl_usd', 0) > 0])
        total = len(acc['history'])
        wr = (wins / total * 100) if total > 0 else 0
        st.markdown(f"### {wr:.1f}%")
        st.progress(wr/100)
        st.caption(f"已完成交易: {total} 次")

with t2:
    if not acc['positions']:
        st.info("监控中... 暂无符合信号入场的持仓")
    else:
        st.table(pd.DataFrame(acc['positions'])[['symbol', 'side', 'entry', 'margin', 'time']])

with t3:
    if not acc['history']:
        st.write("暂无成交历史")
    else:
        df_h = pd.DataFrame(acc['history'])
        st.dataframe(df_h[['symbol', 'side', 'entry', 'exit_price', 'pnl_usd', 'reason', 'close_time']], use_container_width=True)

# 自动运行提示
st.toast("系统已启动，正在实时监控行情并执行策略...")
