import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime
import io
import time

# 1. 보안 설정 및 인증키 (제공해주신 디코딩 키 적용)
# Secrets에 molit_api_key가 등록되어 있어야 합니다.
try:
    DEFAULT_API_KEY = st.secrets["molit_api_key"]
except:
    DEFAULT_API_KEY = "05nRHNEp9Bf9L3tJKc0xdK7/6gNuGSoPD5/Rievn0GXUZKKwO3eHgxP2Hd8A4QdYElUhlED7+HWj+VCLHFxnag=="

# 2. 지역 코드 로드 (image_af13f0.png 전처리 로직 강화)
@st.cache_data
def load_region_codes():
    for enc in ['cp949', 'utf-8', 'euc-kr']:
        try:
            df = pd.read_csv("region_codes.csv", encoding=enc)
            df = df[df['폐지여부'] == '존재'].copy() # 존재 데이터 필터링
            df = df[df['법정동명'].str.contains(' ')].copy()
            df['sido'] = df['법정동명'].apply(lambda x: x.split()[0])
            df['sigungu'] = df['법정동명'].apply(lambda x: x.split()[1])
            # 10자리 코드 앞 5자리만 추출
            df['code'] = df['법정동코드'].astype(str).str[:5]
            # 구 단위(5자리)로 중복을 제거하여 API 호출 횟수 최적화
            return df[['sido', 'sigungu', 'code']].drop_duplicates(['sido', 'sigungu'])
        except:
            continue
    return pd.DataFrame()

# 3. 공식 API 호출 함수 (인증키 및 HTTPS 주소 적용)
def get_molit_data(key, code, ymd):
    # image_af9677.png의 공식 주소 적용
    url = 'https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev'
    params = {'serviceKey': key, 'LAWD_CD': code, 'DEAL_YMD': ymd, 'numOfRows': '1000'}
    try:
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
        return pd.DataFrame(), f"연결 실패: {str(e)}"

# --- UI 구성 ---
st.set_page_config(page_title="아파트 실거래 수집 최종", layout="wide")
st.title("🏙️ 아파트 실거래가 통합 수집 시스템")

region_df = load_region_codes()

with st.sidebar:
    st.header("🔑 설정")
    user_key = st.text_input("인증키", value=DEFAULT_API_KEY, type="password")
    if not region_df.empty:
        sidos = sorted(region_df['sido'].unique())
        sel_sidos = st.multiselect("시/도 선택", sidos, default=["인천광역시"])
        filtered = region_df[region_df['sido'].isin(sel_sidos)]
        sigungu_opts = sorted(filtered['sigungu'].unique())
        # 인천 서구를 기본값으로 설정
        sel_sigungus = st.multiselect("시/군/구 선택", sigungu_opts, default=["서구"])
        # 과거 달 조회를 강력 권장 (202602는 현재 데이터 없음)
        month_list = ["202601", "202512", "202511", "202510"]
        sel_months = st.multiselect("조회 월 (202512 권장)", month_list, default=["202512"])

if st.button("🚀 데이터 수집 시작"):
    if not user_key:
        st.error("인증키를 입력해주세요.")
    else:
        # 시군구 명칭으로 코드 매핑
        target_codes = region_df[region_df['sigungu'].isin(sel_sigungus)]['code'].unique()
        all_data = []
        for ymd in sel_months:
            for code in target_codes:
                name = region_df[region_df['code'] == code]['sigungu'].values[0]
                with st.spinner(f"📡 {name} ({ymd}) 데이터 수집 중..."):
                    df_tmp, msg = get_molit_data(user_key, code, ymd)
                    if not df_tmp.empty:
                        all_data.append(df_tmp)
                        st.success(f"✅ {name} ({ymd}): {len(df_tmp)}건 확인")
                    else:
                        st.info(f"ℹ️ {name} ({ymd}): {msg} (데이터 0건)")
                time.sleep(0.5)
        
        if all_data:
            final_df = pd.concat(all_data, ignore_index=True)
            st.dataframe(final_df, use_container_width=True)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                final_df.to_excel(writer, index=False)
            st.download_button("💾 엑셀 다운로드", output.getvalue(), "apt_real_data.xlsx")
