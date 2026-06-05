import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import io
from streamlit_autorefresh import st_autorefresh
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 페이지 기본 설정
st.set_page_config(page_title="주간 스윙 매매 시스템 & 포트폴리오 패널", layout="wide")

# 🎯 사장님의 최신 구글 연동 주소 전면 반영
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1pMpXBZh3sIDE79e7vNmUgdVEU8f-qbywYy7biuWoUNM/edit?usp=sharing"
GOOGLE_WEB_APP_URL = "https://script.google.com/macros/s/AKfycbxfJVqHishHZVCtX9g2qaU5IAnfbsQfwylOBnIfYxLj2d6QLq7kiMOBtp-AFbCaIWwQ/exec"

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

# 구글 스프레드시트 로드 함수 (캐시를 제거하고 실시간성 강화)
def load_portfolio_from_sheets(url, sheet_name="보유현황"):
    try:
        if "/edit" in url:
            base_url = url.split("/edit")[0]
            csv_url = f"{base_url}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
        else:
            csv_url = url
        # 타임스탬프를 더해 매번 새로운 데이터를 긁어오도록 강제 유도
        response = requests.get(f"{csv_url}&t={int(datetime.now().timestamp())}", timeout=10)
        if response.status_code == 200:
            df = pd.read_csv(io.StringIO(response.text))
            if not df.empty:
                df.columns = [c.strip() for c in df.columns]
                df = df.dropna(subset=['종목명'])
                # 데이터 정제: 매수가, 보유주수 공백 제거 및 숫자 변환
                df['매수가'] = pd.to_numeric(df['매수가'], errors='coerce')
                df['보유주수'] = pd.to_numeric(df['보유주수'], errors='coerce')
            return df
        return pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()

# 주간 시장 데이터 안전 파싱 함수
@st.cache_data(ttl=300)
def fetch_weekly_market_data(sosok_code):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    # 1. 거래대금 상위
    url_v = f"https://finance.naver.com/sise/sise_quant.naver?sosok={sosok_code}"
    res_v = requests.get(url_v, headers=headers, timeout=10)
    soup_v = BeautifulSoup(res_v.text, 'html.parser')
    table_v = soup_v.find('table', {'class': 'type_2'})
    
    stocks = []
    for row in table_v.find_all('tr'):
        anchor = row.find('a', {'class': 'tltle'})
        if anchor: stocks.append({'종목명': anchor.get_text().strip(), '코드': anchor['href'].split('=')[-1]})
            
    df_v = pd.read_html(io.StringIO(str(table_v)))[0].dropna(subset=['종목명'])
    df_v = df_v[df_v['종목명'] != '종목명'].head(10).copy()
    df_v['코드'] = [s['코드'] for s in stocks[:len(df_v)]]
    df_v['raw_val'] = pd.to_numeric(df_v['거래대금'], errors='coerce').fillna(0)
    df_v['거래대금(억)'] = (df_v['raw_val'] / 1000).round(1)

    # 2. 주간 상승률 상위 (순서 기반 안전 파싱 기법 적용)
    url_w = f"https://finance.naver.com/sise/sise_low_up.naver?sosok={sosok_code}"
    res_w = requests.get(url_w, headers=headers, timeout=10)
    soup_w = BeautifulSoup(res_w.text, 'html.parser')
    table_w = soup_w.find('table', {'class': 'type_2'})
    
    stocks_w = []
    for row in table_w.find_all('tr'):
        anchor = row.find('a', {'class': 'tltle'})
        if anchor: stocks_w.append({'종목명': anchor.get_text().strip(), '코드': anchor['href'].split('=')[-1]})
            
    df_w = pd.read_html(io.StringIO(str(table_w)))[0].dropna(subset=['종목명'])
    df_w = df_w[df_w['종목명'] != '종목명'].head(10).copy()
    df_w['코드'] = [s['코드'] for s in stocks_w[:len(df_w)]]
    
    df_w.columns = [f"col_{i}" for i in range(len(df_w.columns))]
    df_w = df_w.rename(columns={"col_1": "종목명", "col_2": "현재가", "col_4": "주간등락률"})
    
    return df_v, df_w

def get_current_price(code, market_type):
    suffix = ".KS" if "코스피" in str(market_type) else ".KQ"
    try:
        ticker = yf.Ticker(f"{code}{suffix}")
        todays_data = ticker.history(period="1d")
        if not todays_data.empty: return int(todays_data['Close'].iloc[-1])
    except: pass
    return None

@st.cache_data(ttl=3600)
def get_all_stock_codes():
    mapping = {}
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    for sosok in [0, 1]:
        url = f"https://finance.naver.com/sise/sise_quant.naver?sosok={sosok}"
        try:
            res = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
            for anchor in soup.find_all('a', {'class': 'tltle'}): mapping[anchor.get_text().strip()] = anchor['href'].split('=')[-1]
        except: pass
    return mapping

def get_stock_chart(code, name, period_choice, market_type):
    suffix = ".KS" if "코스피" in str(market_type) else ".KQ"
    full_code = f"{code}{suffix}"
    ticker = yf.Ticker(full_code)
    
    if period_choice == "하루 (1분봉)": period_val, interval_val = "1d", "1m"
    elif period_choice == "일주일 (30분봉)": period_val, interval_val = "5d", "30m"
    else: period_val, interval_val = "1mo", "1d"
        
    df = ticker.history(period=period_val, interval=interval_val)
    if df.empty: df = ticker.history(period="5d", interval="30m")
    
    if not df.empty:
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA10'] = df['Close'].rolling(window=10).mean()
        df['MA20']
