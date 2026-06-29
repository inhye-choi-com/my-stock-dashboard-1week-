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
                df.columns = [c.strip() for c in df.columns]
                if '종목명' in df.columns:
                    df = df.dropna(subset=['종목명'])
            return df
        return pd.DataFrame()
    except:
        return pd.DataFrame()

@st.cache_data(ttl=600)
def fetch_market_data(sosok):
    try:
        # 1. 거래대금 상위 파싱
        res_v = requests.get(f"https://finance.naver.com/sise/sise_quant.naver?sosok={sosok}", headers=HDR, timeout=5)
        soup_v = BeautifulSoup(res_v.text, 'html.parser')
        t_v = soup_v.find('table', {'class': 'type_2'})
        stk_v = []
        if t_v:
            for r in t_v.find_all('tr'):
                a = r.find('a', {'class': 'tltle'})
                if a:
                    stk_v.append({'종목명': a.get_text().strip(), '코드': a['href'].split('=')[-1]})
        df_v = pd.DataFrame()
        if t_v and stk_v:
            try:
                raw_dfs = pd.read_html(io.StringIO(str(t_v)))
                if raw_dfs:
                    df_v = raw_dfs[0].dropna(subset=['종목명']).copy()
                    df_v = df_v.query("종목명 != '종목명'").head(len(stk_v)).copy()
                    df_v['코드'] = [s['코드'] for s in stk_v[:len(df_v)]]
                    df_v['거래대금'] = pd.to_numeric(df_v['거래대금'], errors='coerce').fillna(0)
                    df_v['거래대금(억)'] = (df_v['거래대금'] / 1000).round(1)
                    df_v = df_v.head(15).reset_index(drop=True)
            except: pass

        # 2. 상승률 상위 파싱
        res_g = requests.get(f"https://finance.naver.com/sise/sise_rise.naver?sosok={sosok}", headers=HDR, timeout=5)
        soup_g = BeautifulSoup(res_g.text, 'html.parser')
        t_g = soup_g.find('table', {'class': 'type_2'})
        stk_g = []
        if t_g:
            for r in t_g.find_all('tr'):
                a = r.find('a', {'class': 'tltle'})
                if a:
                    stk_g.append({'종목명': a.get_text().strip(), '코드': a['href'].split('=')[-1]})
        df_g = pd.DataFrame()
        if t_g and stk_g:
            try:
                raw_dfs_g = pd.read_html(io.StringIO(str(t_g)))
                if raw_dfs_g:
                    df_g = raw_dfs_g[0].dropna(subset=['종목명']).copy()
                    df_g = df_g.query("종목명 != '종목명'").head(len(stk_g)).copy()
                    df_g['코드'] = [s['코드'] for s in stk_g[:len(df_g)]]
                    df_g['raw_vol'] = pd.to_numeric(df_g['거래량'], errors='coerce').fillna(0)
                    df_g['거래량(만)'] = (df_g['raw_vol'] / 10000).round(1)
                    df_g = df_g.head(15).reset_index(drop=True)
            except: pass
        return df_v, df_g
    except:
        return pd.DataFrame(columns=['종목명', '등락률', '거래대금(억)', '코드']), pd.DataFrame(columns=['종목명', '등락률', '거래량(만)', '코드', 'raw_vol'])

@st.cache_data(ttl=3600)
def get_all_stock_codes():
    m = {}
    for s in [0, 1]:
        try:
            res = requests.get(f"https://finance.naver.com/sise/sise_quant.naver?sosok={s}", headers=HDR, timeout=5)
            soup = BeautifulSoup(res.text, 'html.parser')
            for a in soup.find_all('a', {'class': 'tltle'}):
                m[a.get_text().strip()] = a['href'].split('=')[-1]
        except: pass
    return m

def get_current_price(code, market):
    try:
        sfx = ".KQ" if "코스닥" in str(market) else ".KS"
        df = yf.Ticker(f"{code}{sfx}").history(period="1d")
        if not df.empty: return int(df['Close'].iloc[-1])
    except: pass
    return None

def get_stock_chart(code, name, period_choice, market_type):
    """코드 잘림 방지를 위해 가독성 및 라인 길이를 극대화하여 축소한 차트 함수"""
    try:
        p_val, i_val = "3mo", "1d"
        if "
