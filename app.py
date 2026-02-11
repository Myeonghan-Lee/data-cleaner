import streamlit as st
import pandas as pd
import io

# 페이지 기본 설정
st.set_page_config(page_title="나이스 데이터 정리 도구 (분리형)", layout="wide")

st.title("📂 학교생활기록부 데이터 정리 도구")
st.markdown("""
나이스 엑셀 파일을 업로드하면 **성명을 제외하고** 깔끔하게 정리해줍니다.
- **세부능력 및 특기사항**: 과목별로 행이 분리되며, `과목 > 학기 > 번호` 순으로 정렬됩니다.
- **행동특성 및 종합의견**: 학생별로 정리되며, `번호` 순으로 정렬됩니다.
""")

# --------------------------------------------------------------------------------
# 함수 정의: 텍스트 병합 및 데이터 처리
# --------------------------------------------------------------------------------
def process_data(file):
    try:
        # 1. 헤더 위치 찾기 ('번 호'가 있는 행 찾기)
        temp_df = pd.read_excel(file, header=None, nrows=10)
        header_row_index = -1
        
        for i, row in temp_df.iterrows():
            row_values = row.astype(str).values
            if any("번 호" in s for s in row_values):
                header_row_index = i
                break
        
        if header_row_index == -1:
            return None, "표의 헤더('번 호')를 찾을 수 없습니다."

        # 2. 데이터 로드
        file.seek(0)
        df = pd.read_excel(file, header=header_row_index)

        # 3. 컬럼명 전처리 (공백 제거)
        df.columns = [str(c).replace(" ", "") for c in df.columns]
        
        if '번호' not in df.columns:
             return None, "'번호' 컬럼을 찾을 수 없습니다."

        # 4. 공통 전처리: 번호, 학년 등 빈칸 채우기 (Merge 된 셀 처리)
        # 번호, 학년, 반, 성명 등은 기본적으로 채워야 함
        cols_to_fill = ['번호', '학년', '반']
        if '성명' in df.columns:
            cols_to_fill.append('성명')
        if '학기' in df.columns:
            cols_to_fill.append('학기')
        if '과목' in df.columns:
            cols_to_fill.append('과목')

        for col in cols_to_fill:
            if col in df.columns:
                df[col] = df[col].fillna(method='ffill')

        # 5. 파일 종류 판별 및 분기 처리
        
        # --- CASE A: 세부능력 및 특기사항 (과목 컬럼이 있음) ---
        if '과목' in df.columns:
            st.info("💡 [세부능력 및 특기사항] 파일로 인식되었습니다.")
            
            # 내용이 들어있는 컬럼 찾기 (제외할 컬럼들을 뺀 나머지)
            exclude_cols = ['번호', '성명', '학년', '반', '학기', '이수단위', '원점수', '과목', '성취도/석차등급', '석차등급', '성취도', '과목평균', '표준편차']
            content_col = [c for c in df.columns if c not in exclude_cols][0] # 보통 하나만 남음
            
            # 내용 병합 함수
            def merge_text(x):
                return "\n".join([str(s) for s in x if pd.notnull(s) and str(s).strip() != ""])

            # 그룹화: 과목, 학년, 학기, 번호 기준으로 묶음 (성명 제외)
            # 이렇게 해야 같은 학생의 같은 과목 내용이 여러 줄일 때 하나로 합쳐짐
            result_df = df.groupby(['과목', '학년', '학기', '번호'])[content_col].apply(merge_text).reset_index()
            
            # 컬럼 이름 변경 (명확하게)
            result_df.rename(columns={content_col: '세부능력 및 특기사항'}, inplace=True)
            
            # 정렬: 과목 -> 학기 -> 번호
            # 정렬을 위해 번호와 학기를 숫자로 변환
            result_df['번호_숫자'] = pd.to_numeric(result_df['번호'], errors='coerce')
            result_df['학기_숫자'] = pd.to_numeric(result_df['학기'], errors='coerce')
            
            result_df = result_df.sort_values(by=['과목', '학기_숫자', '번호_숫자'])
            
            # 최종 출력 컬럼 순서 지정 (요청사항: 번호-과목-학년-학기-내용)
            final_cols = ['번호', '과목', '학년', '학기', '세부능력 및 특기사항']
            result_df = result_df[final_cols]


        # --- CASE B: 행동특성 및 종합의견 (과목 컬럼이 없음) ---
        else:
            st.info("💡 [행동특성 및 종합의견] 파일로 인식되었습니다.")
            
            # 내용 컬럼 찾기
            exclude_cols = ['번호', '성명', '학년', '반']
            content_col = [c for c in df.columns if c not in exclude_cols][0]

            def merge_text(x):
                return "\n".join([str(s) for s in x if pd.notnull(s) and str(s).strip() != ""])

            # 그룹화: 번호, 학년 기준으로 묶음
            result_df = df.groupby(['번호', '학년'])[content_col].apply(merge_text).reset_index()
            
            # 컬럼 이름 변경
            result_df.rename(columns={content_col: '행동특성 및 종합의견'}, inplace=True)
            
            # 정렬: 번호순
            result_df['번호_숫자'] = pd.to_numeric(result_df['번호'], errors='coerce')
            result_df = result_df.sort_values(by=['번호_숫자'])
            
            # 최종 출력 컬럼 순서 지정 (요청사항: 번호-학년-내용)
            final_cols = ['번호', '학년', '행동특성 및 종합의견']
            result_df = result_df[final_cols]

        return result_df, None

    except Exception as e:
        return None, f"오류 발생: {str(e)}\n(올바른 엑셀 파일인지 확인해주세요)"

# --------------------------------------------------------------------------------
# 메인 UI
# --------------------------------------------------------------------------------
uploaded_file = st.file_uploader("나이스 엑셀 파일(.xlsx) 업로드", type=['xlsx'])

if uploaded_file:
    with st.spinner('데이터 분석 및 정리 중...'):
        processed_df, error_msg = process_data(uploaded_file)
        
    if error_msg:
        st.error(error_msg)
    else:
        st.success("정리 완료!")
        
        # 데이터프레임 보여주기 (처음 5행만 보여주거나 전체 보여주기)
        st.dataframe(processed_df, use_container_width=True)
        
        # 엑셀 다운로드 준비
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            processed_df.to_excel(writer, index=False, sheet_name='Sheet1')
            
            # 서식 설정
            workbook = writer.book
            worksheet = writer.sheets['Sheet1']
            
            # 스타일 정의
            header_format = workbook.add_format({
                'bold': True,
                'text_wrap': True,
                'valign': 'vcenter',
                'fg_color': '#D7E4BC',
                'border': 1
            })
            text_format = workbook.add_format({
                'text_wrap': True, 
                'valign': 'top',
                'border': 1
            })
            center_format = workbook.add_format({
                'align': 'center', 
                'valign': 'top',
                'border': 1
            })

            # 컬럼 너비 및 서식 적용
            # A열(번호) ~ 마지막 열까지 순회
            for col_num, col_name in enumerate(processed_df.columns):
                # 내용이 들어가는 긴 컬럼인지 확인 (이름이 긴 것들)
                if "세부능력" in col_name or "행동특성" in col_name:
                    worksheet.set_column(col_num, col_num, 60, text_format) # 너비 60
                else:
                    worksheet.set_column(col_num, col_num, 8, center_format) # 너비 8, 가운데 정렬

            # 헤더 서식 적용
            for col_num, value in enumerate(processed_df.columns.values):
                worksheet.write(0, col_num, value, header_format)
            
        processed_data = output.getvalue()
        
        file_prefix = "세특정리" if "세부능력" in processed_df.columns[-1] else "행특정리"
        
        st.download_button(
            label="📥 정리된 엑셀 파일 다운로드",
            data=processed_data,
            file_name=f"{file_prefix}_{uploaded_file.name}",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
