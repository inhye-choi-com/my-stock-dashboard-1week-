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
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )
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
        
        timestamp = int(datetime.now().timestamp())
        full_url = f"{csv_url}&t={timestamp}"
        response = requests.get(full_url, headers=BASE_HEADERS, timeout=5)
        
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
        table_v = soup_v.find('table', {'class': 'type_2'})
        
        stocks = []
        if table_v:
            rows = table_v.find_all('tr')
            for row in rows:
                anchor = row.find('a', {'class': 'tltle'})
                if anchor: 
                    stocks.append({
                        '종목명': anchor.get_text().strip(), 
                        '코드': anchor['href'].split('=')[-1]
                    })
        
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
                    stocks_g.append({
                        '종목명': anchor.get_text().strip(), 
                        '코드': anchor['href'].split('=')[-1]
                    })
                    
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
        # 🔥 [버퍼 보완 패치] 긴 한글 리스트 선언부를 안전하게 한 줄씩 분할
        cols_v = [
            '종목명', 
            '등락률', 
            '거래대금(억)', 
            '코드'
        ]
        cols_g = [
            '종목명', 
            '등락률', 
            '거래량(만)', 
            '코드'
        ]
        err_df_v = pd.DataFrame(columns=cols_v)
        err_df_g = pd.DataFrame(columns=cols_g)
        return err_df_v, err_df_g

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
            period_val, interval_val = "3mo", "1d"
        elif period_choice == "1년 (주봉)":
            period_val, interval_val = "1y", "1wk"
        else:
            period_val, interval_val = "3y", "1wk"
            
        df = ticker.history(period=period_val, interval=interval_val)
        
        if df.empty:
            st.warning("⚠️ 차트 데이터를 불러올 수 없습니다.")
            return

        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        
        fig = make_subplots(
            rows=2, cols=1, 
            shared_xaxes=True, 
            vertical_spacing=0.05, 
            row_width=[0.25, 0.75]
        )
        
        fig.add_trace(go.Candlestick(
            x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], 
            name="주가", increasing_line_color='#ef4444', decreasing_line_color='#3b82f6'
        ), row=1, col=1)
        
        fig.add_trace(go.Scatter(x=df.index, y=df['MA5'], line=dict(color='#ff9800', width=1.5), name='5선'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='#4caf50', width=1.5), name='20선'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MA60'], line=dict(color='#9c27b0', width=1.5), name='60선'), row=1, col=1)
        
        colors = ['#ef4444' if r['Close'] >= r['Open'] else '#3b82f6' for _, r in df.iterrows()]
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="거래량", marker_color=colors), row=2, col=1)
        
        fig.update_layout(
            xaxis_rangeslider_visible=False, 
            margin=dict(l=10, r=10, t=10, b=10), 
            height=450, 
            template="plotly_white"
        )
        st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        st.error(f"차트 생성 중 오류가 발생했습니다: {e}")

def parse_rate(val_str):
    try: return float(str(val_str).replace('%','').replace('+','').strip())
    except: return 0.0

# =================================================================
# 3. 메인 UI 렌더링 시작
# =================================================================
st.title("📈 주간 투자 추천 & 스마트 포트폴리오 대시보드")
today_str = datetime.now().strftime('%Y-%m-%d')
st.caption(f"📅 기준일: {today_str} | 🔍 주간 수급 및 이평선 밀집 상태 분석 패턴")

sheet_df = load_portfolio_from_sheets(GOOGLE_SHEET_URL, sheet_name="보유현황")
code_master = get_all_stock_codes()

# ----------------- 매수 / 매도 관리 입력 폼 -----------------
st.markdown("---")
tab_buy, tab_sell = st.tabs(["➕ 새 추천 주식 매수 추가", "➖ 주식 매도 기록"])

with tab_buy:
    with st.form("add_stock_form", clear_on_submit=True):
        f_col1, f_col2, f_col3, f_col4 = st.columns(4)
        with f_col1: new_name = st.text_input("종목명", placeholder="예: 삼성전자", key="b_name")
        with f_col2: new_price = st.number_input("매수가(원)", min_value=0, step=10, value=0, key="b_price")
        with f_col3: new_qty = st.number_input("보유주수(주)", min_value=1, step=1, value=1, key="b_qty")
        with f_col4: new_market = st.selectbox("시장", ["코스피", "코스닥"], key="b_market")
        submit_btn = st.form_submit_button("💼 포트폴리오에 추천주 추가")
        
        if submit_btn:
            if new_name.strip() == "" or new_price <= 0: 
                st.error("❌ 종목명과 정확한 매수 가격을 입력해 주세요.")
            else:
                with st.spinner("구글 드라이브에 기록 중..."):
                    payload = {
                        "action": "buy", 
                        "stock_name": new_name.strip(), 
                        "buy_price": int(new_price), 
                        "qty": int(new_qty), 
                        "market": new_market
                    }
                    try:
                        res = requests.post(GOOGLE_WEB_APP_URL, json=payload, timeout=10)
                        st.success(f"🎉 {new_name} 중기 포트폴리오 편입 완료!")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e: 
                        st.error(f"전송 실패: {e}")

with tab_sell:
    with st.form("sell_stock_form", clear_on_submit=True):
        s_col1, s_col2, s_col3 = st.columns(3)
        active_stocks = (
            sheet_df['종목명'].dropna().unique().tolist() 
            if not sheet_df.empty and '종목명' in sheet_df.columns 
            else []
        )
        with s_col1: sell_name = st.selectbox("매도할 종목 선택", active_stocks if active_stocks else ["보유 주식 없음"])
        
        max_sell_qty = 1000000
        current_hold_qty = 0
        if not sheet_df.empty and '종목명' in sheet_df.columns and sell_name in sheet_df['종목명'].values:
            matching_row = sheet_df[sheet_df['종목명'] == sell_name].iloc[0]
            current_hold_qty = int(pd.to_numeric(matching_row['보유주수'], errors='coerce'))
            max_sell_qty = current_hold_qty if current_hold_qty > 0 else 1000000
            
        with s_col2: sell_price = st.number_input("매도가(원)", min_value=0, step=10, value=0)
        with s_col3: sell_qty = st.number_input(f"매도 주수 (최대 {current_hold_qty}주 보유 중)", min_value=1, max_value=max_sell_qty, step=1, value=min(1, max_sell_qty))
        sell_btn = st.form_submit_button("🚨 실현 손익 확정 및 청산")
        
        if sell_btn and sell_name != "보유 주식 없음":
            if sell_price <= 0: 
                st.error("❌ 정확한 매도 가격을 입력해 주세요.")
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
                            st.success(f"🎉 {sell_name} 매도 청산 완료!")
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as e: 
                            st.error(f"전송 실패: {e}")

# ----------------- 상단 중기 보유 주식 종합 현황 -----------------
st.subheader("📋 내 주간 포트폴리오 현황 (목표가/손절가 감시)")
my_stock_list = []

if not sheet_df.empty and "종목명" in sheet_df.columns:
    p_html = "<table style='width:100%; border-collapse:collapse; text-align:left;'>"
    p_html += (
        "<tr style='border-bottom:2px solid #333; background-color:#f3f4f6; height:35px;'>"
        "<th>종목명</th><th>평균매수가</th><th>보유량</th><th>현재가</th>"
        "<th>평가손익</th><th>수익률</th><th>중기 대응 신호</th></tr>"
    )
    for _, row in sheet_df.iterrows():
        if pd.isna(row['종목명']) or str(row['종목명']).strip() == "": 
            continue
        name = str(row['종목명']).strip()
        buy_price = pd.to_numeric(row['매수가'], errors='coerce')
        qty = pd.to_numeric(row['보유주수'], errors='coerce') if '보유주수' in sheet_df.columns else 1
        if pd.isna(qty): qty = 1
        m_type = str(row
