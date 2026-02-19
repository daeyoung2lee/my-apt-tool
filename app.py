import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime
import io
import time

# 1. 보안 설정 (Secrets)
try:
    DEFAULT_API_KEY = st.secrets["molit_api_key"]
except:
    DEFAULT_API_KEY = "05nRHNEp9Bf9L3tJKc0xdK7/6gNuGSoPD5/Rievn0GXUZKKwO3eHgxP2Hd8A4QdYElUhlED7+HWj+VCLHFxnag=="

# 2. 지역 코드 로드 (중복 제거 및 정확한 매핑)
@st.cache_data
def load_region_codes():
    for enc in ['cp949', 'utf-8', 'euc-kr']:
        try:
            df = pd.read_csv("region_codes.csv", encoding=enc)
            df = df[df['폐지여부'] == '존재'].copy()
            df = df[df['법정동명'].str.contains(' ')].copy()
            df['sido'] = df['법정동명'].apply(lambda x: x.split()[0])
            df['sigungu'] = df['법정동명'].apply(lambda x: x.split()[1])
            df['code'] = df['법정동코드'].astype(str).str[:5]
            # 시도와 시군구를 합쳐서 유일한 값을 만듦 (예: 인천광역시 서구)
            return df[['sido', 'sigungu', 'code']].drop_duplicates(['sido', 'sigungu'])
        except:
            continue
    return pd.DataFrame()

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
    except:
        return pd.DataFrame()

# --- UI 시작 ---
st.set_page_config(page_title="아파트 실거래 수집 최종수정", layout="wide")
st.title("🏙️ 아파트 실거래가 통합 수집 시스템")

region_df = load_region_codes()

with st.sidebar:
    st.header("🔑 설정")
    user_key = st.text_input("인증키", value=DEFAULT_API_KEY, type="password")
    
    if not region_df.empty:
        st.header("📍 지역 및 기간")
        sidos = sorted(region_df['sido'].unique())
        sel_sidos = st.multiselect("시/도 선택", sidos, default=["인천광역시"])
        
        # 선택된 시도에 정확히 매칭되는 시군구만 필터링
        filtered = region_df[region_df['sido'].isin(sel_sidos)]
        sigungu_opts = sorted(filtered['sigungu'].unique())
        sel_sigungus = st.multiselect("시/군/구 선택", sigungu_opts, default=["서구"])
        
        # 날짜 선택
        sel_months = st.multiselect("조회 월", ["202601", "202512", "202511"], default=["202512"])

if st.button("🚀 데이터 수집 시작"):
    if not user_key:
        st.error("인증키를 입력해주세요.")
    else:
        # 선택된 시도와 시군구의 조합으로 정확한 5자리 코드만 추출
        target_codes = region_df[
            (region_df['sido'].isin(sel_sidos)) & 
            (region_df['sigungu'].isin(sel_sigungus))
        ]['code'].unique()
        
        all_data = []
        for ymd in sel_months:
            for code in target_codes:
                # 해당 코드의 시군구 이름 찾기
                name = region_df[region_df['code'] == code]['sigungu'].values[0]
                with st.spinner(f"📡 {name} ({ymd}) 조회 중..."):
                    df_tmp = get_molit_data(user_key, code, ymd)
                    if not df_tmp.empty:
                        all_data.append(df_tmp)
                        st.success(f"✅ {name} ({ymd}): {len(df_tmp)}건 확인!")
                    else:
                        st.info(f"ℹ️ {name} ({ymd}): 데이터가 없습니다.")
                time.sleep(0.5)
        
        if all_data:
            final_df = pd.concat(all_data, ignore_index=True)
            st.dataframe(final_df, use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                final_df.to_excel(writer, index=False)
            st.download_button("💾 엑셀 다운로드", output.getvalue(), "apt_real_data.xlsx")
