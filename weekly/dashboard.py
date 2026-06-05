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

# UI 시작
st.title("📈 주간 투자 추천 & 스마트 포트폴리오 대시보드")
today_str = datetime.now().strftime('%Y-%m-%d')
st.caption(f"📅 기준일: {today_str} | 수급 분석 패턴 시스템")

sheet_df = load_portfolio_from_sheets(GOOGLE_SHEET_URL, sheet_name="보유현황")
code_master = get_all_stock_codes()

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
                st.error("❌ 정보를 올바르게 입력해 주세요.")
            else:
                with st.spinner("기록 중..."):
                    payload = {"action": "buy", "stock_name": new_name.strip(), "buy_price": int(new_price), "qty": int(new_qty), "market": new_market}
                    try:
                        requests.post(GOOGLE_WEB_APP_URL, json=payload, timeout=10)
                        st.success("🎉 중기 포트폴리오 편입 완료!")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e: st.error(f"실패: {e}")

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
        with s_col3: sell_qty = st.number_input(f"매도 주수 (최대 {current_hold_qty}주)", min_value=1, max_value=max_sell_qty, step=1, value=min(1, max_sell_qty))
        sell_btn = st.form_submit_button("🚨 실현 손익 확정 및 청산")
        
        if sell_btn and sell_name != "보유 주식 없음":
            if sell_price <= 0: st.error("❌ 매도가를 입력하세요.")
            else:
                matching = sheet_df[sheet_df['종목명'] == sell_name]
                if not matching.empty:
                    buy_price_avg = int(pd.to_numeric(matching.iloc[0]['매수가'], errors='coerce'))
                    profit_calculated = int((sell_price - buy_price_avg) * int(sell_qty))
                    with st.spinner("처리 중..."):
                        payload = {"action": "sell", "stock_name": sell_name, "buy_price": int(buy_price_avg), "sell_price": int(sell_price), "qty": int(sell_qty), "profit": int(profit_calculated), "date": datetime.now().strftime("%Y-%m-%d %H:%M")}
                        try:
                            requests.post(GOOGLE_WEB_APP_URL, json=payload, timeout=10)
                            st.success("🎉 매도 청산 완료!")
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as e: st.error(f"실패: {e}")

st.subheader("📋 내 주간 포트폴리오 현황 (목표가/손절가 감시)")
my_stock_list = []

if not sheet_df.empty and "종목명" in sheet_df.columns:
    p_html = "<table style='width:100%; border-collapse:collapse; text-align:left;'>"
    p_html += "<tr style='border-bottom:2px solid #333; background-color:#f3f4f6; height:35px;'><th>종목명</th><th>평균매수가</th><th>보유량</th><th>현재가</th><th>평가손익</th><th>수익률</th><th>중기 대응 신호</th></tr>"
    for _, row in sheet_df.iterrows():
        if pd.isna(row['종목명']) or str(row['종목명']).strip() == "": continue
        name = str(row['종목명']).strip()
        buy_price = pd.to_numeric(row['매수가'], errors='coerce')
        qty = pd.to_numeric(row['보유주수'], errors='coerce') if '보유주수' in sheet_df.columns else 1
        if pd.isna(qty): qty = 1
        
        # 🔥 [완벽 복구 및 다이어트 완료] 에러 나던 괄호 라인을 완전히 마감 및 정리함
        m_type = str(row['시장']).strip() if '시장' in sheet_df.columns else "코스피"
        
        if name in code_master and not pd.isna(buy_price):
            code = code_master[name]
            current_price = get_current_price(code, m_type)
            my_stock_list.append(name)
            if current_price:
                profit_rate = round(((current_price - buy_price) / buy_price) * 100, 2)
                total_profit = int((current_price - buy_price) * qty)
                row_style = "class='portfolio-danger'" if profit_rate <= -5.0 else ("class='portfolio-success'" if profit_rate >= 12.0 else "")
                signal = "🚨 리스크 관리 (-5%)" if profit_rate <= -5.0 else ("🎉 목표 달성 (+12%)" if profit_rate >= 12.0 else "➖ 주간 보유")
                rate_html = f"<span class='up-color'>+{profit_rate}%</span>" if profit_rate > 0 else (f"<span class='down-color'>{profit_rate}%</span>" if profit_rate < 0 else "<span>0.0%</span>")
                profit_html = f"<span class='up-color'>{total_profit:,}원</span>" if total_profit > 0 else (f"<span class='down-color'>{total_profit:,}원</span>" if total_profit < 0 else "<span>0원</span>")
                p_html += f"<tr {row_style} style='border-bottom:1px solid #ddd; height:40px;'><td><b>{name}</b></td><td>{int(buy_price):,}원</td><td>{int(qty):,}주</td><td>{current_price:,}원</td><td>{profit_html}</td><td>{rate_html}</td><td><b>{signal}</b></td></tr>"
    p_html += "</table>"
    st.markdown(p_html, unsafe_allow_html=True)
else:
    st.info("💡 보유 현황 데이터가 비어있습니다.")

st.markdown("---")
market_tab = st.radio("📈 대상을 선택하세요", ["코스피 주간 후보군", "코스닥 주간 후보군"], horizontal=True)
sosok_code = 0 if "코스피" in market_tab else 1

try:
    df_v, df_g = fetch_market_data(sosok_code)
    recommendations = {}
    
    def build_custom_html_table(df, table_type):
        if df.empty: return "<p style='color:gray;'>데이터가 없습니다.</p>"
        html = "<table style='width:100%; border-collapse:collapse;'>"
        html += "<tr style='border-bottom:2px solid #ddd; text-align:left;'><th>순위</th><th>종목명</th><th>등락률</th><th>" + ("거래대금(억)" if table_type=="value" else "거래량(만)") + "</th></tr>"
        for idx, row in df.iterrows():
            rate_num = parse_rate(row.get('등락률', '0'))
            rate_html = f"<span class='up-color'>▲ +{rate_num}%</span>" if rate_num > 0 else (f"<span class='down-color'>▼ {rate_num}%</span>" if rate_num < 0 else "<span class='flat-color'>0.0%</span>")
            target_val = float(row.get('거래대금(억)', 0)) if table_type == "value" else int(row.get('raw_vol', 0))
            is_recommended = (table_type == "value" and target_val >= 800 and 2 <= rate_num <= 12) or (table_type == "volume" and target_val >= 1500000 and 4 <= rate_num <= 15)
            if is_recommended and '종목명' in row: 
                recommendations[row['종목명']] = "💎 수급 집중 우상향" if table_type=="value" else "🚀 거래량 밀집 바닥권 탈출"
            row_class = "class='recommend-row'" if is_recommended else ""
            display_col = row.get('거래대금(억)' if table_type=='value' else '거래량(만)', 0)
            html += f"<tr {row_class} style='border-bottom:1px solid #eee; height:35px;'><td>{idx+1}</td><td>{row.get('종목명', '-')}</td><td>{rate_html}</td><td>{display_col}</td></tr>"
        return html + "</table>"

    col1, col2, col3 = st.columns([1, 1, 1.6])
    with col1:
        st.subheader("💵 수급 집중")
        st.markdown(build_custom_html_table(df_v.reset_index(drop=True), "value"), unsafe_allow_html=True)
    with col2:
        st.subheader("🔥 추세 전환")
        st.markdown(build_custom_html_table(df_g.reset_index(drop=True), "volume"), unsafe_allow_html=True)
    with col3:
        st.subheader("🔍 주간 추천주 Pick & 분석")
        if recommendations:
            st.markdown("##### 💡 시스템 자동 추천:")
            for r_name, r_reason in list(recommendations.items())[:3]: st.write(f"- **{r_name}**: {r_reason}")
        else: st.write("기준 충족 종목이 없습니다.")
        st.markdown("---")
        
        stock_names = []
        if not df_v.empty: stock_names += df_v['종목명'].tolist()
        if not df_g.empty: stock_names += df_g['종목명'].tolist()
        stock_names = list(set(stock_names))
        select_options = ["-- 내 포트폴리오 주식 --"] + my_stock_list + ["-- 시장 추천/분석 후보 --"] + stock_names if my_stock_list else stock_names
        
        st.selectbox("종목 선택", select_options if select_options else ["삼성전자"], index=0, key="stock_selector_main")
        sel_name = st.session_state.stock_selector_main
        if "--" in str(sel_name): sel_name = "삼성전자" if not stock_names else stock_names[0]
            
        if not sheet_df.empty and '종목명' in sheet_df.columns and sel_name in sheet_df['종목명'].values:
            stock_row = sheet_df[sheet_df['종목명'] == sel_name].iloc[0]
            b_p = pd.to_numeric(stock_row['매수가'], errors='coerce')
            s_q = pd.to_numeric(stock_row['보유주수'], errors='coerce')
            c_p = get_current_price(code_master.get(sel_name, "005930"), stock_row.get('시장', '코스피'))
            if c_p and not pd.isna(b_p):
                m_col1, m_col2, m_col3 = st.columns(3)
                with m_col1: st.metric(label="보유량", value=f"{int(s_q):,} 주")
                with m_col2: st.metric(label="매수 평단가", value=f"{b_p:,}원")
                with m_col3: st.metric(label="수익률", value=f"{round(((c_p - b_p)/b_p)*100,2)}%")
        
        period_choice = st.radio("차트 주기", ["3개월 (일봉)", "1년 (주봉)", "3년 (주봉)"], horizontal=True, key="chart_period_choice")
        selected_code = code_master.get(sel_name, "005930")
        st.markdown(f"### 📊 {sel_name} ({selected_code}) 차트")
        get_stock_chart(selected_code, sel_name, period_choice, market_tab)
except Exception as e: 
    st.error(f"오류: {e}")
