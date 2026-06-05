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

st.markdown("""
<style>
    .up-color { color: #ef4444; font-weight: bold; } .down-color { color: #3b82f6; font-weight: bold; } 
    .flat-color { color: #6b7280; } .recommend-row { background-color: #fef08a !important; font-weight: bold; }
    .super-recommend-row { background-color: #fee2e2 !important; border: 2px solid #ef4444 !important; font-weight: bold; color: #b91c1c !important; }
    .portfolio-danger { background-color: #fee2e2 !important; color: #b91c1c !important; font-weight: bold; } 
    .portfolio-success { background-color: #dcfce7 !important; color: #15803d !important; font-weight: bold; } 
</style>
""", unsafe_allow_html=True)

def load_portfolio_from_sheets(url, sheet_name="보유현황"):
    try:
        csv_url = f"{url.split('/edit')[0]}/gviz/tq?tqx=out:csv&sheet={sheet_name}" if "/edit" in url else url
        res = requests.get(f"{csv_url}&t={int(datetime.now().timestamp())}", headers=HDR, timeout=5)
        if res.status_code == 200:
            df = pd.read_csv(io.StringIO(res.text))
            if not df.empty and '종목명' in df.columns:
                df = df.dropna(subset=['종목명'])
                df.columns = [c.strip() for c in df.columns]
            return df
        return pd.DataFrame()
    except: return pd.DataFrame()

@st.cache_data(ttl=600)
def fetch_market_data(sosok):
    try:
        # 1. 거래대금 상위
        res_v = requests.get(f"https://finance.naver.com/sise/sise_quant.naver?sosok={sosok}", headers=HDR, timeout=5)
        soup_v = BeautifulSoup(res_v.text, 'html.parser')
        t_v = soup_v.find('table', {'class': 'type_2'})
        stk_v = [{'종목명': r.find('a', {'class': 'tltle'}).get_text().strip(), '코드': r.find('a', {'class': 'tltle'})['href'].split('=')[-1]} for r in t_v.find_all('tr') if r.find('a', {'class': 'tltle'})] if t_v else []
        df_v = pd.read_html(io.StringIO(str(t_v)))[0].dropna(subset=['종목명']) if t_v else pd.DataFrame()
        df_v = df_v[df_v['종목명'] != '종목명'].head(len(stk_v)).copy()
        df_v['코드'] = [s['코드'] for s in stk_v[:len(df_v)]]
        df_v['거래대금(억)'] = (pd.to_numeric(df_v['거래대금'], errors='coerce').fillna(0) / 1000).round(1)
        
        # 2. 상승률 상위
        res_g = requests.get(f"https://finance.naver.com/sise/sise_rise.naver?sosok={sosok}", headers=HDR, timeout=5)
        soup_g = BeautifulSoup(res_g.text, 'html.parser')
        t_g = soup_g.find('table', {'class': 'type_2'})
        stk_g = [{'종목명': r.find('a', {'class': 'tltle'}).get_text().strip(), '코드': r.find('a', {'class': 'tltle'})['href'].split('=')[-1]} for r in t_g.find_all('tr') if r.find('a', {'class': 'tltle'})] if t_g else []
        df_g = pd.read_html(io.StringIO(str(t_g)))[0].dropna(subset=['종목명']) if t_g else pd.DataFrame()
        df_g = df_g[df_g['종목명'] != '종목명'].head(len(stk_g)).copy()
        df_g['코드'] = [s['코드'] for s in stk_g[:len(df_g)]]
        df_g['raw_vol'] = pd.to_numeric(df_g['거래량'], errors='coerce').fillna(0)
        df_g['거래량(만)'] = (df_g['raw_vol'] / 10000).round(1)
        
        return df_v.head(15), df_g.head(15)
    except:
        return pd.DataFrame(columns=['종목명', '등락률', '거래대금(억)', '코드']), pd.DataFrame(columns=['종목명', '등락률', '거래량(만)', '코드'])

def get_current_price(code, market):
    try:
        df = yf.Ticker(f"{code}{'.KS' if '코스피' in str(market) else '.KQ'}").history(period="1d")
        if not df.empty: return int(df['Close'].iloc[-1])
    except: pass
    return None

@st.cache_data(ttl=3600)
def get_all_stock_codes():
    m = {}
    for s in [0, 1]:
        try:
            soup = BeautifulSoup(requests.get(f"https://finance.naver.com/sise/sise_quant.naver?sosok={s}", headers=HDR, timeout=5).text, 'html.parser')
            for a in soup.find_all('a', {'class': 'tltle'}): m[a.get_text().strip()] = a['href'].split('=')[-1]
        except: pass
    return m

def get_stock_chart(code, name, period_choice, market_type):
    try:
        p_val, i_val = ("3mo", "1d") if period_choice == "3개월 (일봉)" else (("1y", "1wk") if period_choice == "1년 (주봉)" else ("3y", "1wk"))
        df = yf.Ticker(f"{code}{'.KS' if '코스피' in str(market_type) else '.KQ'}").history(period=p_val, interval=i_val)
        if df.empty: return st.warning("⚠️ 차트 데이터 없음")
        
        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA60'] = df['Close'].rolling(60).mean()
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_width=[0.25, 0.75])
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="주가", increasing_line_color='#ef4444', decreasing_line_color='#3b82f6'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MA5'], line=dict(color='#ff9800', width=1.5), name='5선'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='#4caf50', width=1.5), name='20선'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MA60'], line=dict(color='#9c27b0', width=1.5), name='60선'), row=1, col=1)
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="거래량", marker_color=['#ef4444' if r['Close'] >= r['Open'] else '#3b82f6' for _, r in df.iterrows()]), row=2, col=1)
        fig.update_layout(xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10), height=400, template="plotly_white")
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e: st.error(f"차트 에러: {e}")

def parse_rate(val):
    try: return float(str(val).replace('%','').replace('+','').strip())
    except: return 0.0

st.title("📈 주간 투자 추천 & 스마트 포트폴리오 대시보드")
st.caption(f"📅 기준일: {datetime.now().strftime('%Y-%m-%d')} | 수급 및 모멘텀 실시간 추적 시스템")

sheet_df = load_portfolio_from_sheets(G_URL)
code_master = get_all_stock_codes()

st.markdown("---")
tab_buy, tab_sell = st.tabs(["➕ 새 추천 주식 매수 추가", "➖ 주식 매도 기록"])

with tab_buy:
    with st.form("add_form", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        n = c1.text_input("종목명", placeholder="예: 삼성전자")
        p = c2.number_input("매수가(원)", min_value=0, step=10)
        q = c3.number_input("보유주수(주)", min_value=1,
