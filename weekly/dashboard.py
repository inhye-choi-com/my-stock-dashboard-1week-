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
                    stk_v.append({'종목명': a.get_text().strip(), '코드': a['href'].split('=')[-1]})
        
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
                    stk_g.append({'종목명': a.get_text().strip(), '코드': a['href'].split('=')[-1]})
                    
        df_g = pd.read_html(io.StringIO(str(t_g)))[0].dropna(subset=['종목명']) if t_g else pd.DataFrame()
        if not df_g.empty:
            df_g = df_g.query("종목명 != '종목명'").head(len(stk_g)).copy()
            df_g['코드'] = [s['코드'] for s in stk_g[:len(df_g)]]
            
            # 💡 [바로 이 부분!] 잘려 있던 괄호와 인자들을 완전히 복구했습니다.
            df_g['raw_vol'] = pd.to_numeric(df_g['거래량'], errors='coerce').fillna(0)
            df_g['거래량(만)'] = (df_g['raw_vol'] / 10000).round(1)
            df_g = df_g.head(15).reset_index(drop=True)

        return df_v, df_g
    except Exception as e:
        st.error(f"마켓 데이터 가져오기 실패: {e}")
        return pd.DataFrame(columns=['종목명', '등락률', '거래대금(억)', '코드']), pd.DataFrame(columns=['종목명', '등락률', '거래량(만)', '코드', 'raw_vol'])
