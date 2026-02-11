import streamlit as st
import pandas as pd
import io

# 페이지 기본 설정
st.set_page_config(page_title="나이스 데이터 정리 도구 (익명)", layout="wide")

st.title("📂 학교생활기록부 데이터 정리 도구 (익명)")
st.markdown("""
나이스에서 다운로드한 **행동특성 및 종합의견** 혹은 **세부능력 및 특기사항** 엑셀 파일을 업로드하세요.
- **결과 파일에는 '성명'이 포함되지 않고 '번호'만 남습니다.**
- 불필요한 상단 정보를 자동으로 찾아 제거합니다.
- 같은 번호를 가진 행들의 내용을 하나로 합쳐줍니다.
""")

# --------------------------------------------------------------------------------
# 함수 정의: 데이터 전처리 및 병합 로직
# --------------------------------------------------------------------------------
def process_data(file):
    try:
        # 1. 헤더 위치 찾기 ('번 호'가 있는 행을 찾습니다)
        # 성명이 없어도 작동하도록 '번 호' 키워드 위주로 찾습니다.
        temp_df = pd.read_excel(file, header=None, nrows=10)
        header_row_index = -1
        
        for i, row in temp_df.iterrows():
            row_values = row.astype(str).values
            # '번 호'라는 글자가 포함된 행을 헤더로 인식
            if any("번 호" in s for s in row_values):
                header_row_index = i
                break
        
        if header_row_index == -1:
            return None, "표의 헤더('번 호')를 찾을 수 없습니다."

        # 2. 찾은 위치를 기준으로 파일 읽기
        file.seek(0) 
        df = pd.read_excel(file, header=header_row_index)

        # 3. 데이터 클렌징
        # 컬럼명 공백 제거 (예: "번 호" -> "번호")
        df.columns = [c.replace(" ", "") if isinstance(c, str) else c for c in df.columns]
        
        if '번호' not in df.columns:
             return None, "'번호' 컬럼을 찾을 수 없습니다."

        # 번호의 빈칸 채우기 (ffill)
        df['번호'] = df['번호'].fillna(method='ffill')
        
        # (옵션) 성명 컬럼이 있다면 내부 처리를 위해 빈칸은 채우되, 결과엔 안 씀
        if '성명' in df.columns:
            df['성명'] = df['성명'].fillna(method='ffill')

        # 4. 내용 합치기
        # 합칠 대상 컬럼 찾기 (번호, 성명, 학년, 반, 학기 등을 제외한 긴 텍스트)
        exclude_cols = ['번호', '성명', '학년', '반', '학기', '이수단위', '원점수', '과목', '성취도/석차등급', '석차등급', '성취도']
        target_cols = [c for c in df.columns if c not in exclude_cols]

        # 병합 로직 함수
        def merge_text(x):
            # 내용이 있는 것만 골라서 줄바꿈으로 연결
            return "\n".join([str(s) for s in x if pd.notnull(s) and str(s).strip() != ""])

        # '과목' 컬럼이 있다면 내용을 "[과목명] 내용" 형태로 변환
        if '과목' in df.columns:
             # 과목명도 빈칸이면 채워줌
             df['과목'] = df['과목'].fillna(method='ffill')
             df['내용병합'] = "[" + df['과목'].astype(str) + "] " + df[target_cols[0]].astype(str)
             target_col_name = '내용병합'
        else:
             # 과목 컬럼이 없으면(행동특성 등) 첫번째 긴 텍스트 컬럼 사용
             target_col_name = target_cols[0] if target_cols else None

        if not target_col_name:
            return None, "합칠 내용이 있는 컬럼을 찾지 못했습니다."

        # ★ 핵심 수정 사항: 그룹화 기준에서 '성명'을 제거하고 '번호'로만 묶습니다.
        # 이렇게 하면 결과 데이터프레임에 '성명' 컬럼이 생성되지 않습니다.
        result_df = df.groupby(['번호'])[target_col_name].apply(merge_text).reset_index()
        
        # 번호 순으로 정렬 (숫자로 변환 후 정렬)
        result_df['번호'] = pd.to_numeric(result_df['번호'], errors='coerce')
        result_df = result_df.sort_values('번호')

        return result_df, None

    except Exception as e:
        return None, str(e)

# --------------------------------------------------------------------------------
# 메인 UI
# --------------------------------------------------------------------------------
uploaded_file = st.file_uploader("엑셀 파일(.xlsx)을 드래그하거나 선택하세요", type=['xlsx'])

if uploaded_file:
    with st.spinner('파일을 분석하고 정리하는 중입니다...'):
        processed_df, error_msg = process_data(uploaded_file)
        
    if error_msg:
        st.error(f"오류가 발생했습니다: {error_msg}")
    else:
        st.success("정리가 완료되었습니다! (성명 제외됨)")
        
        # 결과 미리보기
        st.dataframe(processed_df)
        
        # 다운로드 버튼
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            processed_df.to_excel(writer, index=False, sheet_name='Sheet1')
            
            # 엑셀 서식 다듬기
            workbook = writer.book
            worksheet = writer.sheets['Sheet1']
            format_text = workbook.add_format({'text_wrap': True, 'valign': 'top'})
            
            # A열(번호) 너비 줄이고, B열(내용) 너비 넓힘
            worksheet.set_column('A:A', 10)
            worksheet.set_column('B:B', 60, format_text)
            
        processed_data = output.getvalue()
        
        st.download_button(
            label="📥 정리된 엑셀 파일 다운로드 (익명)",
            data=processed_data,
            file_name=f"정리된_{uploaded_file.name}",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
