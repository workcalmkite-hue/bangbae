import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime

import gspread
from google.oauth2.service_account import Credentials

# 🔧 여기서 열 이름만 네 시트에 맞게 바꿔주면 돼!
DATE_COL = "날짜"
TIME_COL = "시간대"
GRADE_COL = "학년"
CLASS_COL = "반"
NAME_COL = "이름"
ITEM_COL = "항목"
SCORE_COL = "점수"   # 없으면 그냥 무시됨
NOTE_COL = "비고"    # 없으면 그냥 무시됨

BASE_DISPLAY_COLS = [
    DATE_COL, TIME_COL, GRADE_COL, CLASS_COL,
    NAME_COL, ITEM_COL, SCORE_COL, NOTE_COL
]

SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


@st.cache_data(ttl=300)
def load_data() -> pd.DataFrame:
    """구글 시트에서 상벌점 데이터 불러오기"""
    try:
        creds_info = st.secrets["gcp_service_account"]
    except Exception:
        st.error("🔐 Streamlit Secrets에 gcp_service_account 설정이 필요해요.")
        return pd.DataFrame()

    creds = Credentials.from_service_account_info(creds_info, scopes=SCOPE)
    client = gspread.authorize(creds)

    spreadsheet_id = st.secrets["spreadsheet_id"]
    worksheet_name = st.secrets["worksheet_name"]

    sh = client.open_by_key(spreadsheet_id)
    ws = sh.worksheet(worksheet_name)

    data = ws.get_all_records()
    df = pd.DataFrame(data)

    if DATE_COL not in df.columns:
        st.error(f"시트에 '{DATE_COL}' 열이 있어야 해요. 열 이름을 확인해 주세요.")
        return pd.DataFrame()

    # 날짜 파싱
    df[DATE_COL] = pd.to_datetime(df[DATE_COL], errors="coerce")
    df = df.dropna(subset=[DATE_COL]).copy()

    df["월"] = df[DATE_COL].dt.month
    df["일"] = df[DATE_COL].dt.day
    df["date_only"] = df[DATE_COL].dt.date

    return df


def get_display_cols(df: pd.DataFrame):
    return [c for c in BASE_DISPLAY_COLS if c in df.columns]


def main():
    st.set_page_config("상벌점 대시보드", layout="wide")
    st.title("📚 상벌점 대시보드")

    df = load_data()
    if df.empty:
        st.stop()

    col_left, col_right = st.columns(2)

    # 1️⃣ '월'과 '일'을 선택하면 아침 벌점 보기
    with col_left:
        st.subheader("1️⃣ 날짜별 아침 벌점 내역")

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
            f"아침 벌점 건수: **{len(df_morning)}건**"
        )

        if len(df_morning) == 0:
            st.write("해당 날짜의 아침 벌점 내역이 없습니다.")
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
        week_start = today - timedelta(days=today.weekday())  # 월요일
        week_end = week_start + timedelta(days=6)              # 일요일

        if GRADE_COL not in df.columns or CLASS_COL not in df.columns:
            st.error(f"'{GRADE_COL}', '{CLASS_COL}' 열이 필요해요.")
            st.stop()

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

        with col_a:
            st.markdown(f"### 🕒 오늘 벌점 ({today})")
            st.write(f"오늘 벌점 건수: **{len(df_today)}건**")

            if SCORE_COL in df_today.columns:
                try:
                    total_score_today = pd.to_numeric(
                        df_today[SCORE_COL], errors="coerce"
                    ).sum()
                    st.write(f"오늘 벌점 점수 합계: **{total_score_today}점**")
                except Exception:
                    pass

            if len(df_today) == 0:
                st.write("오늘 벌점 내역이 없습니다.")
            else:
                st.dataframe(
                    df_today[display_cols_today].sort_values(DATE_COL),
                    use_container_width=True,
                )

        with col_b:
            st.markdown(
                f"### 📅 이번주 벌점 "
                f"({week_start} ~ {week_end})"
            )
            st.write(f"이번주 벌점 건수: **{len(df_week)}건**")

            if SCORE_COL in df_week.columns:
                try:
                    total_score_week = pd.to_numeric(
                        df_week[SCORE_COL], errors="coerce"
                    ).sum()
                    st.write(f"이번주 벌점 점수 합계: **{total_score_week}점**")
                except Exception:
                    pass

            if len(df_week) == 0:
                st.write("이번주 벌점 내역이 없습니다.")
            else:
                st.dataframe(
                    df_week[display_cols_week].sort_values(DATE_COL),
                    use_container_width=True,
                )

    st.markdown("---")
    st.caption(
        "✅ 시트 구조(열 이름)가 다르면, 파일 상단에 있는 "
        f"`{DATE_COL}`, `{TIME_COL}`, `{GRADE_COL}`, `{CLASS_COL}` 같은 상수만 "
        "네 시트에 맞게 수정해줘."
    )


if __name__ == "__main__":
    main()
