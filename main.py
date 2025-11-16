import streamlit as st
import pandas as pd
import gspread
import re
from google.oauth2.service_account import Credentials

# === 시트 열 이름 ===
DATE_COL = "날짜"   
STU_ID_COL = "학번"
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
        st.error("🔐 secrets.toml에 [gcp_service_account] 설정이 필요해요.")
        st.stop()

    creds = Credentials.from_service_account_info(info, scopes=SCOPE)
    client = gspread.authorize(creds)
    spreadsheet_id = info["spreadsheet_id"]
    return client, spreadsheet_id


def list_month_sheets():
    """이름이 'n월' 형태인 탭만 월 순서대로 반환"""
    client, spreadsheet_id = get_gspread_client()
    sh = client.open_by_key(spreadsheet_id)
    titles = [ws.title for ws in sh.worksheets()]

    month_titles = []
    for t in titles:
        m = re.match(r"(\d+)월", t.strip())
        if m:
            month_titles.append((int(m.group(1)), t))

    month_titles.sort(key=lambda x: x[0])
    return [t for _, t in month_titles]


def load_data(sheet_name: str) -> pd.DataFrame:
    """특정 탭의 데이터를 읽고 날짜 빈칸은 위 날짜로 채운다(ffill)."""
    client, spreadsheet_id = get_gspread_client()
    sh = client.open_by_key(spreadsheet_id)
    ws = sh.worksheet(sheet_name)

    values = ws.get_all_values()

    if not values or len(values) == 1:
        return pd.DataFrame()

    header = [h.strip() for h in values[0]]
    rows = values[1:]

    df = pd.DataFrame(rows, columns=header)

    if DATE_COL not in df.columns:
        st.error(f"'{sheet_name}' 시트에 '{DATE_COL}' 열이 없습니다.")
        return pd.DataFrame()

    # 날짜 빈칸 → 위 날짜로 채우기
    df[DATE_COL] = df[DATE_COL].replace("", pd.NA)
    df[DATE_COL] = df[DATE_COL].ffill()

    # 날짜 파싱 → parsed 컬럼 생성
    df["parsed"] = pd.to_datetime(df[DATE_COL], errors="coerce")

    # 날짜가 하나도 없으면 빈 DF
    if df["parsed"].isna().all():
        return pd.DataFrame()

    # 학번 없는 행 제거
    if STU_ID_COL in df.columns:
        df = df[df[STU_ID_COL] != ""].copy()

    return df


def main():
    st.set_page_config("상벌점 대시보드", layout="wide")
    st.title("📚 상벌점 대시보드 (월 · 일자 조회)")

    # 1) 월 탭 목록
    month_sheets = list_month_sheets()
    if not month_sheets:
        st.error("이름이 'n월' 형태인 시트가 없습니다.")
        st.stop()

    col1, col2 = st.columns(2)

    # ----- 월 선택 -----
    with col1:
        sel_sheet = st.selectbox("월 선택", month_sheets)

    # ----- 시트 데이터 불러오기 -----
    df = load_data(sel_sheet)
    if df.empty:
        st.warning(f"'{sel_sheet}' 시트에 표시할 데이터가 없습니다.")
        st.stop()

    # ----- 일자 부분만 추출 -----
    df["day"] = df["parsed"].dt.day

    day_list = sorted(df["day"].dropna().unique())  # 정렬된 '일자' 숫자 목록 (예: 1, 2, 3, ..)

    with col2:
        sel_day = st.selectbox("일(일자) 선택", day_list, format_func=lambda d: f"{d}일")

    # ----- 선택한 날짜 필터링 -----
    df_day = df[df["day"] == sel_day].copy()

    st.markdown(f"### 📌 {sel_sheet} {sel_day}일 벌점 명단")
    st.write(f"총 **{len(df_day)}명**")

    display_cols = [DATE_COL, STU_ID_COL, NAME_COL, ITEM_COL, NOTE_COL]
    display_cols = [c for c in display_cols if c in df_day.columns]

    if len(df_day) == 0:
        st.info("해당 날짜에 학생 기록이 없습니다.")
    else:
        st.dataframe(df_day[display_cols], use_container_width=True)


if __name__ == "__main__":
    main()
