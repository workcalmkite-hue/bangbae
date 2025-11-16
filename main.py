import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# === 시트 열 이름 (지금 네 파일 기준) ===
DATE_COL = "날짜"   # 예: 8/20, 8/21 ...
STU_ID_COL = "학번" # 예: 3106
NAME_COL = "이름"
ITEM_COL = "사유"
NOTE_COL = "비고"

SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


# === 구글 시트 연결 ===
def get_gspread_client():
    try:
        info = st.secrets["gcp_service_account"]
    except Exception:
        st.error("🔐 Secrets에 [gcp_service_account] 설정이 없습니다.")
        st.stop()

    creds = Credentials.from_service_account_info(info, scopes=SCOPE)
    client = gspread.authorize(creds)
    spreadsheet_id = info["spreadsheet_id"]
    return client, spreadsheet_id


def list_worksheets():
    client, spreadsheet_id = get_gspread_client()
    sh = client.open_by_key(spreadsheet_id)
    return [ws.title for ws in sh.worksheets()]


def load_data(worksheet_name: str) -> pd.DataFrame:
    """특정 탭 전체 데이터를 그대로 읽어서 DataFrame으로."""
    client, spreadsheet_id = get_gspread_client()
    sh = client.open_by_key(spreadsheet_id)
    ws = sh.worksheet(worksheet_name)

    values = ws.get_all_values()  # 2차원 리스트 (헤더+데이터)
    if not values or len(values) == 1:
        return pd.DataFrame()

    header = [h.strip() for h in values[0]]  # 1행 = 헤더
    data_rows = values[1:]

    df = pd.DataFrame(data_rows, columns=header)

    # 필수 컬럼이 없으면 경고
    if DATE_COL not in df.columns:
        st.error(f"'{worksheet_name}' 시트에 '{DATE_COL}' 열이 없습니다. 헤더를 확인해 주세요.")
        return pd.DataFrame()

    # 날짜가 빈 셀인 행은 버림
    df = df[df[DATE_COL] != ""].copy()

    return df


# === 메인 앱 ===
def main():
    st.set_page_config("상벌점 대시보드 - 날짜별 조회", layout="wide")
    st.title("📚 상벌점 대시보드 (날짜별 조회)")

    # 1. 탭(월) 선택
    sheet_names = list_worksheets()
    if not sheet_names:
        st.error("스프레드시트에 탭이 없습니다.")
        st.stop()

    sel_sheet = st.selectbox("📄 조회할 워크시트(월) 선택", sheet_names)
    st.caption("※ 예: '8월', '11월'처럼 월별 탭을 선택하세요.")

    df = load_data(sel_sheet)
    if df.empty:
        st.warning(f"'{sel_sheet}' 시트에 표시할 데이터가 없어요.")
        st.stop()

    # 2. '날짜' 값 목록 만들기 (문자열 그대로 사용)
    unique_dates = sorted(df[DATE_COL].unique())
    sel_date = st.selectbox("📆 날짜 선택", unique_dates)

    # 3. 선택한 날짜에 해당하는 학생만 필터링
    df_day = df[df[DATE_COL] == sel_date].copy()

    st.markdown(f"### 📌 {sel_sheet} - {sel_date} 벌점 명단")
    st.write(f"총 **{len(df_day)}명**")

    # 보여줄 컬럼만 선택 (있으면 표시)
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
