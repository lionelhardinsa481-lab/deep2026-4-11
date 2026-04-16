import streamlit as st
import ccxt
import pandas as pd
import numpy as np
import requests
from datetime import datetime

# ================= 核心配置 =================
# 已经帮你把 Token 填好了，如果你没改动，直接运行
DEFAULT_TOKEN = "4037d68aeb929fa3791713dc4b947565a938776fb2edca1c8040faa144b4e216"
START_CASH = 1000.0   
TRADE_RISK = 0.3      # 提高到 30% 仓位
SCAN_COUNT = 40        

st.set_page_config(page_title="黑马猎手 V3.6 - 调试版", layout="wide")

# ================= 钉钉推送逻辑 (带报错反馈) =================
def push_ding(content, token):
    if not token or len(token) < 10:
        return False, "Token 长度不对，请检查"
    url = f"https://oapi.dingtalk.com/robot/send?access_token={token}"
    # 强制加入关键词“猎手”，请确保你钉钉机器人关键词也包含“猎手”
    data = {
        "msgtype": "text",
        "text": {"content": f"【猎手信号】\n{content}"}
    }
    try:
        res = requests.post(url, json=data, timeout=5)
        res_data = res.json()
        if res_data.get("errcode") == 0:
            return True, "发送成功"
        else:
            return False, f"钉钉拒绝了：{res_data.get('errmsg')} (提示：请检查机器人关键词设置是否包含'猎手')"
    except Exception as e:
        return False, f"网络错误：{str(e)}"

# ================= 核心引擎 =================
@st.cache_resource
def get_api():
    return ccxt.okx({"options": {"defaultType": "swap"}, "enableRateLimit": True})

if 'acc' not in st.session_state:
    st.session_state.acc = {"cash": START_CASH, "pos": [], "history": [], "last_log": "等待扫描..."}

def run_trading_logic(token):
    api = get_api()
    acc = st.session_state.acc
    now = datetime.now().strftime("%H:%M:%S")
    
    try:
        # 1. 拿全市场最火的币
        tickers = api.fetch_tickers()
        df_t = pd.DataFrame.from_dict(tickers, orient='index')
        symbols = df_t[df_t['symbol'].str.contains(':USDT')].sort_values(by='quoteVolume', ascending=False).head(SCAN_COUNT)['symbol'].tolist()
        
        # 2. 检查平仓
        active = []
        for p in acc['pos']:
            t = api.fetch_ticker(f"{p['symbol']}/USDT:USDT")
            cur = t['last']
            if cur <= p['sl'] or cur >= p['tp']:
                pnl = p['margin'] * ((cur - p['entry'])/p['entry'])
                acc['cash'] += (p['margin'] + pnl)
                acc['history'].append({**p, "exit": cur, "pnl": pnl})
                push_ding(f"💰 平仓提醒\n币种：{p['symbol']}\n盈亏：{pnl:.2f} USDT", token)
            else: active.append(p)
        acc['pos'] = active

        # 3. 扫描入场
        for sym in symbols:
            s_name = sym.split('/')[0]
            if any(x['symbol'] == s_name for x in acc['pos']): continue
            
            # 极速策略：只要 15 分钟稍微放量且价格在涨
            bars = api.fetch_ohlcv(sym, timeframe='15m', limit=10)
            df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
            last = df.iloc[-1]
            v_ma = df['v'].mean()
            
            # 条件：当前价高于开盘价 & 成交量大于平均
            if last['c'] > last['o'] and last['v'] > v_ma:
                margin = acc['cash'] * TRADE_RISK
                if acc['cash'] < 10: break
                
                entry = last['c']
                acc['cash'] -= margin
                new_p = {"symbol": s_name, "entry": entry, "sl": entry*0.95, "tp": entry*1.1, "margin": margin, "time": now}
                acc['pos'].append(new_p)
                
                # 发送并记录结果
                ok, msg = push_ding(f"🚀 发现黑马！\n币种：{s_name}\n价格：{entry}", token)
                acc['last_log'] = f"[{now}] 尝试发送 {s_name}: {msg}"
    except Exception as e:
        acc['last_log'] = f"错误：{str(e)}"

# ================= UI 展示 =================
st.title("🦅 黑马猎手 V3.6 - 诊断版")

with st.sidebar:
    st.header("⚙️ 配置")
    token = st.text_input("钉钉 Token", value=DEFAULT_TOKEN)
    
    st.subheader("🧪 联调测试")
    if st.button("点此测试钉钉通知"):
        ok, res = push_ding("这是一条手动测试消息", token)
        if ok: st.success("✅ 钉钉通了！请检查群消息。")
        else: st.error(f"❌ 失败原因：{res}")

    if st.button("🔄 立即刷新行情", type="primary"):
        run_trading_logic(token)
        st.rerun()

# 核心看板
run_trading_logic(token)
acc = st.session_state.acc

c1, c2, c3 = st.columns(3)
c1.metric("总资产", f"${acc['cash'] + sum(p['margin'] for p in acc['pos']):.2f}")
c2.metric("当前持仓", f"{len(acc['pos'])} 单")
c3.metric("日志状态", acc['last_update'] if 'last_update' in acc else "运行中")

st.info(f"📡 最新系统日志：{acc['last_log']}")

# 展示持仓
if acc['pos']:
    st.write("### 🏹 当前持仓")
    st.table(pd.DataFrame(acc['pos']))
else:
    st.write("目前市场太冷清，暂未触发极速信号。")
