import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime
import io

# 1. 보안 설정 (Secrets)
try:
    DEFAULT_API_KEY = st.secrets["molit_api_key"]
except:
    DEFAULT_API_KEY = ""

# 2. 전국 지역 코드 로드 및 전처리 (업로드하신 CSV 규격에 맞춤)
@st.cache_data
def load_region_codes():
    try:
        # 업로드하신 파일의 컬럼명에 맞춰 로드
        df = pd.read_csv("region_codes.csv", encoding='utf-8')
        # '폐지여부'가 '존재'인 것만 필터링
        df = df[df['폐지여부'] == '존재'].copy()
        
        # 법정동명 분리 (예: 서울특별시 종로구 -> sido: 서울특별시, sigungu: 종로구)
        df['sido'] = df['법정동명'].apply(lambda x: x.split()[0] if len(x.split()) > 0 else "")
        df['sigungu'] = df['법정동명'].apply(lambda x: x.split()[1] if len(x.split()) > 1 else "")
        
        # 10자리 코드 중 앞 5자리만 추출 (국토부 API 규격)
        df['code'] = df['법정동코드'].astype(str).str[:5]
        
        # 시군구가 있는 데이터만 남기기
        return df[df['sigungu'] != ""]
    except Exception as e:
        st.error(f"CSV 로드 에러: {e}")
        return pd.DataFrame()

def get_molit_data(key, code, ymd):
    url = 'http://openapi.molit.go.kr/OpenAPI_ToolInstallPackage/service/rest/RTMSOBJSvc/getRTMSDataSvcAptTradeDev'
    params = {'serviceKey': key, 'LAWD_CD': code, 'DEAL_YMD': ymd}
    try:
        res = requests.get(url, params=params)
        root = ET.fromstring(res.content)
        items = []
        for item in root.findall('.//item'):
            items.append({child.tag: child.text for child in item})
        return pd.DataFrame(items)
    except:
        return pd.DataFrame()

# UI 구성
st.set_page_config(page_title="경매 복기 & 실거래가 분석기", layout="wide")
st.title("⚖️ 아파트 경매 복기 & 실거래가 매칭기")

region_df = load_region_codes()

# 사이드바 설정
with st.sidebar:
    st.header("🔑 보안 및 설정")
    user_api_key = st.text_input("API 키", value=DEFAULT_API_KEY, type="password")
    
    st.header("📍 지역 및 기간")
    if not region_df.empty:
        selected_sido = st.selectbox("시/도", region_df['sido'].unique())
        sigungu_list = region_df[region_df['sido'] == selected_sido]['sigungu'].unique()
        selected_sigungu = st.selectbox("시/군/구", sigungu_list)
        target_code = region_df[(region_df['sido'] == selected_sido) & (region_df['sigungu'] == selected_sigungu)]['code'].values[0]
    
    target_date = st.date_input("조회 월", value=datetime.now())
    target_ymd = target_date.strftime("%Y%m")

# 메인 섹션 - 2개의 탭으로 구성
tab1, tab2 = st.tabs(["📊 실거래 데이터 수집", "🔍 경매 데이터 매칭"])

with tab1:
    if st.button("🚀 실거래가 수집"):
        df_real = get_molit_data(user_api_key, target_code, target_ymd)
        if not df_real.empty:
            st.session_state['real_data'] = df_real # 데이터 공유를 위해 세션 저장
            st.success(f"{len(df_real)}건 수집 완료")
            st.dataframe(df_real)
        else:
            st.error("데이터를 불러오지 못했습니다.")

with tab2:
    st.header("📥 경매 낙찰 결과 업로드")
    uploaded_auction = st.file_uploader("경매 결과 엑셀(CSV)을 올려주세요", type=["csv", "xlsx"])
    
    if uploaded_auction and 'real_data' in st.session_state:
        # 경매 데이터 읽기
        auc_df = pd.read_excel(uploaded_auction) if uploaded_auction.name.endswith('xlsx') else pd.read_csv(uploaded_auction)
        st.write("--- 업로드된 경매 데이터 ---")
        st.dataframe(auc_df.head())
        
        # 간단한 매칭 예시 (아파트명 기준)
        st.subheader("💡 분석 리포트 (Beta)")
        st.info("실거래 데이터와 아파트명을 대조하여 안전마진을 계산합니다.")
        # 여기에 추후 주소 매칭 로직을 추가할 수 있습니다.
