import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import io
import time

# 1. 보안 설정 (Secrets에서 키 불러오기)
try:
    DEFAULT_API_KEY = st.secrets["molit_api_key"]
except:
    DEFAULT_API_KEY = ""

# 2. 지역 코드 로드 및 전처리 (사용자 CSV 규격 맞춤)
@st.cache_data
def load_region_codes():
    try:
        # 인코딩 에러 방지를 위해 cp949 시도 후 utf-8 시도
        try:
            df = pd.read_csv("region_codes.csv", encoding='cp949')
        except:
            df = pd.read_csv("region_codes.csv", encoding='utf-8')
            
        df = df[df['폐지여부'] == '존재'].copy()
        # 법정동명에서 시도와 시군구 추출 (예: 서울특별시 종로구)
        df['sido'] = df['법정동명'].apply(lambda x: x.split()[0] if len(x.split()) > 0 else "")
        df['sigungu'] = df['법정동명'].apply(lambda x: x.split()[1] if len(x.split()) > 1 else "")
        
        # 5자리 시군구 코드 생성 (법정동코드 앞 5자리)
        df['code'] = df['법정동코드'].astype(str).str[:5]
        
        # 시군구가 있는 데이터만 중복 제거하여 반환
        return df[df['sigungu'] != ""].drop_duplicates(['sido', 'sigungu'])
    except Exception as e:
        st.error(f"지역 코드 파일 로드 에러: {e}")
        return pd.DataFrame()

def get_molit_data(key, code, ymd):
    url = 'http://openapi.molit.go.kr/OpenAPI_ToolInstallPackage/service/rest/RTMSOBJSvc/getRTMSDataSvcAptTradeDev'
    params = {'serviceKey': key, 'LAWD_CD': code, 'DEAL_YMD': ymd}
    try:
        res = requests.get(url, params=params, timeout=10)
        root = ET.fromstring(res.content)
        items = []
        for item in root.findall('.//item'):
            items.append({child.tag: child.text for child in item})
        return pd.DataFrame(items)
    except:
        return pd.DataFrame()

# --- UI 구성 ---
st.set_page_config(page_title="아파트 실거래 벌크 수집기", layout="wide")
st.title("📑 아파트 실거래가 전국 다중 수집 시스템")

region_df = load_region_codes()

with st.sidebar:
    st.header("🔑 기본 설정")
    user_api_key = st.text_input("API 인증키", value=DEFAULT_API_KEY, type="password")
    
    st.divider()
    st.header("📍 지역 다중 선택")
    if not region_df.empty:
        # 1. 시/도 다중 선택
        all_sidos = sorted(region_df['sido'].unique())
        selected_sidos = st.multiselect("시/도 선택", all_sidos, default=["인천광역시"])
        
        # 2. 선택된 시/도 내 시/군/구 필터링
        filtered_df = region_df[region_df['sido'].isin(selected_sidos)]
        sigungu_options = sorted(filtered_df['sigungu'].unique())
        
        select_all = st.checkbox("선택한 시/도의 모든 구 포함")
        if select_all:
            selected_sigungus = sigungu_options
        else:
            selected_sigungus = st.multiselect("시/군/구 선택", sigungu_options)

    st.divider()
    st.header("📅 기간 선택 (최대 12개월)")
    # 최근 12개월 월 리스트 생성
    curr = datetime.now()
    month_list = [(curr - timedelta(days=30*i)).strftime("%Y%m") for i in range(12)]
    selected_months = st.multiselect("조회 월 선택", sorted(month_list, reverse=True), default=[month_list[1]])

# 메인 실행 버튼
if st.button("🚀 데이터 수집 시작 (다중 호출)"):
    if not user_api_key:
        st.error("API 키를 입력해주세요.")
    elif not selected_sigungus:
        st.warning("지역을 선택해주세요.")
    else:
        # 선택된 시군구에 해당하는 5자리 코드 리스트 추출
        target_df = region_df[region_df['sigungu'].isin(selected_sigungus)]
        target_codes = target_df['code'].unique()
        
        total_steps = len(target_codes) * len(selected_months)
        progress_bar = st.progress(0)
        all_results = []
        
        step = 0
        for ymd in selected_months:
            for code in target_codes:
                step += 1
                local_name = target_df[target_df['code'] == code]['sigungu'].values[0]
                st.write(f"⏳ {local_name} ({ymd}) 데이터 가져오는 중...")
                
                df_temp = get_molit_data(user_api_key, code, ymd)
                if not df_temp.empty:
                    all_results.append(df_temp)
                
                progress_bar.progress(step / total_steps)
                time.sleep(0.2) # API 과부하 방지
        
        if all_results:
            final_df = pd.concat(all_results, ignore_index=True)
            st.success(f"✅ 총 {len(final_df)}건 수집 완료!")
            st.dataframe(final_df, use_container_width=True)
            
            # 엑셀 다운로드
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                final_df.to_excel(writer, index=False)
            st.download_button("💾 전체 데이터 엑셀 다운로드", output.getvalue(), "apt_bulk_data.xlsx")
        else:
            st.error("수집된 데이터가 없습니다. API 승인 후 1~2시간이 지났는지 확인해 보세요.")
