import streamlit as st
import pandas as pd
import gspread
import re
from google.oauth2.service_account import Credentials

# === 시트 열 이름 ===
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
    """
    특정 탭의 데이터를 읽고:
    - '날짜' 빈칸은 위 날짜로 채움(ffill)
    - 'day' 컬럼에 일자(숫자)만 추출해서 넣음
    """
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

    # 1) 날짜 빈칸 → 위 날짜로 채우기
    df[DATE_COL] = df[DATE_COL].replace("", pd.NA)
    df[DATE_COL] = df[DATE_COL].ffill()

    # 2) 우선 datetime으로 한 번 파싱 시도
    parsed = pd.to_datetime(df[DATE_COL], errors="coerce")

    # 3) 기본 day는 parsed에서 뽑기
    df["day"] = parsed.dt.day

    # 4) 그래도 day가 NaN인 행은, 문자열에서 숫자만 추출해서 day로 사용
    mask_na_day = df["day"].isna()
    if mask_na_day.any():
        # 문자열 끝부분의 1~2자리 숫자 추출 (예: "4/11", "4월 11일" → "11")
        extracted = (
            df.loc[mask_na_day, DATE_COL]
            .astype(str)
            .str.extract(r"(\d{1,2})\D*$")[0]
        )
        df.loc[mask_na_day, "day"] = pd.to_numeric(extracted, errors="coerce")

    # 5) day가 결국 하나도 없으면, 날짜 기준 필터는 못하지만 df는 반환
    #    (main에서 다시 체크)
    # 학번 없는 행은 제거 (요약행/공란행 등)
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

    # day 컬럼이 없는 경우 대비
    if "day" not in df.columns or df["day"].dropna().empty:
        st.warning(f"'{sel_sheet}' 시트에서 일자 정보를 찾지 못했습니다.")
        st.stop()

    # ----- 일자 목록(숫자) 만들기 -----
    df["day"] = pd.to_numeric(df["day"], errors="coerce")
    day_list = sorted(df["day"].dropna().unique())  # 예: [1, 2, 3, ..., 31]

    with col2:
        sel_day = st.selectbox("일(일자) 선택", day_list, format_func=lambda d: f"{int(d)}일")

    # ----- 선택한 일자의 데이터 필터링 -----
    df_day = df[df["day"] == sel_day].copy()

    st.markdown(f"### 📌 {sel_sheet} {int(sel_day)}일 벌점 명단")
    st.write(f"총 **{len(df_day)}명**")

    display_cols = [DATE_COL, STU_ID_COL, NAME_COL, ITEM_COL, NOTE_COL]
    display_cols = [c for c in display_cols if c in df_day.columns]

    if len(df_day) == 0:
        st.info("해당 날짜에 학생 기록이 없습니다.")
    else:
        st.dataframe(df_day[display_cols], use_container_width=True)


if __name__ == "__main__":
    main()
