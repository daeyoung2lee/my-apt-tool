import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import io
import time

# 1. 컬럼 한글화 매핑 (경매용)
AUC_KOR_COLUMNS = {
    'aptNm': '아파트명',
    'aucAmt': '매각금액(낙찰가)',
    'evlAmt': '감정가',
    'lowAmt': '최저입찰가',
    'excluUseAr': '전용면적(㎡)',
    'dealYear': '매각년',
    'dealMonth': '매각월',
    'dealDay': '매각일',
    'umdNm': '법정동',
    'floor': '층',
    'snum': '사건번호'
}

# 2. 보안 설정 및 인증키
try:
    DEFAULT_API_KEY = st.secrets["molit_api_key"]
except:
    DEFAULT_API_KEY = "05nRHNEp9Bf9L3tJKc0xdK7/6gNuGSoPD5/Rievn0GXUZKKwO3eHgxP2Hd8A4QdYElUhlED7+HWj+VCLHFxnag=="

# 3. 지역 코드 로드 (image_af13f0.png 구조 반영)
@st.cache_data
def load_region_codes():
    for enc in ['cp949', 'utf-8', 'euc-kr']:
        try:
            df = pd.read_csv("region_codes.csv", encoding=enc)
            df = df[df['폐지여부'] == '존재'].copy()
            df = df[df['법정동명'].str.contains(' ')].copy()
            df['sido'] = df['법정동명'].apply(lambda x: x.split()[0])
            df['sigungu'] = df['법정동명'].apply(lambda x: x.split()[1])
            df['code'] = df['법정동코드'].astype(str).str[:5] # 5자리 추출
            return df[['sido', 'sigungu', 'code']].drop_duplicates(['sido', 'sigungu'])
        except: continue
    return pd.DataFrame()

# 4. 실거래가 API 호출 (국토부)
def get_molit_data(key, code, ymd):
    url = 'https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev'
    params = {'serviceKey': key, 'LAWD_CD': code, 'DEAL_YMD': ymd, 'numOfRows': '1000'}
    try:
        res = requests.get(url, params=params, timeout=15)
        root = ET.fromstring(res.content)
        items = [{child.tag: child.text for child in item} for item in root.findall('.//item')]
        return pd.DataFrame(items)
    except: return pd.DataFrame()

# 5. 경매 결과 API 호출 (대법원 - 신청 필요)
def get_auction_data(key, code, ymd):
    # 대법원 경매사건정보 API 엔드포인트 (신청 후 확인 필요)
    url = 'https://apis.data.go.kr/1505864/getAuclist/getAptAuclist' 
    params = {'serviceKey': key, 'LAWD_CD': code, 'DEAL_YMD': ymd, 'numOfRows': '1000'}
    try:
        res = requests.get(url, params=params, timeout=15)
        root = ET.fromstring(res.content)
        items = [{child.tag: child.text for child in item} for item in root.findall('.//item')]
        return pd.DataFrame(items)
    except: return pd.DataFrame()

# --- UI 시작 ---
st.set_page_config(page_title="황혼의라디오 - 투자분석기", layout="wide")
st.title("🏙️ 아파트 실거래가 & 경매 통합 분석 시스템")

region_df = load_region_codes()

with st.sidebar:
    st.header("⚙️ 설정")
    user_key = st.text_input("인증키", value=DEFAULT_API_KEY, type="password")
    
    if not region_df.empty:
        sidos = sorted(region_df['sido'].unique())
        sel_sidos = st.multiselect("시/도 선택", sidos, default=["인천광역시"])
        filtered = region_df[region_df['sido'].isin(sel_sidos)]
        sigungu_opts = sorted(filtered['sigungu'].unique())
        sel_sigungus = st.multiselect("시/군/구 선택", sigungu_opts, default=["서구"])
        
        # 최근 12개월 생성
        curr = datetime.now()
        month_opts = [(curr - timedelta(days=30*i)).strftime("%Y%m") for i in range(12)]
        sel_months = st.multiselect("조회 월 선택", sorted(list(set(month_opts)), reverse=True), default=[month_opts[1]])

# 탭 구성
tab1, tab2 = st.tabs(["📊 아파트 실거래가", "⚖️ 대법원 경매결과"])

with tab1:
    if st.button("🚀 실거래가 수집 시작"):
        codes = region_df[(region_df['sido'].isin(sel_sidos)) & (region_df['sigungu'].isin(sel_sigungus))]['code'].unique()
        all_real = []
        for ymd in sel_months:
            for code in codes:
                df = get_molit_data(user_key, code, ymd)
                if not df.empty: all_real.append(df)
        if all_real:
            final_real = pd.concat(all_real, ignore_index=True)
            st.session_state['real_data'] = final_real # 세션 저장
            st.dataframe(final_real, use_container_width=True)
        else: st.warning("데이터가 없습니다.")

with tab2:
    st.info("💡 대법원 API 신청 후 활성화됩니다. 실거래가 수집과 동일한 방식으로 작동합니다.")
    if st.button("⚖️ 경매 결과 수집 시작"):
        codes = region_df[(region_df['sido'].isin(sel_sidos)) & (region_df['sigungu'].isin(sel_sigungus))]['code'].unique()
        all_auc = []
        for ymd in sel_months:
            for code in codes:
                df = get_auction_data(user_key, code, ymd)
                if not df.empty: all_auc.append(df)
        if all_auc:
            final_auc = pd.concat(all_auc, ignore_index=True)
            final_auc = final_auc.rename(columns=AUC_KOR_COLUMNS)
            st.session_state['auc_data'] = final_auc
            st.dataframe(final_auc, use_container_width=True)
        else: st.error("경매 API가 아직 미승인 상태이거나 해당 조건의 낙찰 데이터가 없습니다.")
