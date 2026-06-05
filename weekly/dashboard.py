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

# 🎯 사장님의 최신 구글 연동 주소 및 시트 설정
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

# 브라우저 차단 우회용 표준 헤더 고정
HTTP_HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'}

# 구글 스프레드시트 로드 함수
def load_portfolio_from_sheets(url, sheet_name="보유현황"):
    try:
        if "/edit" in url:
            base_url = url.split("/edit")[0]
            csv_url = f"{base_url}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
        else:
            csv_url = url
        response = requests.get(f"{csv_url}&t={int(datetime.now().timestamp())}", headers=HTTP_HEADERS, timeout=10)
        if response.status_code == 200:
            df = pd.read_csv(io.StringIO(response.text))
            if not df.empty:
                # 안전하게 컬럼명의 공백을 모두 제거합니다.
                df.columns = [str(c).strip() for c in df.columns]
                if '종목명' in df.columns:
                    df = df.dropna(subset=['종목명'])
                    df['매수가'] = pd.to_numeric(df['매수가'], errors='coerce').fillna(0)
                    df['보유주수'] = pd.to_numeric(df['보유주수'], errors='coerce').fillna(1)
                    return df
        return pd.DataFrame()
    except:
        return pd.DataFrame()

# 주간 시장 데이터 안전 파싱 함수 (차단 방지 패치 완료)
@st.cache_data(ttl=300)
def fetch_weekly_market_data(sosok_code):
    try:
        # 1. 거래대금 상위
        url_v = f"https://finance.naver.com/sise/sise_quant.naver?sosok={sosok_code}"
        res_v = requests.get(url_v, headers=HTTP_HEADERS, timeout=10)
        soup_v = BeautifulSoup(res_v.text, 'html.parser')
        table_v = soup_v.find('table', {'class': 'type_2'})
        
        stocks = []
        for row in table_v.find_all('tr'):
            anchor = row.find('a', {'class': 'tltle'})
            if anchor: stocks.append({'종목명': anchor.get_text().strip(), '코드': anchor['href'].split('=')[-1]})
                
        # pd.read_html에 직접 URL을 넣으면 차단되므로, 우회 처리된 텍스트를 io.StringIO로 주입합니다.
        df_v = pd.read_html(io.StringIO(str(table_v)))[0].dropna(subset=['종목명'])
        df_v = df_v[df_v['종목명'] != '종목명'].head(10).copy()
        df_v['코드'] = [s['코드'] for s in stocks[:len(df_v)]]
        df_v['raw_val'] = pd.to_numeric(df_v['거래대금'], errors='coerce').fillna(0)
        df_v['거래대금(억)'] = (df_v['raw_val'] / 1000).round(1)

        # 2. 주간 상승률 상위
        url_w = f"https://finance.naver.com/sise/sise_low_up.naver?sosok={sosok_code}"
        res_w = requests.get(url_w, headers=HTTP_HEADERS, timeout=10)
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
    except Exception as e:
        # 오류 발생 시 빈 데이터프레임 구조를 강제 반환하여 시스템 다운을 예방합니다.
        empty_v = pd.DataFrame(columns=['종목명', '현재가', '거래대금(억)', '코드'])
        empty_w = pd.DataFrame(columns=['종목명', '현재가', '주간등락률', '코드'])
        return empty_v, empty_w

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
    for sosok in [0, 1]:
        url = f"https://finance.naver.com/sise/sise_quant.naver?sosok={sosok}"
        try:
            res = requests.get(url, headers=HTTP_HEADERS, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
            for anchor in soup.find_all('a', {'class': 'tltle'}): 
                mapping[anchor.get_text().strip()] = anchor['href'].split('=')[-1]
        except: pass
    return mapping

def get_stock_chart(code, name, period_choice, market_type):
    suffix = ".KS" if "코스피" in str(market_type) else ".KQ"
    full_code = f"{code}{suffix}"
    try:
        ticker = yf.Ticker(full_code)
        if period_choice == "하루 (1분봉)": period_val, interval_val = "1d", "1m"
        elif period_choice == "일주일 (30분봉)": period_val, interval_val = "5d", "30m"
        else: period_val, interval_val = "1mo", "1d"
            
        df = ticker.history(period=period_val, interval=interval_val)
        if df.empty: df = ticker.history(period="5d", interval="30m")
        
        if not df.empty:
            df['MA5'] = df['Close'].rolling(window=5).mean()
            df['MA10'] = df['Close'].rolling(window=10).mean()
            df['MA20'] = df['Close'].rolling(window=20).mean()
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_width=[0.25, 0.75])
            fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="주가", increasing_line_color='#ef4444', decreasing_line_color='#3b82f6'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MA5'], line=dict(color='#ff9800', width=1.5), name='5일선'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MA10'], line=dict(color='#4caf50', width=1.5), name='10일선'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='#9c27b0', width=1.5), name='20일선'), row=1, col=1)
            colors = ['#ef4444' if r['Close'] >= r['Open'] else '#3b82f6' for _, r in df.iterrows()]
            fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="거래량", marker_color=colors), row=2, col=1)
            fig.update_layout(xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10), height=400, template="plotly_white")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("⚠️ 차트 데이터를 불러올 수 없습니다. 야후 파이낸스 일시적 지연일 수 있습니다.")
    except Exception as e:
        st
