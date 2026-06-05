import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import io
from streamlit_autorefresh import st_autorefresh
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 페이지 기본 설정
st.set_page_config(page_title="주간 스윙 투자 & 포트폴리오 패널", layout="wide")

# 🎯 연동 주소 고정
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1pMpXBZh3sIDE79e7vNmUgdVEU8f-qbywYy7biuWoUNM/edit?usp=sharing"
GOOGLE_WEB_APP_URL = "https://script.google.com/macros/s/AKfycbw0EcgCR_myrhrtZbtDn1d3Jq11p__mqQCOnoqZ3fO6-G5juC-x3XdWuyDtdWULfwJ6/exec"

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

# 구글 스프레드시트 로드 함수
def load_portfolio_from_sheets(url, sheet_name="보유현황"):
    try:
        if "/edit" in url:
            base_url = url.split("/edit")[0]
            csv_url = f"{base_url}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
        else:
            csv_url = url
        response = requests.get(f"{csv_url}&t={int(datetime.now().timestamp())}", timeout=10)
        if response.status_code == 200:
            df = pd.read_csv(io.StringIO(response.text))
            if not df.empty:
                df.columns = [c.strip() for c in df.columns]
                df = df.dropna(subset=['종목명'])
            return df
        return pd.DataFrame()
    except:
        return pd.DataFrame()

# 주간(5영업일) 급등주 및 수급주 포착을 위한 데이터 수집 함수 (오류 수정 완료)
@st.cache_data(ttl=600)
def fetch_weekly_market_data(sosok_code):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    # 1. 거래대금 상위 수집
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

    # 2. 주간 상승률 상위 (기존 컬럼명 매핑 오류 전면 수정)
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
    
    # 오류 방지: 컬럼 이름을 안전한 순서(index) 기반으로 접근하여 추출합니다.
    # 네이버 시세 테이블 컬럼 순서: [N, 종목명, 현재가, 전일비, 등락률, 거래량, 거래대금, ...]
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

def parse_rate(val_str):
    try: return float(str(val_str).replace('%','').replace('+','').strip())
    except: return 0.0

# UI 렌더링
st_autorefresh(interval=300000, key="datarefresh") 

st.title("📈 주간 스윙 매매 시스템 & 포트폴리오 패널")
st.caption(f"📅 조회 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 🔄 주간 트렌드 분석 모드")

sheet_df = load_portfolio_from_sheets(GOOGLE_SHEET_URL, sheet_name="보유현황")
code_master = get_all_stock_codes()

# ----------------- 매수 / 매도 관리 입력 폼 -----------------
st.markdown("---")
tab_buy, tab_sell = st.tabs(["➕ 새 주식 매수 추가", "➖ 주식 매도 기록"])

with tab_buy:
    with st.form("add_stock_form", clear_on_submit=True):
        f_col1, f_col2, f_col3, f_col4 = st.columns(4)
        with f_col1: new_name = st.text_input("종목명", placeholder="예: 삼성전자", key="b_name")
        with f_col2: new_price = st.number_input("매수가(원)", min_value=0, step=10, value=0, key="b_price")
        with f_col3: new_qty = st.number_input("보유주수(주)", min_value=1, step=1, value=1, key="b_qty")
        with f_col4: new_market = st.selectbox("시장", ["코스피", "코스닥"], key="b_market")
        submit_btn = st.form_submit_button("💼 포트폴리오에 주간 매수 추가")
        
        if submit_btn:
            if new_name.strip() == "" or new_price <= 0: st.error("❌ 종목명과 정확한 매수 가격을 입력해 주세요.")
            else:
                with st.spinner("구글 시트에 기록 중..."):
                    payload = {"action": "buy", "stock_name": new_name.strip(), "buy_price": int(new_price), "qty": int(new_qty), "market": new_market}
                    try:
                        requests.post(GOOGLE_WEB_APP_URL, json=payload, timeout=10)
                        st.success(f"🎉 {new_name} 스윙 종목 매수 완료!")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e: st.error(f"전송 실패: {e}")

with tab_sell:
    with st.form("sell_stock_form", clear_on_submit=True):
        s_col1, s_col2, s_col3 = st.columns(3)
        active_stocks = sheet_df['종목명'].dropna().unique().tolist() if not sheet_df.empty and '종목명' in sheet_df.columns else []
        with s_col1: sell_name = st.selectbox("매도할 종목 선택", active_stocks if active_stocks else ["보유 주식 없음"])
        
        max_sell_qty = 1000000
        current_hold_qty = 0
        if not sheet_df.empty and '종목명' in sheet_df.columns and sell_name in sheet_df['종목명'].values:
            matching_row = sheet_df[sheet_df['종목명'] == sell_name].iloc[0]
            current_hold_qty = int(pd.to_numeric(matching_row['보유주수'], errors='coerce'))
            max_sell_qty = current_hold_qty if current_hold_qty > 0 else 1000000
            
        with s_col2: sell_price = st.number_input("매도가(원)", min_value=0, step=10, value=0)
        with s_col3: sell_qty = st.number_input(f"매도 주수 (최대 {current_hold_qty}주 보유 중)", min_value=1, max_value=max_sell_qty, step=1, value=min(1, max_sell_qty))
        sell_btn = st.form_submit_button("🚨 실현 손익 확정 청산")
        
        if sell_btn and sell_name != "보유 주식 없음":
            if sell_price <= 0: st.error("❌ 정확한 매도 가격을 입력해 주세요.")
            else:
                matching = sheet_df[sheet_df['종목명'] == sell_name]
                if not matching.empty:
                    buy_price_avg = int(pd.to_numeric(matching.iloc[0]['매수가'], errors='coerce'))
                    profit_calculated = int((sell_price - buy_price_avg) * int(sell_qty))
                    
                    with st.spinner("구글 연동 처리 중..."):
                        payload = {
                            "action": "sell", 
                            "stock_name": sell_name, 
                            "buy_price": int(buy_price_avg),
                            "sell_price": int(sell_price), 
                            "qty": int(sell_qty), 
                            "profit": int(profit_calculated), 
                            "date": datetime.now().strftime("%Y-%m-%d %H:%M")
                        }
                        try:
                            requests.post(GOOGLE_WEB_APP_URL, json=payload, timeout=10)
                            st.success(f"🎉 {sell_name} 분할 청산 성공!")
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as e: st.error(f"전송 실패: {e}")

# ----------------- 상단 실시간 보유 주식 종합 현황 -----------------
st.subheader("📋 내 주간 보유 현황 & 스윙 수익률 감시")
my_stock_list = []

if not sheet_df.empty and "종목명" in sheet_df.columns:
    p_html = "<table style='width:100%; border-collapse:collapse; text-align:left;'>"
