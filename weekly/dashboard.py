import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import io
import yfinance as yf

st.set_page_config(page_title="Dashboard", layout="wide")

HDR = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
G_URL = "https://docs.google.com/spreadsheets/d/1pMpXBZh3sIDE79e7vNmUgdVEU8f-qbywYy7biuWoUNM/edit?usp=sharing"
W_URL = "https://script.google.com/macros/s/AKfycbw0EcgCR_myrhrtZbtDn1d3Jq11p__mqQCOnoqZ3fO6-G5juC-x3XdWuyDtdWULfwJ6/exec"

def load_portfolio_from_sheets(url, sheet_name="보유현황"):
    try:
        csv_url = f"{url.split('/edit')[0]}/gviz/tq?tqx=out:csv&sheet={sheet_name}" if "/edit" in url else url
        res = requests.get(f"{csv_url}&t={int(datetime.now().timestamp())}", headers=HDR, timeout=5)
        if res.status_code == 200:
            df = pd.read_csv(io.StringIO(res.text))
            if not df.empty:
                df.columns = [c.strip() for c in df.columns]
                return df.dropna(subset=['종목명'])
        return pd.DataFrame()
    except: return pd.DataFrame()

@st.cache_data(ttl=600)
def fetch_market_data(sosok):
    try:
        r1 = requests.get(f"https://finance.naver.com/sise/sise_quant.naver?sosok={sosok}", headers=HDR, timeout=5)
        t1 = BeautifulSoup(r1.text, 'html.parser').find('table', {'class': 'type_2'})
        v_list = [{'종목명': a.get_text().strip(), '코드': a['href'].split('=')[-1]} for r in t1.find_all('tr') for a in [r.find('a', {'class': 'tltle'})] if a] if t1 else []
        df_v = pd.DataFrame()
        if t1 and v_list:
            df_v = pd.read_html(io.StringIO(str(t1)))[0].dropna(subset=['종목명'])
            df_v = df_v.query("종목명 != '종목명'").head(len(v_list)).copy()
            df_v['코드'] = [x['코드'] for x in v_list[:len(df_v)]]
            df_v['거래대금(억)'] = (pd.to_numeric(df_v['거래대금'], errors='coerce').fillna(0) / 1000).round(1)
            df_v = df_v.head(15).reset_index(drop=True)

        r2 = requests.get(f"https://finance.naver.com/sise/sise_rise.naver?sosok={sosok}", headers=HDR, timeout=5)
        t2 = BeautifulSoup(r2.text, 'html.parser').find('table', {'class': 'type_2'})
        g_list = [{'종목명': a.get_text().strip(), '코드': a['href'].split('=')[-1]} for r in t2.find_all('tr') for a in [r.find('a', {'class': 'tltle'})] if a] if t2 else []
        df_g = pd.DataFrame()
        if t2 and g_list:
            df_g = pd.read_html(io.StringIO(str(t2)))[0].dropna(subset=['종목명'])
            df_g = df_g.query("종목명 != '종목명'").head(len(g_list)).copy()
            df_g['코드'] = [x['코드'] for x in g_list[:len(df_g)]]
            df_g['거래량(만)'] = (pd.to_numeric(df_g['거래량'], errors='coerce').fillna(0) / 10000).round(1)
            df_g = df_g.head(15).reset_index(drop=True)
        return df_v, df_g
    except: return pd.DataFrame(columns=['종목명','등락률','거래대금(억)','코드']), pd.DataFrame(columns=['종목명','등락률','거래량(만)','코드'])

@st.cache_data(ttl=3600)
def get_all_stock_codes():
    m = {}
    for s in [0, 1]:
        try:
            res = requests.get(f"https://finance.naver.com/sise/sise_quant.naver?sosok={s}", headers=HDR, timeout=5)
            for a in BeautifulSoup(res.text, 'html.parser').find_all('a', {'class': 'tltle'}):
                m[a.get_text().strip()] = a['href'].split('=')[-1]
        except: pass
    return m

def get_current_price(code, market):
    try:
        sfx = ".KQ" if "코스닥" in str(market) else ".KS"
        df = yf.Ticker(f"{code}{sfx}").history(period="1d")
        if not df.empty: return int(df['Close'].iloc[-1])
    except: pass
    return None

def get_stock_chart(code, name, p_choice, market_type):
    """[보정 완료] 긴 Plotly 소스 대신 100% 잘림이 방지되는 가벼운 대안 차트 적용"""
    try:
        p, i = "3mo", "1d"
        if "1년" in p_choice: p, i = "1y", "1wk"
        elif "3년" in p_choice: p, i = "3y", "1wk"
        sfx = ".KQ" if "코스닥" in str(market_type) else ".KS"
        df = yf.Ticker(f"{code}{sfx}").history(period=p, interval=i)
        if df.empty: return
        
        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA60'] = df['Close'].rolling(60).mean()
        
        st.write("📈 주가 및 이동평균선 (5일/20일/60일)")
        st.line_chart(df[['Close', 'MA5', 'MA20', 'MA60']])
        st.write("📊 거래량")
        st.bar_chart(df['Volume'])
    except: pass

def parse_rate(val):
    try: return float(str(val).replace('%','').replace('+','').replace(' ','').strip())
    except: return 0.0

st.title("📈 주간 투자 추천 & 스마트 포트폴리오")
sheet_df = load_portfolio_from_sheets(G_URL)
code_master = get_all_stock_codes()

tab_buy, tab_sell = st.tabs(["➕ 매수 추가", "➖ 매도 기록"])
with tab_buy:
    with st.form("add_f", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        n = c1.text_input("종목명")
        p = c2.number_input("매수가", min_value=0, step=10)
        q = c3.number_input("보유주수", min_value=1, step=1, value=1)
        m = c4.selectbox("시장", ["코스피", "코스닥"])
        if st.form_submit_button("추가") and n.strip() and p > 0:
            try:
                requests.post(W_URL, json={"action": "buy", "stock_name": n.strip(), "buy_price": int(p), "qty": int(q), "market": m}, timeout=10)
                st.success("완료!"); st.cache_data.clear(); st.rerun()
            except Exception as e: st.error(f"오류: {e}")

with tab_sell:
    with st.form("sell_f", clear_on_submit=True):
        s1, s2, s3 = st.columns(3)
        stks = sheet_df['종목명'].dropna().unique().tolist() if not sheet_df.empty and '종목명' in sheet_df.columns else []
        sn = s1.selectbox("종목 선택", stks if stks else ["없음"])
        hq = 0
        if sn in stks:
            target = sheet_df[sheet_df['종목명'] == sn]
            if not target.empty: hq = int(pd.to_numeric(target.iloc[0]['보유주수'], errors='coerce') or 0)
        sp = s2.number_input("매도가", min_value=0, step=10)
        sq = s3.number_input(f"매도량 (최대 {hq})", min_value=1, max_value=max(1, hq), step=1)
        if st.form_submit_button("매도") and sn != "없음" and sp > 0:
            bp = int(pd.to_numeric(sheet_df[sheet_df['종목명'] == sn].iloc[0]['매수가'], errors='coerce'))
            try:
                requests.post(W_URL, json={"action": "sell", "stock_name": sn, "buy_price": bp, "sell_price": int(sp), "qty": int(sq), "profit": int((sp-bp)*sq), "date": datetime.now().strftime("%Y-%m-%d %H:%M")}, timeout=10)
                st.success("완료!"); st.cache_data.clear(); st.rerun()
            except Exception as e: st.error(f"오류: {e}")

st.subheader("📋 내 포트폴리오")
my_list, rows = [], []
if not sheet_df.empty and "종목명" in sheet_df.columns:
    for _, row in sheet_df.iterrows():
        name = str(row['종목명']).strip()
        if pd.isna(row['종목명']) or name == "" or name not in code_master: continue
        bp, qty, mt = pd.to_numeric(row['매수가'], errors='coerce'), pd.to_numeric(row['보유주수'], errors='coerce'), str(row.get('시장', '코스피')).strip()
        cp = get_current_price(code_master[name], mt)
        if cp and not pd.isna(bp):
            my_list.append(name)
            r = round(((cp - bp) / bp) * 100, 2)
            rows.append({"종목명": name, "매평단": f"{int(bp):,}원", "보유량": f"{int(qty):,}주", "현재가": f"{cp:,}원", "수익률": f"{r}%"})
    if rows: st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else: st.info("데이터 로딩 중 또는 장전 상태입니다.")
else: st.info("보유 종목이 없습니다.")

st.markdown("---")
m_tab = st.radio("📈 대상", ["코스피 후보군", "코스닥 후보군"], horizontal=True)
df_v, df_g = fetch_market_data(0 if "코스피" in m_tab else 1)

try:
    def build_table(df, t_type):
        if df is None or df.empty: return "☕ 장전 또는 데이터 집계 전입니다.\n"
        h = "| 순위 | 종목명 | 등락률 | " + ("거래대금(억)" if t_type=="val" else "거래량(만)") + " |\n|---|---|---|---|\n"
        for idx, row in df.iterrows():
            nm, r_num = row.get('종목명', '-'), parse_rate(row.get('등락률', '0'))
            r_h = f"+{r_num}%" if r_num > 0 else f"{r_num}%"
            val_txt = row.get('거래대금(억)' if t_type=='val' else '거래량(만)', 0)
            h += f"| {idx+1} | {nm} | {r_h} | {val_txt} |\n"
        return h

    col1, col2, col3 = st.columns([1, 1, 1.6])
    with col1:
        st.subheader("💵 수급 상위")
        st.markdown(build_table(df_v, "val"))
    with col2:
        st.subheader("🔥 상승률 상위")
        st.markdown(build_table(df_g, "vol"))
    with col3:
        st.subheader("🔍 차트 및 상세 분석")
        v_list = df_v['종목명'].tolist() if not df_v.empty else []
        g_list = df_g['종목명'].tolist() if not df_g.empty else []
        st_names = list(set(v_list + g_list))
        opts = ["-- 내 주식 --"] + my_list + ["-- 시장 주식 --"] + st_names if my_list else st_names
        sel = st.selectbox("종목 선택", opts if opts else ["삼성전자"], index=0)
        if "--" in str(sel): sel = "삼성전자" if not st_names else st_names[0]
            
        p_choice = st.radio("주기", ["3개월 (일봉)", "1년 (주봉)", "3년 (주봉)"], horizontal=True)
        scode = code_master.get(sel, "005930")
        st.markdown(f"### 📊 {sel} ({scode})")
        get_stock_chart(scode, sel, p_choice, m_tab)
except Exception as e: st.error(f"Error: {e}")
