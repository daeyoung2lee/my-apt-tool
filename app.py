import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime
import io

# ---------------------------------------------------------
# 1. 환경 설정 및 보안 (Secrets 적용)
# ---------------------------------------------------------
# Streamlit Cloud의 설정(Secrets)에 저장된 키를 가져옵니다. 
# 설정이 안 되어 있을 경우를 대비해 입력창도 남겨둡니다.
try:
    DEFAULT_API_KEY = st.secrets["molit_api_key"]
except:
    DEFAULT_API_KEY = ""

# ---------------------------------------------------------
# 2. 데이터 로드 함수 (전국 지역 코드)
# ---------------------------------------------------------
@st.cache_data # 데이터를 매번 읽지 않도록 캐싱합니다.
def load_region_codes():
    # 시군구 코드 파일 (GitHub에 같이 올릴 파일)
    # 형식: sido, sigungu, code (5자리)
    try:
        df = pd.read_csv("region_codes.csv", dtype={'code': str})
        return df
    except:
        st.error("region_codes.csv 파일을 찾을 수 없습니다.")
        return pd.DataFrame(columns=['sido', 'sigungu', 'code'])

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
    except Exception as e:
        st.error(f"API 호출 중 오류 발생: {e}")
        return pd.DataFrame()

# ---------------------------------------------------------
# 3. UI 구성
# ---------------------------------------------------------
st.set_page_config(page_title="전문가용 실거래가 수집기", layout="wide")
st.title("📊 아파트 실거래가 통합 분석기")

# 지역 데이터 로드
region_df = load_region_codes()

with st.sidebar:
    st.header("🔑 보안 및 설정")
    # Secrets에 키가 있으면 자동 입력, 없으면 수동 입력
    user_api_key = st.text_input(
        "공공데이터 API 인증키", 
        value=DEFAULT_API_KEY, 
        type="password",
        help="Streamlit Cloud 설정에 등록하면 매번 입력할 필요가 없습니다."
    )
    
    st.header("📍 지역 선택")
    if not region_df.empty:
        sido_list = region_df['sido'].unique()
        selected_sido = st.selectbox("시/도", sido_list)
        
        sigungu_list = region_df[region_df['sido'] == selected_sido]['sigungu'].unique()
        selected_sigungu = st.selectbox("시/군/구", sigungu_list)
        
        # 선택된 시군구의 5자리 코드 추출
        target_code = region_df[(region_df['sido'] == selected_sido) & 
                                (region_df['sigungu'] == selected_sigungu)]['code'].values[0]
    
    st.header("📅 기간 설정")
    date = st.date_input("조회 월", value=datetime.now())
    target_ymd = date.strftime("%Y%m")

# 메인 화면 실행 버튼
if st.button("🚀 실거래 데이터 수집 시작"):
    if not user_api_key:
        st.warning("API 키가 없습니다. 왼쪽 사이드바에 입력해주세요.")
    else:
        with st.spinner('데이터를 불러오는 중입니다...'):
            df = get_molit_data(user_api_key, target_code, target_ymd)
            
            if not df.empty:
                st.success(f"✅ {selected_sido} {selected_sigungu} - {len(df)}건 수집 완료")
                
                # 데이터 전처리 (금액 정수화 등)
                if '거래금액' in df.columns:
                    df['거래금액'] = df['거래금액'].str.replace(',', '').astype(int)
                
                st.dataframe(df, use_container_width=True)
                
                # 다운로드 섹션
                col1, col2 = st.columns(2)
                with col1:
                    csv = df.to_csv(index=False).encode('utf-8-sig')
                    st.download_button("💾 CSV 다운로드", csv, f"apt_{target_code}_{target_ymd}.csv", "text/csv")
                with col2:
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df.to_excel(writer, index=False)
                    st.download_button("📂 Excel 다운로드", output.getvalue(), f"apt_{target_code}_{target_ymd}.xlsx")
            else:
                st.error("데이터가 없습니다. 지역 코드나 API 키 등록 상태를 확인하세요.")
