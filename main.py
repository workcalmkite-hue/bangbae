import streamlit as st
import pandas as pd
import gspread
import re
from google.oauth2.service_account import Credentials

# === 시트 열 이름 ===
DATE_COL = "날짜"   # B열
STU_ID_COL = "학번" # C열 (예: 3106 → 3학년 1반 06번)
NAME_COL = "이름"   # D열
ITEM_COL = "사유"   # E열
NOTE_COL = "비고"   # F열

# 학급 정보 컬럼 이름
GRADE_COL = "학년"
CLASS_COL = "반"

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
    - 'day' 컬럼에 일자(숫자)만 추출
    - '학번'에서 학년/반도 추출해서 컬럼 추가
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

    # 2) datetime으로 파싱 시도
    parsed = pd.to_datetime(df[DATE_COL], errors="coerce")

    # 3) 우선 parsed에서 day 추출
    df["day"] = parsed.dt.day

    # 4) day가 NaN인 경우는 문자열에서 숫자만 추출
    mask_na_day = df["day"].isna()
    if mask_na_day.any():
        extracted = (
            df.loc[mask_na_day, DATE_COL]
            .astype(str)
            .str.extract(r"(\d{1,2})\D*$")[0]
        )
        df.loc[mask_na_day, "day"] = pd.to_numeric(extracted, errors="coerce")

    # 학번 없는 행 제거 (요약행/공란행 등)
    if STU_ID_COL in df.columns:
        df = df[df[STU_ID_COL] != ""].copy()

    # === 학번에서 학년/반 추출 (예: 3106 → 3학년 1반) ===
    if STU_ID_COL in df.columns:
        df[STU_ID_COL] = df[STU_ID_COL].astype(str).str.strip()
        df[GRADE_COL] = df[STU_ID_COL].str[0]          # 첫 글자 = 학년
        df[CLASS_COL] = df[STU_ID_COL].str[1]          # 두 번째 글자 = 반

        # 숫자로 쓰고 싶으면 아래 주석 해제
        # df[GRADE_COL] = pd.to_numeric(df[GRADE_COL], errors="coerce")
        # df[CLASS_COL] = pd.to_numeric(df[CLASS_COL], errors="coerce")

    return df


def main():
    st.set_page_config("상벌점 대시보드", layout="wide")
    st.title("📚 상벌점 대시보드")

    # 1) 월 탭 목록
    month_sheets = list_month_sheets()
    if not month_sheets:
        st.error("이름이 'n월' 형태인 시트가 없습니다.")
        st.stop()

    # ====== (A) 날짜별 조회 ======
    st.subheader("🗓 날짜별 조회")

    col1, col2 = st.columns(2)

    with col1:
        sel_sheet = st.selectbox("월 선택", month_sheets, key="month_for_date")

    df = load_data(sel_sheet)
    if df.empty:
        st.warning(f"'{sel_sheet}' 시트에 표시할 데이터가 없습니다.")
        st.stop()

    # day 컬럼 확인
    if "day" not in df.columns or df["day"].dropna().empty:
        st.warning(f"'{sel_sheet}' 시트에서 일자 정보를 찾지 못했습니다.")
        st.stop()

    df["day"] = pd.to_numeric(df["day"], errors="coerce")
    day_list = sorted(df["day"].dropna().unique())  # 예: [1, 2, 3, ..., 31]

    with col2:
        sel_day = st.selectbox(
            "일(일자) 선택", day_list,
            format_func=lambda d: f"{int(d)}일",
            key="day_for_date"
        )

    df_day = df[df["day"] == sel_day].copy()

    st.markdown(f"#### 📌 {sel_sheet} {int(sel_day)}일 벌점 명단")
    st.write(f"총 **{len(df_day)}명**")

    display_cols = [DATE_COL, STU_ID_COL, NAME_COL, ITEM_COL, NOTE_COL]
    display_cols = [c for c in display_cols if c in df_day.columns]

    if len(df_day) == 0:
        st.info("해당 날짜에 학생 기록이 없습니다.")
    else:
        st.dataframe(df_day[display_cols], use_container_width=True)

    st.markdown("---")

    # ====== (B) 학급별 조회 ======
    st.subheader("🏫 학급별 조회 (월 전체 중)")

    col_m, col_g, col_c = st.columns(3)

    # 월 다시 선택 (원한다면 같게 써도 되고, 다르게 선택해도 됨)
    with col_m:
        sel_sheet_class = st.selectbox(
            "월 선택 (학급별 조회)", month_sheets,
            index=month_sheets.index(sel_sheet),  # 위에서 선택한 월을 기본값으로
            key="month_for_class"
        )

    df_class_base = load_data(sel_sheet_class)
    if df_class_base.empty:
        st.warning(f"'{sel_sheet_class}' 시트에 표시할 데이터가 없습니다.")
        st.stop()

    # 학년/반 정보가 없으면 안내
    if GRADE_COL not in df_class_base.columns or CLASS_COL not in df_class_base.columns:
        st.error(f"'{sel_sheet_class}' 시트에서 학년/반 정보를 찾지 못했습니다. 학번 형식을 확인해 주세요.")
        st.stop()

    # 학년 선택
    grades = sorted(df_class_base[GRADE_COL].dropna().unique())

    with col_g:
        sel_grade = st.selectbox(
            "학년 선택",
            grades,
            format_func=lambda g: f"{g}학년",
            key="grade_select"
        )

    # 반 선택 (선택한 학년에서만)
    class_options = sorted(
        df_class_base[df_class_base[GRADE_COL] == sel_grade][CLASS_COL].dropna().unique()
    )

    with col_c:
        sel_class = st.selectbox(
            "반 선택",
            class_options,
            format_func=lambda c: f"{c}반",
            key="class_select"
        )

    # 해당 학급의 월 전체 벌점 내역
    mask_class = (
        (df_class_base[GRADE_COL] == sel_grade) &
        (df_class_base[CLASS_COL] == sel_class)
    )
    df_class = df_class_base[mask_class].copy()

    st.markdown(f"#### 📌 {sel_sheet_class} {sel_grade}학년 {sel_class}반 벌점 명단 (월 전체)")
    st.write(f"총 **{len(df_class)}건**")

    display_cols_class = [DATE_COL, STU_ID_COL, NAME_COL, ITEM_COL, NOTE_COL]
    display_cols_class = [c for c in display_cols_class if c in df_class.columns]

    if len(df_class) == 0:
        st.info("해당 학급의 이 달 벌점 기록이 없습니다.")
    else:
        # 날짜 기준으로 정렬 (가능하면)
        if "day" in df_class.columns:
            df_class = df_class.sort_values("day")
        st.dataframe(df_class[display_cols_class], use_container_width=True)


if __name__ == "__main__":
    main()
