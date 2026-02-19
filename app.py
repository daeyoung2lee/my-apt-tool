import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime
import io
import time

# 1. 보안 설정 및 인증키 (Secrets 우선, 없을 시 직접 입력)
try:
    DEFAULT_API_KEY = st.secrets["molit_api_key"]
except:
    # 사용자께서 제공해주신 디코딩 인증키 직접 입력
    DEFAULT_API_KEY = "05nRHNEp9Bf9L3tJKc0xdK7/6gNuGSoPD5/Rievn0GXUZKKwO3eHgxP2Hd8A4QdYElUhlED7+HWj+VCLHFxnag=="

# 2. 지역 코드 데이터 로드 (image_af13f0.png 구조 반영)
@st.cache_data
def load_region_codes():
    for enc in ['cp949', 'utf-8', 'euc-kr']:
        try:
            df = pd.read_csv("region_codes.csv", encoding=enc)
            df = df[df['폐지여부'] == '존재'].copy() # 존재 데이터만 필터링
            df = df[df['법정동명'].str.contains(' ')].copy()
            df['sido'] = df['법정동명'].apply(lambda x: x.split()[0])
            df['sigungu'] = df['법정동명'].apply(lambda x: x.split()[1])
            df['code'] = df['법정동코드'].astype(str).str[:5] # 시군구 5자리 추출
            return df[['sido', 'sigungu', 'code']].drop_duplicates()
        except:
            continue
    return pd.DataFrame()

# 3. 공식 API 호출 함수 (HTTPS 엔드포인트 적용)
def get_molit_data(key, code, ymd):
    # 공식 End Point로 주소 변경
    url = 'https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev'
    params = {
        'serviceKey': key,
        'LAWD_CD': code,
        'DEAL_YMD': ymd,
        'numOfRows': '1000', # 한 번에 가져올 데이터 양 설정
        'pageNo': '1'
    }
    try:
        # verify=False는 SSL 보안 인증 관련 오류 발생 시 해결책입니다.
        res = requests.get(url, params=params, timeout=15, verify=True)
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

# --- 웹앱 UI 구성 ---
st.set_page_config(page_title="아파트 실거래 수집기 최종본", layout="wide")
st.title("🏙️ 아파트 실거래가 통합 수집 시스템")

region_df = load_region_codes()

with st.sidebar:
    st.header("🔑 설정")
    user_key = st.text_input("디코딩 인증키", value=DEFAULT_API_KEY, type="password")
    
    if not region_df.empty:
        st.header("📍 지역 및 기간 선택")
        sidos = sorted(region_df['sido'].unique())
        sel_sidos = st.multiselect("시/도", sidos, default=["인천광역시"])
        
        filtered = region_df[region_df['sido'].isin(sel_sidos)]
        sigungu_opts = sorted(filtered['sigungu'].unique())
        sel_sigungus = st.multiselect("시/군/구", sigungu_opts, default=["서구"])
        
        # 2026년 2월은 신고 시차로 인해 데이터가 거의 없음. 2025년 위주 테스트 권장
        sel_months = st.multiselect("조회 월", ["202601", "202512", "202511", "202510"], default=["202512", "202601"])

if st.button("🚀 데이터 수집 시작"):
    if not user_key:
        st.error("인증키를 입력해주세요.")
    else:
        target_codes = region_df[region_df['sigungu'].isin(sel_sigungus)]['code'].unique()
        all_data = []
        
        for ymd in sel_months:
            for code in target_codes:
                name = region_df[region_df['code'] == code]['sigungu'].values[0]
                with st.spinner(f"📡 {name} ({ymd}) 데이터 요청 중..."):
                    df_tmp, msg = get_molit_data(user_key, code, ymd)
                    if not df_tmp.empty:
                        all_data.append(df_tmp)
                        st.write(f"✅ {name} ({ymd}): {len(df_tmp)}건 확인")
                    else:
                        st.info(f"ℹ️ {name} ({ymd}): {msg}")
                time.sleep(0.5) # API 속도 제한 준수
        
        if all_data:
            final_df = pd.concat(all_data, ignore_index=True)
            st.success(f"🎉 총 {len(final_df)}건의 실거래 데이터를 불러왔습니다!")
            st.dataframe(final_df, use_container_width=True)
            
            # 파일 다운로드 기능
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                final_df.to_excel(writer, index=False)
            st.download_button("💾 전체 데이터 엑셀 다운로드", output.getvalue(), "apt_real_data.xlsx")
