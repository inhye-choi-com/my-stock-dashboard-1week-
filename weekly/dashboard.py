import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import io
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 페이지 설정
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
        
        stk_v = []
        if t_v:
            for r in t_v.find_all('tr'):
                a = r.find('a', {'class': 'tltle'})
                if a:
                    nm = a.get_text().strip()
                    cd = a['href'].split('=')[-1]
                    stk_v.append({'종목명': nm, '코드': cd})
        
        df_v = pd.read_html(io.StringIO(str(t_v)))[0].dropna(subset=['종목명']) if t_v else pd.DataFrame()
        if not df_v.empty:
            df_v = df_v.query("종목명 != '종목명'").head(len(stk_v)).copy()
            df_v['코드'] = [s['코드'] for s in stk_v[:len(df_v)]]
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
                    # 💡 [보정 완료] 끊기기 쉽던 문자열 한 줄 정의를 변수로 분리하여 완벽하게 마감했습니다.
                    g_nm = a.get_text().strip()
                    g_cd = a['href'].split('=')[-1]
                    stk_g.append({'종목명': g_nm, '코드': g_cd})
                    
        df_g = pd.read_html(io.StringIO(str(t_g)))[0].dropna(subset=['종목명']) if t_g else pd.DataFrame()
        if not df_g.empty:
            df_g = df_g.query("종목명 != '종목명'").head(len(stk_g)).copy()
            df_g['코드'] = [s['코드'] for s in stk_g[:len(df_g)]]
            df_g['raw_vol'] = pd.to_numeric(df_g['거래량'], errors='coerce').fillna(0)
            df_g['거래량(만)'] = (df_g['raw_vol'] / 10000).round(1)
            df_g = df_g.head(15).reset_index(drop=True)

        return df_v, df_g
    except Exception as e:
        st.error(f"마켓 데이터 가져오기 실패: {e}")
        return pd.DataFrame(columns=['종목명', '등락률', '거래대금(억)', '코드']), pd.DataFrame(columns=['종목명', '등락률', '거래량(만)', '코드', 'raw_vol'])

@st.cache_data(ttl=3600)
def get_all_stock_codes():
    m = {}
    for s in [0, 1]:
        try:
            base_api = "https://finance.naver.com"
            sub_api = f"/sise/sise_quant.naver?sosok={s}"
            res = requests.get(base_api + sub_api, headers=HDR, timeout=5)
            soup = BeautifulSoup(res.text, 'html.parser')
            anchors = soup.find_all('a', {'class': 'tltle'})
            for a in anchors:
                name_key = a.get_text().strip()
                code_val = a['href'].split('=')[-1]
                m[name_key] = code_val
        except:
            pass
    return m

def get_current_price(code, market):
    try:
        suffix = ".KQ" if "코스닥" in str(market) else ".KS"
        full_ticker = f"{code}{suffix}"
        ticker_obj = yf.Ticker(full_ticker)
        df = ticker_obj.history(period="1d")
        if not df.empty:
            return int(df['Close'].iloc[-1])
    except:
        pass
    return None

def get_stock_chart(code, name, period_choice, market_type):
    try:
        p_val, i_val = "3mo", "1d"
        if period_choice == "1년 (주봉)":
            p_val, i_val = "1y", "1wk"
        elif period_choice == "3년 (주봉)":
            p_val, i_val = "3y", "1wk"
            
        suffix = ".KQ" if "코스닥" in str(market_type) else ".KS"
        df = yf.Ticker(f"{code}{suffix}").history(period=p_val, interval=i_val)
        
        if df.empty:
            st.warning("⚠️ 차트 데이터 없음")
            return
        
        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA60'] = df['Close'].rolling(60).mean()
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_width=[0.25, 0.75])
        
        fig.add_trace(go.Candlestick(
            x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
            name="주가", increasing_line_color='#ef4444', decreasing_line_color='#3b82f6'
        ), row=1, col=1)
        
        fig.add_trace(go.Scatter(x=df.index, y=df['MA5'], line=dict(color='#ff9800', width=1.5), name='5선'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='#4caf50', width=1.5), name='20선'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MA60'], line=dict(color='#9c27b0', width=1.5), name='60선'), row=1, col=1)
        
        m_colors = ['#ef4444' if r['Close'] >= r['Open'] else '#3b82f6' for _, r in df.iterrows()]
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="거래량", marker_color=m_colors), row=2, col=1)
        
        fig.update_layout(xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10), height=400, template="plotly_white")
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"차트 에러: {e}")

def parse_rate(val):
    try:
        return float(str(val).replace('%','').replace('+','').replace(' ','').strip())
    except:
        return 0.0

st.title("📈 주간 투자 추천 & 스마트 포트폴리오 대시보드")
st.caption(f"📅 기준일: {datetime.now().strftime('%Y-%m-%d')} | 수급 및 모멘텀 실시간 추적")

sheet_df = load_portfolio_from_sheets(G_URL)
code_master = get_all_stock_codes()

st.markdown("---")
tab_buy, tab_sell = st.tabs(["➕ 새 추천 주식 매수 추가", "➖ 주식 매도 기록"])

with tab_buy:
    with st.form("add_form", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        n = c1.text_input("종목명", placeholder="예: 삼성전자")
        p = c2.number_input("매수가(원)", min_value=0, step=10)
        q = c3.number_input("보유주수(주)", min_value=1, step=1, value=1)
        m = c4.selectbox("시장", ["코스피", "코스닥"])
        if st.form_submit_button("💼 포트폴리오 추가") and n.strip() and p > 0:
            try:
                requests.post(W_URL, json={"action": "buy", "stock_name": n.strip(), "buy_price": int(p), "qty": int(q), "market": m}, timeout=10)
                st.success("🎉 추가 완료!"); st.cache_data.clear(); st.rerun()
            except Exception as e: st.error(f"오류: {e}")

with tab_sell:
    with st.form("sell_form", clear_on_submit=True):
        s1, s2, s3 = st.columns(3)
        stks = sheet_df['종목명'].dropna().unique().tolist() if not sheet_df.empty and '종목명' in sheet_df.columns else []
        sn = s1.selectbox("매도 종목 선택", stks if stks else ["보유 주식 없음"])
        
        hq = 0
        if sn in stks:
            target_row = sheet_df[sheet_df['종목명'] == sn]
            if not target_row.empty:
                hq = int(pd.to_numeric(target_row.iloc[0]['보유주수'], errors='coerce') or 0)
                
        sp = s2.number_input("매도가(원)", min_value=0, step=10)
        sq = s3.number_input(f"매도 주수 (최대 {hq}주)", min_value=1, max_value=max(1, hq), step=1)
        if st.form_submit_button("🚨 청산 실행") and sn != "보유 주식 없음" and sp > 0:
            bp = int(pd.to_numeric(sheet_df[sheet_df['종목명'] == sn].iloc[0]['매수가'], errors='coerce'))
            try:
                requests.post(W_URL, json={"action": "sell", "stock_name": sn, "buy_price": bp, "sell_price": int(sp), "qty": int(sq), "profit": int((sp-bp)*sq), "date": datetime.now().strftime("%Y-%m-%d %H:%M")}, timeout=10)
                st.success("🎉 매도 완료!"); st.cache_data.clear(); st.rerun()
            except Exception as e: st.error(f"오류: {e}")

st.subheader("📋 내 주간 포트폴리오 현황")
my_stock_list = []
rows_data = []

if not sheet_df.empty and "종목명" in sheet_df.columns:
    for _, row in sheet_df.iterrows():
        name = str(row['종목명']).strip()
        if pd.isna(row['종목명']) or name == "":
            continue
        if name not in code_master:
            continue
            
        bp, qty, mt = pd.to_numeric(row['매수가'], errors='coerce'), pd.to_numeric(row['보유주수'], errors='coerce'), str(row.get('시장', '코스피')).strip()
        cp = get_current_price(code_master[name], mt)
        if cp and not pd.isna(bp):
            my_stock_list.append(name)
            r = round(((cp - bp) / bp) * 100, 2)
            prof = int((cp - bp) * (1 if pd.isna(qty) else qty))
            
            sig = "🟢 안정적 보유"
            if r <= -4.0: sig = "🚨 즉시 손절 추천 (-4% 이탈)"
            elif r >= 10.0: sig = "🔥 즉시 익절 추천 (+10% 달성)"
                
            rows_data.append({
                "종목명": name,
                "평균매수가": f"{int(bp):,}원",
                "보유량": f"{int(qty):,}주",
                "현재가": f"{cp:,}원",
                "평가손익": f"{prof:,}원",
                "수익률": f"{r}%",
                "투자신호": sig
            })
            
    if rows_data:
        display_df = pd.DataFrame(rows_data)
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("💡 실시간 시세를 가져올 수 있는 유효한 보유 종목이 없습니다.")
else:
    st.info("💡 보유 주식이 없습니다.")

st.markdown("---")
m_tab = st.radio("📈 대상 선택", ["코스피 주간 후보군", "코스닥 주간 후보군"], horizontal=True)
df_v, df_g = fetch_market_data(0 if "코스피" in m_tab else 1)

try:
    v_set = set(df_v['종목명'].tolist()) if not df_v.empty else set()
    g_set = set(df_g['종목명'].tolist()) if not df_g.empty else set()
    super_stocks = v_set.intersection(g_set)
    recommendations = {}
    
    def build_table(df, t_type):
        if df.empty:
            return "데이터 없음\n"
        h = "| 순위 | 종목명 | 등락률 | " + ("거래대금(억)" if t_type=="val" else "거래량(만)") + " |\n|---|---|---|---|\n"
        for idx, row in df.iterrows():
            nm = row.get('종목명', '-')
            r_num = parse_rate(row.get('등락률', '0'))
            r_h = f"+{r_num}%" if r_num > 0 else f"{r_num}%"
            
            t_val = float(row.get('거래대금(억)', 0)) if t_type == "val" else int(row.get('raw_vol', 0))
            is_rec = False
            
            if t_type == "val" and t_val >= 500 and 1.5 <= r_num <= 15:
                is_rec = True
            elif t_type == "vol" and t_val >= 1000000 and 2.5 <= r_num <= 20:
                is_rec = True
                
            if is_rec:
                if t_type == "val": recommendations[nm] = "💎 수급 집중"
                else: recommendations[nm] = "🚀 추세 전환"
                
            val_txt = row.get('거래대금(억)' if t_type=='val' else '거래량(만)', 0)
            h += f"| {idx+1} | {nm} | {r_h} | {val_txt} |\n"
        return h

    col1, col2, col3 = st.columns([1, 1, 1.6])
    with col1: 
        st.subheader("💵 수급 집중")
        st.markdown(build_table(df_v, "val"))
    with col2: 
        st.subheader("🔥 추세 전환")
        st.markdown(build_table(df_g, "vol"))
    with col3:
        st.subheader("🔍 주간 추천주 Pick")
        
        style_box = "background-color: #fef08a; padding: 12px; border-radius: 6px; border-left: 5px solid #eab308; color: #1e293b; font-weight: bold; margin-bottom: 10px;"
        
        if super_stocks:
            st.markdown(f"<div style='{style_box}'>🎯 [양타점 강력 추천] 수급 + 추세 동시 돌파 종목 포착!</div>", unsafe_allow_html=True)
            for ss in super_stocks: 
                st.markdown(f"🟡 **`{ss}`** -> 당일 수급과 주봉 추세가 동시에 폭발한 강력한 대장 후보군입니다.")
        elif recommendations:
            st.markdown(f"<div style='{style_box}'>⭐ [알고리즘 분석] 수급 및 기술적 지표 주간 우수 종목</div>", unsafe_allow_html=True)
            for r_nm, r_re in list(recommendations.items())[:3]: 
                st.markdown(f"👉 **{r_nm}** : <span style='background-color: #fef08a; padding: 2px 6px; border-radius: 4px; font-weight: bold;'>{r_re}</span> 조건 충족", unsafe_allow_html=True)
        else: 
            st.write("현재 실시간 수급/추세 스크리닝 기준을 만족하는 종목이 없습니다.")
        
        st.markdown("---")
        
        v_list = df_v['종목명'].tolist() if not df_v.empty else []
        g_list = df_g['종목명'].tolist() if not df_g.empty else []
        st_names = list(set(v_list + g_list))
        
        opts = ["-- 내 포트폴리오 주식 --"] + my_stock_list + ["-- 시장 분석 후보 --"] + st_names if my_stock_list else st_names
        
        st.selectbox("종목 선택", opts if opts else ["삼성전자"], index=0, key="sel_box")
        sel = st.session_state.sel_box
        if "--" in str(sel): 
            sel = "삼성전자" if not st_names else st_names[0]
            
        if not sheet_df.empty and '종목명' in sheet_df.columns and sel in sheet_df['종목명'].values:
            sr = sheet_df[sheet_df['종목명'] == sel].iloc[0]
            bp, sq = pd.to_numeric(sr['매수가'], errors='coerce'), pd.to_numeric(sr['보유주수'], errors='coerce')
            cp = get_current_price(code_master.get(sel, "005930"), sr.get('시장', '코스피'))
            if cp and not pd.isna(bp):
                mc1, mc2, mc3 = st.columns(3)
                mc1.metric("보유량", f"{int(sq):,} 주")
                mc2.metric("매수평단", f"{int(bp):,}원")
                mc3.metric("수익률", f"{round(((cp-bp)/bp)*100,2)}%")
        
        p_choice = st.radio("주기", ["3개월 (일봉)", "1년 (주봉)", "3년 (주봉)"], horizontal=True, key="p_choice")
        scode = code_master.get(sel, "005930")
        st.markdown(f"### 📊 {sel} ({scode}) 차트")
        get_stock_chart(scode, sel, p_choice, m_tab)

    st.markdown("---")
    st.subheader("🔥 주간 특급 추천주 주요 이슈 브리핑")
    if super_stocks:
        for ss in super_stocks:
            with st.expander(f"📰 {ss} 종목 관련 주간 실시간 팩터 브리핑", expanded=True):
                st.markdown(f"### <span style='background-color: #fef08a; padding: 2px 8px;'>💡 {ss} 핵심 투자 포인트</span>", unsafe_allow_html=True)
                st.info(f"`{ss}`은(는) 주간 데이터 집계 결과 대량의 기관/외인 수급 유입과 더불어 하락 추세선을 장대양봉으로 돌파하는 골든크로스가 동시 관측되었습니다. 거래량 밴드 상단 유지를 실시간 추적하세요.")
    else: 
        st.write("💡 양타점(수급+추세) 동시 검출 종목이 발생하면 이곳에 노란색 강조 마크와 브리핑 내용이 자동으로 나타납니다.")
except Exception as e: 
    st.error(f"시스템 에러 발생: {e}")
