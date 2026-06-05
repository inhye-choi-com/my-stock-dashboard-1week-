import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import io
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# =================================================================
# 1. 페이지 기본 설정 및 기본 차단 헤더 정의
# =================================================================
st.set_page_config(page_title="주간 투자 추천 & 포트폴리오 매니저", layout="wide")

BASE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# 구글 시트 및 웹앱 주소 고정
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1pMpXBZh3sIDE79e7vNmUgdVEU8f-qbywYy7biuWoUNM/edit?usp=sharing"
GOOGLE_WEB_APP_URL = "https://script.google.com/macros/s/AKfycbw0EcgCR_myrhrtZbtDn1d3Jq11p__mqQCOnoqZ3fO6-G5juC-x3XdWuyDtdWULfwJ6/exec"

# 스타일 정의
st.markdown("""
<style>
    .up-color { color: #ef4444; font-weight: bold; }   
    .down-color { color: #3b82f6; font-weight: bold; } 
    .flat-color { color: #6b7280; }                   
    .recommend-row { background-color: #fef08a !important; font-weight: bold; }
    .portfolio-danger { background-color: #fee2e2 !important; color: #b91c1c !important; font-weight: bold; } 
    .portfolio-success { background-color: #dcfce7 !important; color: #15803d !important; font-weight: bold; } 
</style>
""", unsafe_allow_html=True)

# =================================================================
# 2. 데이터 수집 및 차트 함수 정의
# =================================================================

def load_portfolio_from_sheets(url, sheet_name="보유현황"):
    try:
        if "/edit" in url:
            base_url = url.split("/edit")[0]
            csv_url = f"{base_url}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
        else:
            csv_url = url
        
        response = requests.get(f"{csv_url}&t={int(datetime.now().timestamp())}", headers=BASE_HEADERS, timeout=5)
        if response.status_code == 200:
            df = pd.read_csv(io.StringIO(response.text))
            if not df.empty:
                df.columns = [c.strip() for c in df.columns]
                if '종목명' in df.columns:
                    df = df.dropna(subset=['종목명'])
            return df
        return pd.DataFrame()
    except:
        return pd.DataFrame()

@st.cache_data(ttl=600)
def fetch_market_data(sosok_code):
    try:
        # 1. 거래대금 상위 수집
        url_v = f"https://finance.naver.com/sise/sise_quant.naver?sosok={sosok_code}"
        res_v = requests.get(url_v, headers=BASE_HEADERS, timeout=5)
        soup_v = BeautifulSoup(res_v.text, 'html.parser')
        
        # 🔥 [오류 수정] 잘려나갔던 테이블 속성 정의 완벽 복구 및 마감 완료
        table_v = soup_v.find('table', {'class': 'type_2'})
        
        stocks = []
        if table_v:
            rows = table_v.find_all('tr')
            for row in rows:
                anchor = row.find('a', {'class': 'tltle'})
                if anchor: 
                    stocks.append({'종목명': anchor.get_text().strip(), '코드': anchor['href'].split('=')[-1]})
        
        tables = pd.read_html(io.StringIO(str(table_v)))
        df_v = tables[0].dropna(subset=['종목명']) if tables else pd.DataFrame()
        df_v = df_v[df_v['종목명'] != '종목명'].head(15).copy()
        
        actual_len_v = min(len(df_v), len(stocks))
        df_v = df_v.head(actual_len_v).copy()
        df_v['코드'] = [s['코드'] for s in stocks[:actual_len_v]]
        
        df_v['raw_val'] = pd.to_numeric(df_v['거래대금'], errors='coerce').fillna(0)
        df_v['거래대금(억)'] = (df_v['raw_val'] / 1000).round(1)
        
        # 2. 상승률 상위 종목 수집
        url_g = f"https://finance.naver.com/sise/sise_rise.naver?sosok={sosok_code}"
        res_g = requests.get(url_g, headers=BASE_HEADERS, timeout=5)
        soup_g = BeautifulSoup(res_g.text, 'html.parser')
        table_g = soup_g.find('table', {'class': 'type_2'})
        
        stocks_g = []
        if table_g:
            rows_g = table_g.find_all('tr')
            for row in rows_g:
                anchor = row.find('a', {'class': 'tltle'})
                if anchor: 
                    stocks_g.append({'종목명': anchor.get_text().strip(), '코드': anchor['href'].split('=')[-1]})
                    
        tables_g = pd.read_html(io.StringIO(str(table_g)))
        df_g = tables_g[0].dropna(subset=['종목명']) if tables_g else pd.DataFrame()
        df_g = df_g[df_g['종목명'] != '종목명'].head(15).copy()
        
        actual_len_g = min(len(df_g), len(stocks_g))
        df_g = df_g.head(actual_len_g).copy()
        df_g['코드'] = [s['코드'] for s in stocks_g[:actual_len_g]]
        
        df_g['raw_vol'] = pd.to_numeric(df_g['거래량'], errors='coerce').fillna(0)
        df_g['거래량(만)'] = (df_g['raw_vol'] / 10000).round(1)
        
        return df_v, df_g

    except Exception as e:
        st.warning("⚠️ 실시간 네이버 금융 데이터 수집에 일시적 지연이 발생했습니다.")
        return pd.
