import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import io
import time

# 1. 보안 설정 (Secrets)
try:
    DEFAULT_API_KEY = st.secrets["molit_api_key"]
except:
    DEFAULT_API_KEY = ""

# 2. 지역 코드 로드 및 전처리
@st.cache_data
def load_region_codes():
    encodings = ['utf-8', 'cp949', 'euc-kr']
    df = None
    for enc in encodings:
        try:
            df = pd.read_csv("region_codes.csv", encoding=enc)
            break
        except:
            continue
    if df is None: return pd.DataFrame()

    try:
        df = df[df['폐지여부'] == '존재'].copy()
        df = df[df['법정동명'].str.contains(' ')].copy()
        df['sido'] = df['법정동명'].apply(lambda x: x.split()[0])
        df['sigungu'] = df['법정동명'].apply(lambda x: " ".join(x.split()[1:]))
        df['code'] = df['법정동코드'].astype(str).str[:5]
        return df[['sido', 'sigungu', 'code']].drop_duplicates()
    except:
        return pd.DataFrame()

# 3. API 호출 함수
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

# --- UI 시작 ---
st.set_page_config(page_title="아파트 실거래 벌크 수집기", layout="wide")
st.title("📑 아파트 실거래가 다중 수집 시스템")

region_df = load_region_codes()

with st.sidebar:
    st.header("🔑 기본 설정")
    user_api_key = st.text_input("API 인증키", value=DEFAULT_API_KEY, type="password")
    
    st.divider()
    st.header("📍 지역 중복 선택")
    if not region_df.empty:
        # 시/도 선택
        all_sidos = sorted(region_df['sido'].unique())
        selected_sidos = st.multiselect("시/도 선택", all_sidos, default=["서울특별시"])
        
        # 선택된 시/도에 해당하는 시/군/구 필터링
        filtered_sigungu = region_df[region_df['sido'].isin(selected_sidos)]
        sigungu_options = sorted(filtered_sigungu['sigungu'].unique())
        
        select_all_sigungu = st.checkbox("선택한 시/도의 모든 시/군/구 포함")
        if select_all_sigungu:
            selected_sigungus = sigungu_options
            st.info(f"총 {len(selected_sigungus)}개 지역이 선택되었습니다.")
        else:
            selected_sigungus = st.multiselect("시/군/구 선택", sigungu_options)

    st.divider()
    st.header("📅 기간 선택 (최대 12개월)")
    # 최근 12개월 리스트 생성
    today = datetime.now()
    month_list = [(today - timedelta(days=30*i)).strftime("%Y%m") for i in range(12)]
    selected_months = st.multiselect("조회 월 선택", sorted(month_list, reverse=True), default=[month_list[0]])

# 메인 실행 섹션
if st.button("🚀 데이터 수집 시작 (다중 호출)"):
    if not user_api_key:
        st.error("API 키를 입력해주세요.")
    elif not selected_sigungus or not selected_months:
        st.warning("지역과 월을 최소 하나 이상 선택해주세요.")
    else:
        # 선택된 시군구 코드 리스트 추출
        target_codes = region_df[region_df['sigungu'].isin(selected_sigungus)]['code'].unique()
        
        total_steps = len(target_codes) * len(selected_months)
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        all_results = []
        current_step = 0
        
        for ymd in selected_months:
            for code in target_codes:
                current_step += 1
                local_name = region_df[region_df['code'] == code]['sigungu'].values[0]
                status_text.text(f"⏳ 수집 중 ({current_step}/{total_steps}): {local_name} ({ymd})")
                
                df_temp = get_molit_data(user_api_key, code, ymd)
                if not df_temp.empty:
                    all_results.append(df_temp)
                
                progress_bar.progress(current_step / total_steps)
                time.sleep(0.1) # API 과부하 방지용 미세 지연
        
        if all_results:
            final_df = pd.concat(all_results, ignore_index=True)
            st.success(f"✅ 총 {len(final_df)}건의 데이터 수집 완료!")
            
            # 전처리: 거래금액 숫자화
            if '거래금액' in final_df.columns:
                final_df['거래금액'] = final_df['거래금액'].str.replace(',', '').astype(int)
            
            st.dataframe(final_df, use_container_width=True)
            
            # 다운로드 버튼
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                final_df.to_excel(writer, index=False)
            st.download_button("💾 전체 데이터 엑셀 다운로드", output.getvalue(), f"apt_bulk_{datetime.now().strftime('%Y%m%d')}.xlsx")
        else:
            st.error("수집된 데이터가 없습니다. API 키나 지역 설정을 확인하세요.")
