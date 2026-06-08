import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import io
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="주간 투자 추천 & 포트폴리오 매니저", layout="wide")

HDR = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
G_URL = "https://docs.google.com/spreadsheets/d/1pMpXBZh3sIDE79e7vNmUgdVEU8f-qbywYy7biuWoUNM/edit?usp=sharing"
W_URL = "https://script.google.com/macros/s/AKfycbw0EcgCR_myrhrtZbtDn1d3Jq11p__mqQCOnoqZ3fO6-G5juC-x3XdWuyDtdWULfwJ6/exec"

def load_portfolio_from_sheets(url, sheet_name="보유현황"):
    try:
        if "/edit" in url:
            base = url.split('/edit')[0]
            csv_url = f"{base}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
        else:
            csv_url = url
        ts = int(datetime.now().timestamp())
        res = requests.get(f"{csv_url}&t={ts}", headers=HDR, timeout=5)
        if res.status_code == 200:
            df = pd.read_csv(io.StringIO(res.text))
            if not df.empty:
                if '종목명' in df.columns:
                    df = df.dropna(subset=['종목명'])
                    df.columns = [c.strip() for c in df.columns]
            return df
        return pd.DataFrame()
    except:
        return pd.DataFrame()

@st.cache_data(ttl=600)
def fetch_market_data(sosok):
    try:
        res_v = requests.get(f"https://finance.naver.com/sise/sise_quant.naver?sosok={sosok}", headers=HDR, timeout=5)
        soup_v = BeautifulSoup(res_v.text, 'html.parser')
        t_v = soup_v.find('table', {'class': 'type_2'})
        stk_v = []
        if t_v:
            for r in t_v.find_all('tr'):
                a = r.find('a', {'class': 'tltle'})
                if a:
                    stk_v.append({'종목명': a.get_text().strip(), '코드': a['href'].split('=')[-1]})
        
        df_v = pd.read_html(io.StringIO(str(t_v)))[0].dropna(subset=['종목명']) if t_v else pd.DataFrame()
        target_col = '종목명'
        df_v = df_v.query(f"{target_col} != '종목명'").head(len(stk_v)).copy()
        df_v['코드'] = [s['코드'] for s in stk_v[:len(df_v)]]
        df_v['거래대금(억)'] = (pd.to_numeric(df_v['거래대금'], errors='coerce').fillna(0) / 1000).round(1)
        
        res_g = requests.get(f"https://finance.naver.com/sise/sise_rise.naver?sosok={sosok}", headers=HDR, timeout=5)
        soup_g = BeautifulSoup(res_g.text, 'html.parser')
        t_g = soup_g.find('table', {'class': 'type_2'})
        stk_g = []
        if t_g:
            for r in t_g.find_all('tr'):
                a = r.find('a', {'class': 'tltle'})
                if a:
                    stk_g.append({'종목명': a.get_text().strip(), '코드': a['href'].split('=')[-1]})
                    
        df_g = pd.read_html(io.StringIO(str(t_g)))[0].dropna(subset=['종목명']) if t_g else pd.DataFrame()
        df_g = df_g.query(f"{target_col} != '종목명'").head(len(stk_g)).copy()
        df_g['코드'] = [s['코드'] for s in stk_g[:len(df_g)]]
        df_g['raw_vol'] = pd.to_numeric(df_g['거래량'], errors='coerce').fillna(0)
        df_g['거래량(만)'] = (df_g['raw_vol'] / 10000).round(1)
        
        return df_v.head(15), df_g.head(15)
    except:
        return pd.DataFrame(columns=['종목명', '등락률', '거래대금(억)', '코드']), pd.DataFrame(columns=['종목명', '등락률', '거래량(만)', '코드'])

@st.cache_data(ttl=3600)
def get_all_stock_codes():
    m = {}
    for s in [0, 1]:
        try:
            base_api = "https://finance.naver.com"
            sub_api = f"/sise/sise_quant.naver?sosok={s}"
            res = requests.get(base_api + sub_api, headers=HDR, timeout=5)
            soup = BeautifulSoup(res.text, 'html.parser')
            anchors = soup.find_all('a', {'class': 'tltle'})
            for a in anchors:
                name_key = a.get_text().strip()
                code_val = a['href'].split('=')[-1]
                m[name_key] = code_val
        except:
            pass
    return m

def get_current_price(code, market):
    try:
        suffix = ".KQ"
        if "코스피" in str(market):
            suffix = ".KS"
        full_ticker = f"{code}{suffix}"
        ticker_obj = yf.Ticker(full_ticker)
        df = ticker_obj.history(period="1d")
        if not df.empty:
            last_close = df['Close'].iloc[-1]
            return int(last_close)
    except:
        pass
    return None

def get_stock_chart(code, name, period_choice, market_type):
    try:
        p_val = "3mo"
        i_val = "1d"
        if period_choice == "1년 (주봉)":
            p_val = "1y"
            i_val = "1wk"
        elif period_choice == "3년 (주봉)":
            p_val = "3y"
            i_val = "1wk"
            
        suffix = ".KQ"
        if "코스피" in str(market_type):
            suffix = ".KS"
            
        df = yf.Ticker(f"{code}{suffix}").history(period=p_val, interval=i_val)
        if df.empty:
            return st.warning("⚠️ 차트 데이터 없음")
        
        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA60'] = df['Close'].rolling(60).mean()
        
        fig = make_subplots(
            rows=2, 
            cols=1, 
            shared_xaxes=True, 
            vertical_spacing=0.05, 
            row_width=[0.25, 0.75]
        )
        
        c_trace = go.Candlestick(
            x=df.index, 
            open=df['Open'], 
            high=df['High'], 
            low=df['Low'], 
            close=df['Close'], 
            name="주가", 
            increasing_line_color='#ef4444', 
            decreasing_line_color='#3b82f6'
        )
        fig.add_trace(c_trace, row=1, col=1)
        
        ma5_trace = go.Scatter(
            x=df.index, 
            y=df['MA5'], 
            line=dict(color='#ff9800', width=1.5), 
            name='5선'
        )
        fig.add_trace(ma5_trace, row=1, col=1)
        
        ma20_trace = go.Scatter(
            x=df.index, 
            y=df['MA20'], 
            line=dict(color='#4caf50', width=1.5), 
            name='20선'
        )
        fig.add_trace(ma20_trace, row=1, col=1)
        
        ma60_trace = go.Scatter(
            x=df.index, 
            y=df['MA60'], 
            line=dict(color='#9c27b0', width=1.5), 
            name='60선'
        )
        fig.add_trace(ma60_trace, row=1, col=1)
        
        m_colors = []
        for _, r in df.iterrows():
            if r['Close'] >= r['Open']:
                m_colors.append('#ef4444')
            else:
                m_colors.append('#3b82f6')
                
        v_trace = go.Bar(
            x=df.index, 
            y=df['Volume'], 
            name="거래량", 
            marker_color=m_colors
        )
        fig.add_trace(v_trace, row=2, col=1)
        
        fig.update_layout(
            xaxis_rangeslider_visible=False,
            margin=dict(l=10, r=10, t=10, b=10),
            height=400,
            template="plotly_white"
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"차트 에러: {e}")

def parse_rate(val):
    try:
        return float(str(val).replace('%','').replace('+','').strip())
    except:
        return 0.0

st.title("📈 주간 투자 추천 & 스마트 포트폴리오 대시보드")
st.caption(f"📅 기준일: {datetime.now().strftime('%Y-%m-%d')} | 수급 및 모멘텀 실시간 추적")

sheet_df = load_portfolio_from_sheets(G_URL)
code_master = get_all_stock_codes()

st.markdown("---")
tab_buy, tab_sell = st.tabs(["➕ 새 추천 주식 매수 추가", "➖ 주식 매도 기록"])

with tab_buy:
    with st.form("add_form", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        n = c1.text_input("종목명", placeholder="예: 삼성전자")
        p = c2.number_input("매수가(원)", min_value=0, step=10)
        q = c3.number_input("보유주수(주)", min_value=1, step=1, value=1)
        m = c4.selectbox("시장", ["코스피", "코스닥"])
        if st.form_submit_button("💼 포트폴리오 추가") and n.strip() and p > 0:
            try:
                requests.post(W_URL, json={"action": "buy", "stock_name": n.strip(), "buy_price": int(p), "qty": int(q), "market": m}, timeout=10)
                st.success("🎉 추가 완료!"); st.cache_data.clear(); st.rerun()
            except Exception as e: st.error(f"오류: {e}")

with tab_sell:
