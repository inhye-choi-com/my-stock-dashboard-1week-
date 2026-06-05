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
        # 1. 거래대금 상위 수집
        res_v = requests.get(f"https://finance.naver.com/sise/sise_quant.naver?sosok={sosok}", headers=HDR, timeout=5)
        soup_v = BeautifulSoup(res_v.text, 'html.parser')
        t_v = soup_v.find('table', {'class': 'type_2'})
        stk_v = []
        if t_v:
            for r in t_v.find_all('tr'):
                a = r.find('a', {'class': 'tltle'})
                if a: stk_v.append({'종목명': a.get_text().strip(), '코드': a['href'].split('=')[-1]})
        df_v = pd.read_html(io.StringIO(str(t_v)))[0].dropna(subset=['종목명']) if t_v else pd.DataFrame()
        df_v = df_v[df_v['종목명'] != '종목명'].head(len(stk_v)).copy()
        df_v['코드'] = [s['코드'] for s in stk_v[:len(df_v)]]
        df_v['거래대금(억)'] = (pd.to_numeric(df_v['거래대금'], errors='coerce').fillna(0) / 1000).round(1)
        
        # 2. 상승률 상위 수집
        res_g = requests.get(f"https://finance.naver.com/sise/sise_rise.naver?sosok={sosok}", headers=HDR, timeout=5)
        soup_g = BeautifulSoup(res_g.text, 'html.parser')
        t_g = soup_g.find('table', {'class': 'type_2'})
        stk_g = []
        if t_g:
            for r in t_g.find_all('tr'):
                a = r.find('a', {'class': 'tltle'})
                if a: stk_g.append({'종목명': a.get_text().strip(), '코드': a['href'].split('=')[-1]})
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
        if not df.empty: return int
