import streamlit as st
import pandas as pd
import io

# 페이지 설정
st.set_page_config(page_title="학생부 데이터 병합 도구", layout="wide")

st.title("📂 학교생활기록부 데이터 병합 및 정리 도구")
st.markdown("""
여러 개의 엑셀/CSV 파일을 업로드하면, **'행동특성 및 종합의견'**과 **'세부능력 및 특기사항'** 형식에 맞춰 정리해줍니다.
""")

# 1. 파일 업로드 섹션
uploaded_files = st.file_uploader(
    "데이터 파일들을 이곳에 드래그하거나 선택하세요 (4개 이상 가능)", 
    type=['xlsx', 'xls', 'csv'], 
    accept_multiple_files=True
)

if uploaded_files:
    # 데이터 로드 및 병합
    all_data = []
    
    for file in uploaded_files:
        try:
            if file.name.endswith('.csv'):
                df = pd.read_csv(file)
            else:
                df = pd.read_excel(file)
            all_data.append(df)
        except Exception as e:
            st.error(f"{file.name} 파일을 읽는 중 오류가 발생했습니다: {e}")

    if all_data:
        # 컬럼명이 서로 다를 경우를 대비해 outer join으로 병합
        merged_df = pd.concat(all_data, ignore_index=True)
        
        st.write("---")
        st.subheader("1. 데이터 미리보기 (병합된 원본)")
        st.dataframe(merged_df.head(3))
        
        st.info("파일마다 컬럼 이름이 다를 수 있으므로, 아래에서 정리할 데이터에 해당하는 컬럼을 선택해주세요.")

        # 2. 컬럼 매핑 섹션 (사이드바 혹은 메인 화면)
        col_options = merged_df.columns.tolist()
        
        c1, c2 = st.columns(2)
        
        with c1:
            st.markdown("### 📌 공통 기준 컬럼")
            col_number = st.selectbox("학생 '번호' 컬럼 선택", col_options, index=0 if len(col_options)>0 else None)
            col_grade = st.selectbox("학생 '학년' 컬럼 선택", col_options, index=1 if len(col_options)>1 else None)
            
        with c2:
            st.markdown("### 📌 정리 대상 컬럼")
            col_behavior = st.selectbox("'행동특성 및 종합의견' 내용 컬럼", ["(없음)"] + col_options)
            
            st.markdown("---")
            col_subject = st.selectbox("'과목' 컬럼", ["(없음)"] + col_options)
            col_semester = st.selectbox("'학기' 컬럼", ["(없음)"] + col_options)
            col_detail = st.selectbox("'세부능력 및 특기사항' 내용 컬럼", ["(없음)"] + col_options)

        # 3. 데이터 처리 및 다운로드 버튼
        if st.button("데이터 정리 및 변환 시작"):
            
            # --- 처리 로직 1: 행동특성 및 종합의견 ---
            st.write("---")
            st.subheader("📋 결과 1: 행동특성 및 종합의견")
            
            if col_behavior != "(없음)":
                # 필요한 컬럼만 추출 및 결측치 제거
                df_beh = merged_df[[col_number, col_grade, col_behavior]].dropna(subset=[col_behavior])
                
                # 데이터 타입 통일 (문자열로 변환)
                df_beh[col_number] = df_beh[col_number].astype(str)
                df_beh[col_behavior] = df_beh[col_behavior].astype(str)

                # 같은 번호, 같은 학년인 경우 내용 합치기 (줄바꿈으로 구분)
                df_beh_grouped = df_beh.groupby([col_number, col_grade])[col_behavior].apply(lambda x: '\n'.join(x)).reset_index()
                
                # 정렬: 번호순
                df_beh_grouped = df_beh_grouped.sort_values(by=[col_number])
                
                # 컬럼명 변경 (사용자 요청 형식: 번호-학년-행동특성및종합의견)
                df_beh_grouped.columns = ['번호', '학년', '행동특성 및 종합의견']
                
                st.dataframe(df_beh_grouped)
                
                # 엑셀 다운로드
                buffer_beh = io.BytesIO()
                with pd.ExcelWriter(buffer_beh, engine='xlsxwriter') as writer:
                    df_beh_grouped.to_excel(writer, index=False, sheet_name='행동특성')
                
                st.download_button(
                    label="📥 행동특성 결과 다운로드 (Excel)",
                    data=buffer_beh.getvalue(),
                    file_name="정리된_행동특성및종합의견.xlsx",
                    mime="application/vnd.ms-excel"
                )
            else:
                st.warning("행동특성 컬럼이 선택되지 않았습니다.")

            # --- 처리 로직 2: 세부능력 및 특기사항 ---
            st.subheader("📋 결과 2: 세부능력 및 특기사항")
            
            if col_subject != "(없음)" and col_semester != "(없음)" and col_detail != "(없음)":
                # 필요한 컬럼 추출
                df_det = merged_df[[col_number, col_subject, col_grade, col_semester, col_detail]].dropna(subset=[col_detail])
                
                # 데이터 타입 통일
                df_det[col_number] = df_det[col_number].astype(str)
                df_det[col_subject] = df_det[col_subject].astype(str)
                df_det[col_semester] = df_det[col_semester].astype(str)
                df_det[col_detail] = df_det[col_detail].astype(str)

                # 같은 번호, 과목, 학년, 학기인 경우 내용 합치기
                group_cols = [col_number, col_subject, col_grade, col_semester]
                df_det_grouped = df_det.groupby(group_cols)[col_detail].apply(lambda x: '\n'.join(x)).reset_index()
                
                # 정렬: 과목순 -> 학기순 -> 번호순
                df_det_grouped = df_det_grouped.sort_values(by=[col_subject, col_semester, col_number])
                
                # 컬럼명 변경 (사용자 요청 형식)
                df_det_grouped.columns = ['번호', '과목', '학년', '학기', '세부능력 및 특기사항']
                
                st.dataframe(df_det_grouped)
                
                # 엑셀 다운로드
                buffer_det = io.BytesIO()
                with pd.ExcelWriter(buffer_det, engine='xlsxwriter') as writer:
                    df_det_grouped.to_excel(writer, index=False, sheet_name='세특')
                    
                st.download_button(
                    label="📥 세부능력 및 특기사항 결과 다운로드 (Excel)",
                    data=buffer_det.getvalue(),
                    file_name="정리된_세부능력및특기사항.xlsx",
                    mime="application/vnd.ms-excel"
                )
            else:
                st.warning("세특 관련 컬럼(과목, 학기, 내용) 중 선택되지 않은 항목이 있습니다.")
