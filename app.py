import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime
import io

# 1. 보안 설정 (Secrets에서 키 불러오기)
try:
    DEFAULT_API_KEY = st.secrets["molit_api_key"]
except:
    DEFAULT_API_KEY = ""

# 2. 지역 코드 로드 함수 (인코딩 에러 자동 해결 및 전처리)
@st.cache_data
def load_region_codes():
    encodings = ['utf-8', 'cp949', 'euc-kr'] # 여러 인코딩 시도
    df = None
    
    for enc in encodings:
        try:
            df = pd.read_csv("region_codes.csv", encoding=enc)
            break
        except:
            continue
            
    if df is None:
        st.error("region_codes.csv 파일을 읽을 수 없습니다. 인코딩을 확인해주세요.")
        return pd.DataFrame()

    try:
        # '폐지여부'가 '존재'인 것만 필터링 (image_af13f0.png 기준)
        df = df[df['폐지여부'] == '존재'].copy()
        
        # 법정동명 분리 (예: 서울특별시 종로구 청운동 -> sido: 서울특별시, sigungu: 종로구)
        # 시/도만 있는 행(예: 서울특별시)은 제외하기 위해 공백 개수로 필터링
        df = df[df['법정동명'].str.contains(' ')].copy()
        df['sido'] = df['법정동명'].apply(lambda x: x.split()[0])
        df['sigungu'] = df['법정동명'].apply(lambda x: x.split()[1])
        
        # 10자리 코드 중 앞 5자리만 추출
        df['code'] = df['법정동코드'].astype(str).str[:5]
        
        # 중복 제거 (시군구 단위로 묶기)
        return df[['sido', 'sigungu', 'code']].drop_duplicates()
    except Exception as e:
        st.error(f"데이터 전처리 중 에러 발생: {e}")
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

# --- 웹앱 UI 시작 ---
st.set_page_config(page_title="아파트 경매/실거래 매칭기", layout="wide")
st.title("⚖️ 아파트 경매 복기 & 실거래가 매칭 시스템")

region_df = load_region_codes()

with st.sidebar:
    st.header("🔑 설정")
    user_api_key = st.text_input("공공데이터 API 인증키", value=DEFAULT_API_KEY, type="password")
    
    st.header("📍 지역 및 기간")
    if not region_df.empty:
        sido_list = sorted(region_df['sido'].unique())
        selected_sido = st.selectbox("시/도 선택", sido_list)
        
        sigungu_list = sorted(region_df[region_df['sido'] == selected_sido]['sigungu'].unique())
        selected_sigungu = st.selectbox("시/군/구 선택", sigungu_list)
        
        target_code = region_df[(region_df['sido'] == selected_sido) & (region_df['sigungu'] == selected_sigungu)]['code'].values[0]
    
    target_date = st.date_input("조회 월 선택", value=datetime.now())
    target_ymd = target_date.strftime("%Y%m")

tab1, tab2 = st.tabs(["📊 실거래 데이터", "🔍 경매 데이터 매칭"])

with tab1:
    if st.button("🚀 데이터 수집 시작"):
        with st.spinner('국토부 데이터를 불러오는 중...'):
            df_real = get_molit_data(user_api_key, target_code, target_ymd)
            if not df_real.empty:
                st.session_state['real_data'] = df_real
                st.success(f"{selected_sigungu} {target_ymd} 데이터 {len(df_real)}건 수집 완료!")
                st.dataframe(df_real, use_container_width=True)
            else:
                st.error("데이터가 없습니다. API 키 등록 상태를 확인하세요.")

with tab2:
    st.info("실거래 데이터를 먼저 수집한 후, 경매 결과 파일을 업로드하세요.")
    auc_file = st.file_uploader("경매 결과 엑셀 파일(XLSX) 업로드", type=["xlsx", "csv"])
    
    if auc_file and 'real_data' in st.session_state:
        df_auc = pd.read_excel(auc_file) if auc_file.name.endswith('xlsx') else pd.read_csv(auc_file)
        st.write("### 📥 업로드된 경매 데이터 미리보기")
        st.dataframe(df_auc.head())
        
        # TODO: 아파트명과 전용면적을 기준으로 한 매칭 로직을 여기에 구현 예정
        st.warning("현재 주소 매칭 로직을 고도화 중입니다. 곧 실시간 시세 대비 수익률 분석이 가능해집니다.")
