import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import io
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 페이지 설정
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
    """네이버 금융 테이블 구조와 100% 매칭되도록 보정된 스크래핑 함수"""
    try:
        # 1. 거래대금 상위 (수급) 파싱
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
        if not df_v.empty:
            df_v = df_v.query("종목명 != '종목명'").head(len(stk_v)).copy()
            df_v['코드'] = [s['코드'] for s in stk_v[:len(df_v)]]
            df_v['거래대금'] = pd.to_numeric(df_v['거래대금'], errors='coerce').fillna(0)
            df_v['거래대금(억)'] = (df_v['거래대금'] / 1000).round(1)
            df_v = df_v.head(15).reset_index(drop=True)

        # 2. 상승률 상위 (추세) 파싱
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
        if not df_g.empty:
            df_g = df_g.query("종목명 != '종목명'").head(len(stk_g)).copy()
            df_g['코드'] = [s['코드'] for s in stk_g[:len(df_g)]]
            df_g['raw_vol'] = pd.to_numeric(df_g['거래량'], errors='coerce').fillna(0)
            df_g['거래량(만)'] = (df_g['raw_vol'] / 10000).round(1)
            df_g = df_g.head(15).reset_index(drop=True)

        return df_v, df_g
    except Exception as e:
        st.error(f"마켓 데이터 가져오기 실패: {e}")
        return pd.DataFrame(columns=['종목명', '등락률', '거래대금(억)', '코드']), pd.DataFrame(columns=['종목명', '등락률', '거래량(만)', '코드', 'raw_vol'])

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
        suffix = ".KQ" if "코스닥" in str(market) else ".KS"
        full_ticker = f"{code}{suffix}"
        ticker_obj = yf.Ticker(full_ticker)
        df = ticker_obj.history(period="1d")
        if not df.empty:
            return int(df['Close'].iloc[-1])
    except:
        pass
    return None

def get_stock_chart(code, name, period_choice, market_type):
    try:
        p_val, i_val = "3mo", "1d"
        if period_choice == "1년 (주봉)":
            p_val, i_val = "1y", "1wk"
        elif period_choice == "3년 (주봉)":
            p_val, i_val = "3y", "1wk"
            
        suffix = ".KQ" if "코스닥" in str(market_type) else ".KS"
        df = yf.Ticker(f"{code}{suffix}").history(period=p_val, interval=i_val)
        
        if df.empty:
            st.warning("⚠️ 차트 데이터 없음")
            return
        
        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA60'] = df['Close'].rolling(60).mean()
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_width=[0.25, 0.75])
        
        fig.add_trace(go.Candlestick(
            x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
            name="주가", increasing_line_color='#ef4444', decreasing_line_color='#3b82f6'
        ), row=1, col=1)
        
        fig.add_trace(go.Scatter(x=df.index, y=df['MA5'], line=dict(color='#ff9800', width=1.5), name='5선'), row=1, col=1)
        fig.add_trace(
