import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime

# 1. 전국 시도 및 시군구 법정동 코드 데이터 (주요 지역 예시 - 구조화)
# 실제로는 수백 개이므로 대표 지역을 넣었습니다. 구조에 따라 추가 가능합니다.
REGION_MAP = {
    "서울특별시": {"강남구": "11680", "서초구": "11650", "송파구": "11710", "강동구": "11740", "마포구": "11440"},
    "경기도": {"수원시": "41110", "성남시 분당구": "41135", "용인시 수지구": "41465", "고양시 일산동구": "41281"},
    "인천광역시": {"연수구": "28185", "부평구": "28237"},
    "부산광역시": {"해운대구": "26350", "수영구": "26500"},
    "대구광역시": {"수성구": "27260"},
    "대전광역시": {"유성구": "30200"},
    "세종특별자치시": {"세종시": "36110"}
    # 필요에 따라 https://www.code.go.kr 에서 코드를 찾아 추가할 수 있습니다.
}

def get_data(key, code, ymd):
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

# UI 구성
st.set_page_config(page_title="전국 아파트 실거래 수집기", layout="wide")
st.title("🏠 전국 아파트 실거래가 데이터 추출기")
st.markdown("경매 복기 및 투자 적정가 예측을 위한 시세 수집 도구입니다.")

with st.sidebar:
    st.header("⚙️ 설정")
    api_key = st.text_input("공공데이터 API 인증키(Decoding)", type="password")
    
    sido = st.selectbox("시/도 선택", list(REGION_MAP.keys()))
    sigungu = st.selectbox("시/군/구 선택", list(REGION_MAP[sido].keys()))
    lawd_code = REGION_MAP[sido][sigungu]
    
    date = st.date_input("조회 월 선택", value=datetime.now())
    target_ymd = date.strftime("%Y%m")
    
    file_type = st.radio("파일 형식", ["Excel", "CSV"])

if st.button("데이터 가져오기"):
    if not api_key:
        st.warning("API 인증키를 입력해주세요.")
    else:
        df = get_data(api_key, lawd_code, target_ymd)
        if not df.empty:
            st.success(f"{sido} {sigungu} {target_ymd} 데이터 {len(df)}건을 찾았습니다.")
            st.dataframe(df)
            
            # 다운로드 버튼
            if file_type == "Excel":
                import io
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False)
                st.download_button("엑셀 다운로드", data=output.getvalue(), file_name=f"apt_{lawd_code}_{target_ymd}.xlsx")
            else:
                csv = df.to_csv(index=False).encode('utf-8-sig')
                st.download_button("CSV 다운로드", data=csv, file_name=f"apt_{lawd_code}_{target_ymd}.csv")
        else:
            st.error("데이터가 없거나 인증키가 잘못되었습니다. (방금 발급받았다면 1~2시간 후 시도하세요)")