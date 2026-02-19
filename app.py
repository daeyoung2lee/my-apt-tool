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

# 2. 지역 코드 로드 (image_af13f0.png 규격 반영)
@st.cache_data
def load_region_codes():
    for enc in ['cp949', 'utf-8', 'euc-kr']:
        try:
            df = pd.read_csv("region_codes.csv", encoding=enc)
            # '폐지여부'가 '존재'인 데이터만 사용
            df = df[df['폐지여부'] == '존재'].copy()
            # 시도와 시군구 분리
            df = df[df['법정동명'].str.contains(' ')].copy()
            df['sido'] = df['법정동명'].apply(lambda x: x.split()[0])
            df['sigungu'] = df['법정동명'].apply(lambda x: x.split()[1])
            # 앞 5자리 코드 추출
            df['code'] = df['법정동코드'].astype(str).str[:5]
            return df[['sido', 'sigungu', 'code']].drop_duplicates()
        except:
            continue
    return pd.DataFrame()

# 3. 데이터 수집 및 상세 진단 함수
def get_molit_data(key, code, ymd):
    url = 'http://openapi.molit.go.kr/OpenAPI_ToolInstallPackage/service/rest/RTMSOBJSvc/getRTMSDataSvcAptTradeDev'
    params = {'serviceKey': key, 'LAWD_CD': code, 'DEAL_YMD': ymd}
    try:
        res = requests.get(url, params=params, timeout=15)
        # XML 응답 파싱
        root = ET.fromstring(res.content)
        header = root.find(".//header")
        res_code = header.findtext("resultCode")
        res_msg = header.findtext("resultMsg")
        
        # 서버 응답이 성공(00)이 아닌 경우 메시지 출력
        if res_code != "00":
            return pd.DataFrame(), f"서버 응답 오류: {res_msg} (코드: {res_code})"
            
        items = []
        for item in root.findall('.//item'):
            items.append({child.tag: child.text for child in item})
        return pd.DataFrame(items), "성공"
    except Exception as e:
        return pd.DataFrame(), f"통신 에러: {str(e)}"

# --- UI 구성 ---
st.set_page_config(page_title="아파트 실거래 수집 진단 도구", layout="wide")
st.title("⚖️ 아파트 실거래 데이터 수집 및 진단 시스템")

region_df = load_region_codes()

with st.sidebar:
    st.header("🔑 API 설정")
    user_key = st.text_input("인증키 (Decoding)", value=DEFAULT_API_KEY, type="password")
    
    if not region_df.empty:
        st.header("📍 지역 및 기간")
        sidos = sorted(region_df['sido'].unique())
        sel_sidos = st.multiselect("시/도", sidos, default=["인천광역시"])
        
        filtered = region_df[region_df['sido'].isin(sel_sidos)]
        sigungu_opts = sorted(filtered['sigungu'].unique())
        sel_sigungus = st.multiselect("시/군/구", sigungu_opts, default=["서구"])
        
        # 2026년 2월은 데이터 신고 시차 때문에 2025년 데이터 권장
        sel_months = st.multiselect("조회 월", ["202601", "202512", "202511"], default=["202601", "202512"])

if st.button("🚀 데이터 수집 및 원인 진단 시작"):
    if not user_key:
        st.error("API 키를 입력해주세요.")
    else:
        target_codes = region_df[region_df['sigungu'].isin(sel_sigungus)]['code'].unique()
        all_data = []
        
        for ymd in sel_months:
            for code in target_codes:
                name = region_df[region_df['code'] == code]['sigungu'].values[0]
                with st.status(f"📡 {name} ({ymd}) 데이터 확인 중...", expanded=True) as status:
                    df_tmp, msg = get_molit_data(user_key, code, ymd)
                    if not df_tmp.empty:
                        all_data.append(df_tmp)
                        status.update(label=f"✅ {name} {len(df_tmp)}건 확인", state="complete")
                    else:
                        st.info(f"ℹ️ {name} 응답: {msg}")
                        status.update(label=f"⚠️ {name} 데이터 없음", state="error")
                time.sleep(0.3)
        
        if all_data:
            final_df = pd.concat(all_data, ignore_index=True)
            st.success(f"🎊 총 {len(final_df)}건 수집 완료!")
            st.dataframe(final_df, use_container_width=True)
            
            # 예상 이익금 계산 예시 ($LaTeX$ 활용)
            # $$\text{예상 이익금} = \text{실거래가} - \text{낙찰가}$$
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                final_df.to_excel(writer, index=False)
            st.download_button("💾 엑셀 다운로드", output.getvalue(), "apt_data.xlsx")
