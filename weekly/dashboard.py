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

# 브라우저인 척 속이기 위한 공통 헤더 (봇 차단 방지)
BASE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

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
# 2. 데이터 에러 방지용 안전 함수 정의 (오류 발생 시 빈 데이터프레임 반환)
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
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=600)  # 10분 캐시로 네이버 차단 우회
def fetch_market_data(sosok_code):
    try:
        # 1. 거래대금 상위
        url_v = f"https://finance.naver.com/sise/sise_quant.naver?sosok={sosok_code}"
        res_v = requests.get(url_v, headers=BASE_HEADERS, timeout=5)
        soup_v = BeautifulSoup(res_v.text, 'html.parser')
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
        df_v['code'] = [s['코드'] for s in stocks[:actual_len_v]]  # 내부 연동용 영문 컬럼 유지
        df_v['코드'] = df_v['code']
        df_v['raw_val'] = pd.to_numeric(df_v['거래대금'], errors='coerce').fillna(0)
        df_v['거래대금(억)'] = (df_v['raw_val'] / 1000).round(1)
        
        # 2. 상승률 상위 종목
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
        df_g['code'] = [s['코드'] for s in stocks_g[:actual_len_g]]
        df_g['코드'] = df_g['code']
        df_g['raw_vol'] = pd.to_numeric(df_g['거래량'], errors='coerce').fillna(0)
        df_g['거래량(만)'] = (df_g['raw_vol'] / 10000).round(1)
        
        return df_v, df_g
    except Exception as e:
        st.warning(f"⚠️ 실시간 네이버 금융 데이터 수집에 일시적 지연이 발생했습니다.")
        return pd.DataFrame(columns=['종목명', '등락률', '거래대금(억)', '코드']), pd.DataFrame(columns=['종목명', '등락률', '거래량(만)', '코드'])

def get_current_price(code, market_type):
    suffix = ".KS" if "코스피" in str(market_type) else ".KQ"
    try:
        ticker = yf.Ticker(f"{code}{suffix}")
        todays_data = ticker.history(period="1d")
        if not todays_data.empty: 
            return int(todays_data['Close'].iloc[-1])
    except: 
        pass
    return None

@st.cache_data(ttl=3600)
def get_all_stock_codes():
    mapping = {}
    for sosok in [0, 1]:
        url = f"https://finance.naver.com/sise/sise_quant.naver?sosok={sosok}"
        try:
            res = requests.get(url, headers=BASE_HEADERS, timeout=5)
            soup = BeautifulSoup(res.text, 'html.parser')
            for anchor in soup.find_all('a', {'class': 'tltle'}): 
                mapping[anchor.get_text().strip()] = anchor['href'].split('=')[-1]
        except: 
            pass
    return mapping

# 🔥 [문법 오류 수정 완료] 괄호와 인자값 정상 배치
def get_stock_chart(code, name, period_choice, market_type):
    suffix = ".KS" if "코스피" in str(market_type) else ".KQ"
    full_code = f"{code}{suffix}"
    try:
        ticker = yf.Ticker(full_code)
        if period_choice == "3개월 (일봉)":
            period_val, interval_val = "3mo", "1d"
        elif period_choice == "1년 (주봉)":
            period_val, interval_val = "1y", "1wk"
        else:
            period_val, interval_val = "3y", "1wk"
            
        df = ticker.history(period=period_val, interval=interval_val)
        
        if not df.empty:
            df['MA5'] = df['Close'].rolling(window=5).mean()
            df['MA20'] = df['Close'].rolling(window=20).mean()
            df['MA60'] = df['Close'].rolling(window=60).mean()
            
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_width=[0.25, 0.75])
            fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="주가", increasing_line_color='#ef4444', decreasing_line_color='#3b82f6'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MA5'], line=dict(color='#ff9800', width=1.5), name='5선'), row=1, col=1)
