import streamlit as st
import pandas as pd
from datetime import date, timedelta

import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import GSpreadException

# 🔧 시트 헤더 이름에 맞춰서 설정
DATE_COL = "날짜"
STU_ID_COL = "학번"   # 학년+반+번호 (예: 2414)
NAME_COL = "이름"
ITEM_COL = "사유"
NOTE_COL = "비고"

# 학번에서 자동으로 만들 컬럼 이름
GRADE_COL = "학년"
CLASS_COL = "반"

# 시간대 열은 지금 시트에 없지만, 나중에 추가될 수도 있으니 옵션으로 둠
TIME_COL = "시간대"    # 있으면 아침만 필터, 없으면 하루 전체

BASE_DISPLAY_COLS = [
    DATE_COL, GRADE_COL, CLASS_COL, STU_ID_COL,
    NAME_COL, ITEM_COL, NOTE_COL
]

SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_gspread_client():
    """Streamlit secrets의 서비스 계정 정보로 gspread 클라이언트 생성"""
    try:
        creds_info = st.secrets["gcp_service_account"]
    except Exception:
        st.error("🔐 Streamlit Secrets에 [gcp_service_account] 설정이 필요해요.")
        st.stop()

    creds = Credentials.from_service_account_info(creds_info, scopes=SCOPE)
    client = gspread.authorize(creds)
    spreadsheet_id = creds_info["spreadsheet_id"]

    return client, spreadsheet_id


@st.cache_data(ttl=300)
def list_worksheets():
    """스프레드시트 안의 워크시트(탭) 목록 가져오기"""
    client, spreadsheet_id = get_gspread_client()
    sh = client.open_by_key(spreadsheet_id)
    sheets = sh.worksheets()
    return [ws.title for ws in sheets]


@st.cache_data(ttl=300)
def load_data(worksheet_name: str) -> pd.DataFrame:
    """특정 워크시트(탭)의 상벌점 데이터 불러오기"""
    client, spreadsheet_id = get_gspread_client()
    sh = client.open_by_key(spreadsheet_id)
    ws = sh.worksheet(worksheet_name)

    try:
        data = ws.get_all_records()
    except GSpreadException:
        st.warning(f"'{worksheet_name}' 시트에 데이터가 없거나, 첫 줄에 열 이름(헤더)이 없습니다.")
        return pd.DataFrame()

    df = pd.DataFrame(data)

    if DATE_COL not in df.columns or STU_ID_COL not in df.columns:
        st.error(f"시트에 '{DATE_COL}', '{STU_ID_COL}' 열이 있어야 해요. 헤더를 확인해주세요.")
        return pd.DataFrame()

    # 날짜 파싱
    df[DATE_COL] = pd.to_datetime(df[DATE_COL], errors="coerce")
    df = df.dropna(subset=[DATE_COL]).copy()

    # 학번 → 문자열로 맞추기
    df[STU_ID_COL] = df[STU_ID_COL].astype(str).str.strip()

    # 학번에서 학년/반 추출 (예: 2414 → 2학년 4반)
    # 길이가 2 이상인 학번만 사용
    df[GRADE_COL] = df[STU_ID_COL].str[0]
    df[CLASS_COL] = df[STU_ID_COL].str[1]

    # 숫자로 쓰고 싶으면 아래 주석 해제
    # df[GRADE_COL] = pd.to_numeric(df[GRADE_COL], errors="coerce").astype("Int64")
    # df[CLASS_COL] = pd.to_numeric(df[CLASS_COL], errors="coerce").astype("Int64")

    # 월/일/날짜만 컬럼 추가
    df["월"] = df[DATE_COL].dt.month
    df["일"] = df[DATE_COL].dt.day
    df["date_only"] = df[DATE_COL].dt.date

    return df


def get_display_cols(df: pd.DataFrame):
    return [c for c in BASE_DISPLAY_COLS if c in df.columns]


def main():
    st.set_page_config("상벌점 대시보드", layout="wide")
    st.title("📚 상벌점 대시보드")

    # 어떤 탭(월)을 볼지 선택
    sheet_names = list_worksheets()
    if not sheet_names:
        st.error("불러올 워크시트가 없습니다. 스프레드시트 탭을 확인해 주세요.")
        st.stop()

    sel_sheet = st.selectbox("📄 조회할 워크시트(월) 선택", sheet_names)
    st.caption("※ 예: 1월, 2월, 3월 처럼 월별로 탭을 나눠서 쓰는 경우 해당 탭을 선택하세요.")

    df = load_data(sel_sheet)
    if df.empty:
        st.warning(f"'{sel_sheet}' 시트에 표시할 데이터가 없어요.")
        st.stop()

    col_left, col_right = st.columns(2)

    # 1️⃣ '월'과 '일'을 선택하면 (아침) 벌점 보기
    with col_left:
        st.subheader("1️⃣ 날짜별 (아침) 벌점 내역")

        months = sorted(df["월"].unique())
        sel_month = st.selectbox("월 선택", months, format_func=lambda m: f"{m}월")

        df_month = df[df["월"] == sel_month]
        days = sorted(df_month["일"].unique())
        sel_day = st.selectbox("일 선택", days, format_func=lambda d: f"{d}일")

        mask = (df["월"] == sel_month) & (df["일"] == sel_day)

        if TIME_COL in df.columns:
            mask = mask & (df[TIME_COL] == "아침")
        else:
            st.info("⚠️ '시간대' 열이 없어서, 선택한 날짜의 전체 벌점을 보여줄게요.")

        df_morning = df.loc[mask].copy()

        st.caption(
            f"선택 날짜: **{sel_month}월 {sel_day}일**, "
            f"벌점 건수: **{len(df_morning)}건**"
        )

        if len(df_morning) == 0:
            st.write("해당 날짜의 벌점 내역이 없습니다.")
        else:
            display_cols = get_display_cols(df_morning)
            st.dataframe(
                df_morning[display_cols].sort_values(DATE_COL),
                use_container_width=True,
            )

    # 2️⃣ 학년/반 선택 → 오늘 & 이번주 벌점
    with col_right:
        st.subheader("2️⃣ 학급별 오늘 / 이번주 벌점")

        today = date.today()
        week_start = today - timedelta(days=today.weekday())  # 이번 주 월요일
        week_end = week_start + timedelta(days=6)              # 이번 주 일요일

        grades = sorted(df[GRADE_COL].dropna().unique())
        sel_grade = st.selectbox("학년 선택", grades, format_func=lambda g: f"{g}학년")

        class_options = sorted(
            df[df[GRADE_COL] == sel_grade][CLASS_COL].dropna().unique()
        )
        sel_class = st.selectbox("반 선택", class_options,
                                 format_func=lambda c: f"{c}반")

        class_mask = (df[GRADE_COL] == sel_grade) & (df[CLASS_COL] == sel_class)

        df_today = df[(df["date_only"] == today) & class_mask].copy()
        df_week = df[
            (df["date_only"] >= week_start)
            & (df["date_only"] <= week_end)
            & class_mask
        ].copy()

        display_cols_today = get_display_cols(df_today)
        display_cols_week = get_display_cols(df_week)

        col_a, col_b = st.columns(2)

        # 🕒 오늘 벌점
        with col_a:
            st.markdown(f"### 🕒 오늘 벌점 ({today})")
            st.write(f"오늘 벌점 건수: **{len(df_today)}건**")

            if len(df_today) == 0:
                st.write("오늘 벌점 내역이 없습니다.")
            else:
                st.dataframe(
                    df_today[display_cols_today].sort_values(DATE_COL),
                    use_container_width=True,
                )

        # 📅 이번주 벌점
        with col_b:
            st.markdown(
                f"### 📅 이번주 벌점 "
                f"({week_start} ~ {week_end})"
            )
            st.write(f"이번주 벌점 건수: **{len(df_week)}건**")

            if len(df_week) == 0:
                st.write("이번주 벌점 내역이 없습니다.")
            else:
                st.dataframe(
                    df_week[display_cols_week].sort_values(DATE_COL),
                    use_container_width=True,
                )

    st.markdown("---")
    st.caption(
        "✅ 모든 탭의 1행에 '날짜, 학번, 이름, 사유, 비고' 헤더가 있어야 하며, "
        "학번은 '2414'처럼 학년+반+번호 형식이라고 가정했어요."
    )


if __name__ == "__main__":
    main()
