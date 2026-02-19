import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import io
import time

# 1. 컬럼명 변환 매핑 (데이터 가독성 향상)
KOR_COLUMNS = {
    'aptNm': '아파트명',
    'dealAmount': '거래금액(만원)',
    'excluUseAr': '전용면적(㎡)',
    'dealYear': '년',
    'dealMonth': '월',
    'dealDay': '일',
    'floor': '층',
    'umdNm': '법정동',
    'buildYear': '건축년도',
    'jibun': '지번',
    'dealingGbn': '거래유형',
    'estateAgentSggNm': '중개사소재지',
    'rgstDate': '등기일자',
    'aptDong': '단지동명',
    'sggCd': '시군구코드',
    'cdealType': '해제여부',
    'cdealDay': '해제사유발생일'
}

# 2. 보안 설정 및 인증키
try:
    DEFAULT_API_KEY = st.secrets["molit_api_key"]
except:
    DEFAULT_API_KEY = "05nRHNEp9Bf9L3tJKc0xdK7/6gNuGSoPD5/Rievn0GXUZKKwO3eHgxP2Hd8A4QdYElUhlED7+HWj+VCLHFxnag=="

# 3. 전국 지역 코드 로드 (CSV 전처리)
@st.cache_data
def load_region_codes():
    for enc in ['cp949', 'utf-8', 'euc-kr']:
        try:
            df = pd.read_csv("region_codes.csv", encoding=enc)
            df = df[df['폐지여부'] == '존재'].copy() # 존재 데이터만 사용
            df = df[df['법정동명'].str.contains(' ')].copy()
            df['sido'] = df['법정동명'].apply(lambda x: x.split()[0])
            df['sigungu'] = df['법정동명'].apply(lambda x: x.split()[1])
            df['code'] = df['법정동코드'].astype(str).str[:5] # 시군구 5자리 코드
            return df[['sido', 'sigungu', 'code']].drop_duplicates(['sido', 'sigungu'])
        except: continue
    return pd.DataFrame()

# 4. 공식 API 호출 함수 (HTTPS 적용)
def get_molit_data(key, code, ymd):
    url = 'https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev'
    params = {'serviceKey': key, 'LAWD_CD': code, 'DEAL_YMD': ymd, 'numOfRows': '1000'}
    try:
        res = requests.get(url, params=params, timeout=15)
        root = ET.fromstring(res.content)
        items = []
        for item in root.findall('.//item'):
            items.append({child.tag: child.text for child in item})
        return pd.DataFrame(items)
    except: return pd.DataFrame()

# --- 웹앱 UI 시작 ---
st.set_page_config(page_title="아파트 실거래 통합 수집기", layout="wide")
st.title("🏙️ 아파트 실거래가 통합 수집 시스템")

region_df = load_region_codes()

with st.sidebar:
    st.header("🔑 설정")
    user_key = st.text_input("인증키", value=DEFAULT_API_KEY, type="password")
    
    if not region_df.empty:
        st.header("📍 지역 및 기간 선택")
        sidos = sorted(region_df['sido'].unique())
        sel_sidos = st.multiselect("시/도 선택", sidos, default=["인천광역시"])
        
        filtered = region_df[region_df['sido'].isin(sel_sidos)]
        sigungu_opts = sorted(filtered['sigungu'].unique())
        sel_sigungus = st.multiselect("시/군/구 선택", sigungu_opts, default=["서구"])
        
        # [수정] 📅 당월 포함 최근 12개월 리스트 자동 생성 로직
        current_date = datetime.now()
        # 현재 월부터 과거 12개월치 YYYYMM 생성
        month_options = [(current_date - timedelta(days=30*i)).strftime("%Y%m") for i in range(12)]
        # 중복 제거 및 정렬 (최신순)
        month_options = sorted(list(set(month_options)), reverse=True)
        
        sel_months = st.multiselect("조회 월 선택 (당월 포함)", month_options, default=[month_options[0], month_options[1]])

if st.button("🚀 데이터 수집 시작"):
    if not user_key:
        st.error("인증키를 입력해주세요.")
    else:
        target_codes = region_df[(region_df['sido'].isin(sel_sidos)) & (region_df['sigungu'].isin(sel_sigungus))]['code'].unique()
        all_data = []
        for ymd in sel_months:
            for code in target_codes:
                name = region_df[region_df['code'] == code]['sigungu'].values[0]
                with st.spinner(f"📡 {name} ({ymd}) 데이터 수집 중..."):
                    df_tmp = get_molit_data(user_key, code, ymd)
                    if not df_tmp.empty: all_data.append(df_tmp)
                time.sleep(0.3)
        
        if all_data:
            final_df = pd.concat(all_data, ignore_index=True)
            
            # 한글 컬럼명 변환 및 전처리
            final_df = final_df.rename(columns=KOR_COLUMNS)
            main_cols = ['법정동', '아파트명', '거래금액(만원)', '전용면적(㎡)', '층', '년', '월', '일', '건축년도']
            other_cols = [c for c in final_df.columns if c not in main_cols]
            final_df = final_df[main_cols + other_cols]
            
            if '거래금액(만원)' in final_df.columns:
                final_df['거래금액(만원)'] = final_df['거래금액(만원)'].str.replace(',', '').astype(int)

            st.success(f"✅ 총 {len(final_df)}건의 데이터를 수집했습니다.")
            st.dataframe(final_df, use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                final_df.to_excel(writer, index=False)
            st.download_button("💾 한글화 엑셀 다운로드", output.getvalue(), f"apt_data_{datetime.now().strftime('%Y%m%d')}.xlsx")
        else:
            st.warning("수집된 데이터가 없습니다. 당월(2월) 데이터는 아직 신고 전일 수 있으니 지난달 데이터를 확인해보세요.")
