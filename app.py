import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import io
import time

# 1. 보안 설정 (Secrets에서 키 불러오기)
try:
    # image_af967b.png의 설정값 확인
    DEFAULT_API_KEY = st.secrets["molit_api_key"]
except:
    DEFAULT_API_KEY = ""

# 2. 지역 코드 로드 (image_af13f0.png 규격 반영)
@st.cache_data
def load_region_codes():
    for enc in ['cp949', 'utf-8', 'euc-kr']:
        try:
            df = pd.read_csv("region_codes.csv", encoding=enc)
            # 법정동명에서 시도/시군구 분리 로직 정교화
            df = df[df['폐지여부'] == '존재'].copy()
            df = df[df['법정동명'].str.contains(' ')].copy()
            df['sido'] = df['법정동명'].apply(lambda x: x.split()[0])
            df['sigungu'] = df['법정동명'].apply(lambda x: x.split()[1])
            # 5자리 코드 생성 (앞 5글자)
            df['code'] = df['법정동코드'].astype(str).str[:5]
            return df[['sido', 'sigungu', 'code']].drop_duplicates()
        except:
            continue
    return pd.DataFrame()

# 3. 데이터 수집 및 진단 함수
def get_molit_data(key, code, ymd):
    url = 'http://openapi.molit.go.kr/OpenAPI_ToolInstallPackage/service/rest/RTMSOBJSvc/getRTMSDataSvcAptTradeDev'
    params = {'serviceKey': key, 'LAWD_CD': code, 'DEAL_YMD': ymd}
    try:
        res = requests.get(url, params=params, timeout=15)
        
        # 진단 모드: API 응답 결과 파싱
        root = ET.fromstring(res.content)
        header = root.find(".//header")
        result_code = header.findtext("resultCode")
        result_msg = header.findtext("resultMsg")
        
        # 에러 발생 시 알림
        if result_code != "00":
            st.error(f"⚠️ API 서버 응답 오류: {result_msg} (코드: {result_code})")
            return pd.DataFrame(), result_msg
            
        items = []
        for item in root.findall('.//item'):
            items.append({child.tag: child.text for child in item})
            
        return pd.DataFrame(items), "정상"
    except Exception as e:
        return pd.DataFrame(), str(e)

# --- UI 구성 ---
st.set_page_config(page_title="아파트 실거래 벌크 수집기", layout="wide")
st.title("📑 전국 아파트 실거래 데이터 수집 시스템")

region_df = load_region_codes()

with st.sidebar:
    st.header("🔑 API 설정")
    user_api_key = st.text_input("인증키 (Decoding)", value=DEFAULT_API_KEY, type="password")
    
    if not region_df.empty:
        st.header("📍 지역 선택")
        sido_list = sorted(region_df['sido'].unique())
        sel_sidos = st.multiselect("시/도", sido_list, default=["인천광역시"])
        
        filtered = region_df[region_df['sido'].isin(sel_sidos)]
        sigungu_opts = sorted(filtered['sigungu'].unique())
        
        sel_all = st.checkbox("선택한 시/도의 모든 구 포함")
        sel_sigungus = sigungu_opts if sel_all else st.multiselect("시/군/구", sigungu_opts)

    st.header("📅 기간 선택")
    # 2026년 2월은 데이터가 없으므로 2025년 위주로 선택 권장
    month_list = ["202601", "202512", "202511", "202510", "202509", "202508"]
    sel_months = st.multiselect("조회 월 (과거 데이터 권장)", month_list, default=["202601", "202512"])

if st.button("🚀 데이터 수집 시작"):
    if not user_api_key:
        st.error("API 키를 입력해주세요.")
    else:
        target_codes = region_df[region_df['sigungu'].isin(sel_sigungus)]['code'].unique()
        all_dfs = []
        
        bar = st.progress(0)
        total = len(target_codes) * len(sel_months)
        cnt = 0
        
        for ymd in sel_months:
            for code in target_codes:
                cnt += 1
                name = region_df[region_df['code'] == code]['sigungu'].values[0]
                status = st.empty()
                status.text(f"⏳ {name} ({ymd}) 데이터 확인 중...")
                
                df_tmp, msg = get_molit_data(user_api_key, code, ymd)
                if not df_tmp.empty:
                    all_dfs.append(df_tmp)
                
                bar.progress(cnt / total)
                time.sleep(0.3) # 서버 과부하 방지
        
        if all_dfs:
            final_df = pd.concat(all_dfs, ignore_index=True)
            st.success(f"✅ 총 {len(final_df)}건 수집 완료!")
            st.dataframe(final_df)
            
            # 엑셀 다운로드
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                final_df.to_excel(writer, index=False)
            st.download_button("💾 전체 데이터 다운로드", output.getvalue(), "apt_data.xlsx")
        else:
            st.warning("데이터를 가져오지 못했습니다. 위쪽의 에러 메시지를 확인하거나 더 과거의 달(예: 202512)을 선택해 보세요.")
