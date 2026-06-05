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

BASE_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0'
    )
}

GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1pMpXBZh3sIDE79e7vNmUgdVEU8f-qbywYy7biuWoUNM/edit?usp=sharing"
GOOGLE_WEB_APP_URL = "https://script.google.com/macros/s/AKfycbw0EcgCR_myrhrtZbtDn1d3Jq11p__mqQCOnoqZ3fO6-G5juC-x3XdWuyDtdWULfwJ6/exec"

# CSS 스타일에 '양타점 추천주용 강렬한 빨간색 음영' 추가
st.markdown("""
<style>
    .up-color { color: #ef4444; font-weight: bold; }   
    .down-color { color: #3b82f6; font-weight: bold; } 
    .flat-color { color: #6b7280; }                   
    .recommend-row { background-color: #fef08a !important; font-weight: bold; }
    .super-recommend-row { background-color: #fee2e2 !important; border: 2px solid #ef4444 !important; font-weight: bold; color: #b91c1c !important; }
    .portfolio-danger { background-color: #fee2e2 !important; color: #b91c1c !important; font-weight: bold; } 
    .portfolio-success { background-color: #dcfce7 !important; color: #15803d !important; font-weight: bold; } 
</style>
""", unsafe_allow_html=True)

def load_portfolio_from_sheets(url, sheet_name="보유현황"):
    try:
        if "/edit" in url:
            base_url = url.split("/edit")[0]
            csv_url = f"{base_url}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
        else:
            csv_url = url
        timestamp = int(datetime.now().timestamp())
        res = requests.get(f"{csv_url}&t={timestamp}", headers=BASE_HEADERS, timeout=5)
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
def fetch_market_data(sosok_code):
    try:
        url_v = f"https://finance.naver.com/sise/sise_quant.naver?sosok={sosok_code}"
        res_v = requests.get(url_v, headers=BASE_HEADERS, timeout=5)
        soup_v = BeautifulSoup(res_v.text, 'html.parser')
        table_v = soup_v.find('table', {'class': 'type_2'})
        
        stocks = []
        if table_v:
            for row in table_v.find_all('tr'):
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
        
        url_g = f"https://finance.naver.com/sise/sise_rise.naver?sosok={sosok_code}"
        res_g = requests.get(url_g, headers=BASE_HEADERS, timeout=5)
        soup_g = BeautifulSoup(res_g.text, 'html.parser')
        table_g = soup_g.find('table', {'class': 'type_2'})
        
        stocks_g = []
        if table_g:
            for row in table_g.find_all('tr'):
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
        st.warning("⚠️ 네이버 금융 수집 지연이 발생했습니다.")
        cols_v = ['종목명', '등락률', '거래대금(억)', '코드']
        cols_g = ['종목명', '등락률', '거래량(만)', '코드']
        return pd.DataFrame(columns=cols_v), pd.DataFrame(columns=cols_g)

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

def get_stock_chart(code, name, period_choice, market_type):
    suffix = ".KS" if "코스피" in str(market_type) else ".KQ"
    full_code = f"{code}{suffix}"
    try:
        ticker = yf.Ticker(full_code)
        if period_choice == "3개월 (일봉)":
            p_val, i_val = "3mo", "1d"
        elif period_choice == "1년 (주봉)":
            p_val, i_val = "1y", "1wk"
        else:
            p_val, i_val = "3y", "1wk"
            
        df = ticker.history(period=p_val, interval=i_val)
        if df.empty:
            st.warning("⚠️ 차트 데이터를 불러올 수 없습니다.")
            return

        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_width=[0.25, 0.75])
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="주가", increasing_line_color='#ef4444', decreasing_line_color='#3b82f6'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MA5'], line=dict(color='#ff9800', width=1.5), name='5선'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='#4caf50', width=1.5), name='20선'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MA60'], line=dict(color='#9c27b0', width=1.5), name='60선'), row=1, col=1)
        
        colors = ['#ef4444' if r['Close'] >= r['Open'] else '#3b82f6' for _, r in df.iterrows()]
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="거래량", marker_color=colors), row=2, col=1)
        fig.update_layout(xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10), height=450, template="plotly_white")
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"차트 에러: {e}")

def parse_rate(val_str):
    try: return float(str(val_str).replace('%','').replace('+','').strip())
    except: return 0.0

# ----------------- UI 시작 -----------------
st.title("📈 주간 투자 추천 & 스마트 포트폴리오 대시보드")
today_str = datetime.now().strftime('%Y-%m-%d')
st.caption(f"📅 기준일: {today_str} | 수급 및 모멘텀 실시간 추적 시스템")

sheet_df = load_portfolio_from_sheets(GOOGLE_SHEET_URL, sheet_name="보유현황")
code_master = get_all_stock_codes()

st.markdown
