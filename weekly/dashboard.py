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
    """네이버 금융 테이블 구조와 100% 매칭되도록 보정된 스크래핑 함수"""
    try:
        # 1. 거래대금 상위 (수급) 파싱
        res_v = requests.get(f"https://finance.naver.com/sise/sise_quant.naver?sosok={sosok}", headers=HDR, timeout=5)
        soup_v = BeautifulSoup(res_v.text, 'html.parser')
        t_v = soup_v.find('table', {'class': 'type_2'})
        
        # BeautifulSoup으로 종목명과 순서대로 코드 매칭
        stk_v = []
        if t_v:
            for r in t_v.find_all('tr'):
                a = r.find('a', {'class': 'tltle'})
                if a:
                    stk_v.append({'종목명': a.get_text().strip(), '코드': a['href'].split('=')[-1]})
        
        # pd.read_html로 깨끗하게 데이터프레임 변환 후 결합
        df_v = pd.read_html(io.StringIO(str(t_v)))[0].dropna(subset=['종목명']) if t_v else pd.DataFrame()
        if not df_v.empty:
            df_v = df_v.query("종목명 != '종목명'").head(len(stk_v)).copy()
            df_v['코드'] = [s['코드'] for s in stk_v[:len(df_v)]]
            # 거래대금 컬럼 타입을 숫자로 안전하게 변경
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
            # 거래량 문자열 처리 방어
            df_g['raw_vol'] = pd.to_numeric(df_g['거래량'], errors
