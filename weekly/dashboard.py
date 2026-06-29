import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import io
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="Dashboard", layout="wide")

HDR = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
G_URL = "https://docs.google.com/spreadsheets/d/1pMpXBZh3sIDE79e7vNmUgdVEU8f-qbywYy7biuWoUNM/edit?usp=sharing"
W_URL = "https://script.google.com/macros/s/AKfycbw0EcgCR_myrhrtZbtDn1d3Jq11p__mqQCOnoqZ3fO6-G5juC-x3XdWuyDtdWULfwJ6/exec"

def load_portfolio_from_sheets(url, sheet_name="보유현황"):
    try:
        csv_url = f"{url.split('/edit')[0]}/gviz/tq?tqx=out:csv&sheet={sheet_name}" if "/edit" in url else url
        res = requests.get(f"{csv_url}&t={int(datetime.now().timestamp())}", headers=HDR, timeout=5)
        if res.status_code == 200:
            df = pd.read_csv(io.StringIO(res.text))
            if not df.empty:
                df.columns = [c.strip() for c in df.columns]
                return df.dropna(subset=['종목명'])
        return pd.DataFrame()
    except: return pd.DataFrame()

@st.cache_data(ttl=600)
def fetch_market_data(sosok):
    try:
        r1 = requests.get(f"https://finance.naver.com/sise/sise_quant.naver?sosok={sosok}", headers=HDR, timeout=5)
        s1 = BeautifulSoup(r1.text, 'html.parser')
        t1 = s1.find('table', {'class': 'type_2'})
        v_list = [{'종목명': a.get_text().strip(), '코드': a['href'].split('=')[-1]} for r in t1.find_all('tr') for a in [r.find('a', {'class': 'tltle'})] if a] if t1 else []
        df_v = pd.DataFrame()
        if t1 and v_list:
            df_v = pd.read_html(io.StringIO(str(t1)))[0].dropna(subset=['종목명'])
            df_v = df_v.query("종목명 != '종목명'").head(len(v_list)).copy()
            df_v['코드'] = [x['코드'] for x in v_list[:len(df_v)]]
            df_v['거래대금(억)'] = (pd.to_numeric(df_v['거래대금'], errors='coerce').fillna(0) / 1000).round(1)
            df_v = df_v.head(15).reset_index(drop=True)

        r2 = requests.get(f"https://finance.naver.com/sise/sise_rise.naver?sosok={sosok}", headers=HDR, timeout=5)
        s2 = BeautifulSoup(r2.text, 'html.parser')
        t2 = s2.find('table', {'class': 'type_2'})
        g_list = [{'종목명': a.get_text().strip(), '코드': a['href'].split('=')[-1]} for r in t2.find_all('tr') for a in [r.find('a', {'class': 'tltle'})] if a] if t2 else []
        df_g = pd.DataFrame()
        if t2 and g_list:
            df_g = pd.read_html(io.StringIO(str(t2)))[0].dropna(subset=['종목명'])
            df_g = df_g.query("종목명 != '종목명'").head(len(g_list)).copy()
            df_g['코드'] = [x['코드'] for x in g_list[:len(df_g)]]
            df_g['거래량(만)'] = (pd.to_numeric(df_g['거래량'], errors='coerce').fillna(0) / 10000).round(1)
            df_g = df_g.head(15).reset_index(drop=True)
        return df_v, df_g
    except: return pd.DataFrame(columns=['종목명','등락률','거래대금(억)','코드']), pd.DataFrame(columns=['종목명','등락률','거래량(만)','코드'])

@st.cache_data(ttl=3600)
def get_all_stock_codes():
    m = {}
    for s in [0, 1]:
        try:
            res = requests.get(f"https://finance.naver.com/sise/sise_quant.naver?sosok={s}", headers=HDR, timeout=5)
            for a in BeautifulSoup(res.text, 'html.parser').find_all('a', {'class': 'tltle'}):
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

def get_stock_chart(code, name, p_choice, market_type):
    try:
        p, i = "3mo", "1d"
        if "1년" in p_choice: p, i = "1y", "1wk"
        elif "3년" in p_choice: p, i = "3y", "1wk"
        sfx = ".KQ" if "코스닥" in str(market_type) else ".KS"
        df = yf.Ticker(f"{code}{sfx}").history(period=p, interval=i)
        if df.empty: return
        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA60'] = df['Close'].rolling(60).mean()
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_width=[0.25, 0.75])
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="Price", increasing_line_color='#ef4444', decreasing_line_color='#3b82f6'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MA5'], line=dict(color='#ff9800', width=1.5), name='MA5'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df
