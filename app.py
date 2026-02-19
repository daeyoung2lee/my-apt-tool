import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime
import io
import time

# 1. 보안 설정 및 인증키 (제공해주신 디코딩 키 적용)
try:
    # Streamlit Secrets에 설정한 키를 우선 사용
    DEFAULT_API_KEY = st.secrets["molit_api_key"]
except:
    # 직접 제공해주신 인증키 (디코딩 버전)
    DEFAULT_API_KEY = "05nRHNEp9Bf9L3tJKc0xdK7/6gNuGSoPD5/Rievn0GXUZKKwO3eHgxP2Hd8A4QdYElUhlED7+HWj+VCLHFxnag=="

# 2. 지역 코드 데이터 로드 (image_af13f0.png 구조 완벽 반영)
@st.cache_data
def load_region_codes():
    # 엑셀 CSV 인코딩(CP949)과 일반 UTF-8 모두 대응
    for enc in ['cp949', 'utf-8', 'euc-kr']:
        try:
            df = pd.read_csv("region_codes.csv", encoding=enc)
            # '폐지여부'가 '존재'인 데이터만 필터링
            df = df[df['폐지여부'] == '존재'].copy()
            # '법정동명'에서 시도/시군구 분리
            df = df[df['법정동명'].str.contains(' ')].copy()
            df['sido'] = df['법정동명'].apply(lambda x: x.split()[0])
            df['sigungu'] = df['법정동명'].apply(lambda x: x.split()[1])
            # 10자리 법정동코드에서 앞 5자리(시군구코드) 추출
            df['code'] = df['법정동코드'].astype(str).str[:5]
            return df[['sido', 'sigungu', 'code']].drop_duplicates()
        except:
            continue
    return pd.DataFrame()

# 3. 새로운 공식 API 호출 함수 (HTTPS 적용)
def get_molit_data(key, code, ymd):
    # image_af9677.png에 명시된 새로운 공식 End Point 사용
    url = 'https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev'
    params = {
        'serviceKey': key,
        'LAWD_CD': code,
        'DEAL_YMD': ymd,
        'numOfRows': '1000',
        'pageNo': '1'
    }
    try:
        # 공식 주소로 요청 전송 (보안 연결 적용)
        res = requests.get(url, params=params, timeout=15)
        root = ET.fromstring(res.content)
        
        header = root.find(".//header")
        res_code = header.findtext("resultCode")
        res_msg = header.findtext("resultMsg")
        
        if res_code != "00":
            return pd.DataFrame(), f"API 오류: {res_msg} (코드:{res_code})"
            
        items = []
        for item in root.findall('.//item'):
            items.append({child.tag: child.text for child in item})
        return pd.DataFrame(items), "성공"
    except Exception as e:
        return pd.DataFrame(), f"통신 에러: {str(e)}"

# --- 웹앱 화면 구성 ---
st.set_page_config(page_title="아파트 실거래 수집기", layout="wide")
st.title("🏙️ 아파트 실거래가 통합 수집 시스템")

region_df = load_region_codes()

with st.sidebar:
    st.header("🔑 API 설정")
    user_key = st.text_input("디코딩 인증키", value=DEFAULT_API_KEY, type="password")
    
    if not region_df.empty:
        st.header("📍 지역 및 기간 선택")
        sidos = sorted(region_df['sido'].unique())
        sel_sidos = st.multiselect("시/도 선택", sidos, default=["인천광역시"])
        
        filtered = region_df[region_df['sido'].isin(sel_sidos)]
        sigungu_opts = sorted(filtered['sigungu'].unique())
        sel_sigungus = st.multiselect("시/군/구 선택", sigungu_opts, default=["서구"])
        
        # 데이터가 확실히 존재하는 과거 달 위주로 선택 권장
        sel_months = st.multiselect("조회 월 선택", ["202601", "202512", "202511", "202510"], default=["202512", "202601"])

if st.button("🚀 데이터 수집 시작"):
    if not user_key:
        st.error("인증키를 입력해주세요.")
    else:
        target_codes = region_df[region_df['sigungu'].isin(sel_sigungus)]['code'].unique()
        all_results = []
        
        for ymd in sel_months:
            for code in target_codes:
                name = region_df[region_df['code'] == code]['sigungu'].values[0]
                with st.spinner(f"📡 {name} ({ymd}) 데이터 요청 중..."):
                    df_tmp, msg = get_molit_data(user_key, code, ymd)
                    if not df_tmp.empty:
                        all_results.append(df_tmp)
                        st.write(f"✅ {name} ({ymd}): {len(df_tmp)}건 확인")
                    else:
                        st.info(f"ℹ️ {name} ({ymd}): {msg}")
                time.sleep(0.5)
        
        if all_results:
            final_df = pd.concat(all_results, ignore_index=True)
            st.success(f"🎉 총 {len(final_df)}건의 실거래 데이터를 불러왔습니다!")
            st.dataframe(final_df, use_container_width=True)
            
            # 엑셀 다운로드 기능
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                final_df.to_excel(writer, index=False)
            st.download_button("💾 전체 데이터 엑셀 다운로드", output.getvalue(), "apt_real_data.xlsx")
