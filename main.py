import streamlit as st
import pandas as pd
import gspread
import re
from google.oauth2.service_account import Credentials

# === 시트 열 이름 (현재 파일 기준) ===
DATE_COL = "날짜"   # B열
STU_ID_COL = "학번" # C열
NAME_COL = "이름"   # D열
ITEM_COL = "사유"   # E열
NOTE_COL = "비고"   # F열

SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


# === 구글 시트 연결 ===
def get_gspread_client():
    try:
        info = st.secrets["gcp_service_account"]
    except Exception:
        st.error("🔐 secrets.toml 에 [gcp_service_account] 설정이 필요해요.")
        st.stop()

    creds = Credentials.from_service_account_info(info, scopes=SCOPE)
    client = gspread.authorize(creds)
    spreadsheet_id = info["spreadsheet_id"]
    return client, spreadsheet_id


def list_month_sheets():
    """이름이 'n월' 형태인 탭만 골라서 월 순서대로 정렬"""
    client, spreadsheet_id = get_gspread_client()
    sh = client.open_by_key(spreadsheet_id)
    titles = [ws.title for ws in sh.worksheets()]

    month_titles = []
    for t in titles:
        m = re.match(r"(\d+)월", t.strip())
        if m:
            month_num = int(m.group(1))
            month_titles.append((month_num, t))

    # 월 숫자 기준으로 정렬
    month_titles.sort(key=lambda x: x[0])
    return [t for _, t in month_titles]


def load_data(worksheet_name: str) -> pd.DataFrame:
    """특정 탭의 데이터를 DataFrame으로 읽고, 날짜 빈칸은 위 날짜로 채움."""
    client, spreadsheet_id = get_gspread_client()
    sh = client.open_by_key(spreadsheet_id)
    ws = sh.worksheet(worksheet_name)

    values = ws.get_all_values()  # 헤더 + 데이터

    if not values or len(values) == 1:
        return pd.DataFrame()

    header = [h.strip() for h in values[0]]
    data_rows = values[1:]

    df = pd.DataFrame(data_rows, columns=header)

    if DATE_COL not in df.columns:
        st.error(f"'{worksheet_name}' 시트에 '{DATE_COL}' 열이 없습니다. 헤더를 확인해 주세요.")
        return pd.DataFrame()

    # 🔥 날짜 처리: 빈칸은 바로 위 날짜로 채우기 (엑셀에서 SCAN/LAMBDA 하던 것과 같은 효과)
    df[DATE_COL] = df[DATE_COL].replace("", pd.NA)
    df[DATE_COL] = df[DATE_COL].ffill()

    # 날짜가 결국 하나도 없는 시트면 빈 df 반환
    if df[DATE_COL].isna().all():
        return pd.DataFrame()

    # 완전 빈 행(학번/이름 없는 행 등)은 정리 (선택 사항)
    if STU_ID_COL in df.columns:
        df = df[df[STU_ID_COL] != ""].copy()

    return df


def main():
    st.set_page_config("상벌점 대시보드", layout="wide")
    st.title("📚 상벌점 대시보드")

    # 1) 월 탭 목록 가져오기
    month_sheets = list_month_sheets()
    if not month_sheets:
        st.error("이름이 'n월' 형태인 워크시트가 없습니다. 예: '8월', '11월'")
        st.stop()

    # 👉 월, 일을 한 줄에 나란히 선택
    col_month, col_day = st.columns(2)

    with col_month:
        sel_sheet = st.selectbox("월 선택", month_sheets)

    # 선택한 월(탭)의 데이터 읽기
    df = load_data(sel_sheet)
    if df.empty:
        st.warning(f"'{sel_sheet}' 시트에 표시할 데이터가 없어요.")
        st.stop()

    # 이 월에 실제로 존재하는 날짜 목록 (문자열 그대로)
    unique_dates = sorted(df[DATE_COL].dropna().unique())

    with col_day:
        sel_date = st.selectbox("일 선택 (해당 월의 날짜)", unique_dates)

    # 선택한 날짜만 필터링
    df_day = df[df[DATE_COL] == sel_date].copy()

    st.markdown(f"### 📌 {sel_sheet} {sel_date} 벌점 명단")
    st.write(f"총 **{len(df_day)}명**")

    # 표시할 열만 골라서 보여주기
    display_cols = []
    for col in [DATE_COL, STU_ID_COL, NAME_COL, ITEM_COL, NOTE_COL]:
        if col in df_day.columns:
            display_cols.append(col)

    if len(df_day) == 0:
        st.info("해당 날짜에 기록된 학생이 없습니다.")
    else:
        st.dataframe(df_day[display_cols], use_container_width=True)


if __name__ == "__main__":
    main()
