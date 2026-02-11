import streamlit as st
import pandas as pd
import io
import re

# --- 페이지 설정 ---
st.set_page_config(page_title="NEIS 학생부 데이터 통합 도구", layout="wide")

st.title("📊 학생부(행동특성/세특) 데이터 통합 정리 도구")
st.markdown("""
여러 개의 **행동특성 및 종합의견** 파일과 **세부능력 및 특기사항** 파일을 업로드하면, 
**학생(번호)별로 내용을 하나의 셀에 합쳐서** 정리해 줍니다.
""")

# --- 함수 정의 ---

def normalize_columns(df):
    """컬럼명에서 공백과 줄바꿈을 제거하여 표준화"""
    df.columns = df.columns.str.replace(' ', '').str.replace('\n', '').str.strip()
    return df

def find_header_row(df_raw, keywords=['번호', '성명']):
    """데이터프레임 상단에서 실제 헤더가 있는 행(row) 인덱스를 찾음"""
    for i in range(min(10, len(df_raw))):
        row_values = df_raw.iloc[i].astype(str).tolist()
        # 키워드가 모두 포함된 행을 찾음
        if all(any(k in val for val in row_values) for k in keywords):
            return i
    return 0

def load_data(uploaded_file):
    """업로드된 파일을 읽어서 적절한 헤더를 찾아 DataFrame으로 반환"""
    file_ext = uploaded_file.name.split('.')[-1].lower()
    
    try:
        if file_ext == 'csv':
            # 인코딩 문제 방지를 위해 euc-kr, cp949, utf-8 순 시도
            try:
                df_raw = pd.read_csv(uploaded_file, encoding='cp949', header=None)
            except:
                df_raw = pd.read_csv(uploaded_file, encoding='utf-8', header=None)
        else:
            df_raw = pd.read_excel(uploaded_file, header=None)
            
        header_idx = find_header_row(df_raw)
        
        # 다시 읽기 (헤더 적용)
        if file_ext == 'csv':
             try:
                df = pd.read_csv(uploaded_file, encoding='cp949', skiprows=header_idx)
             except:
                df = pd.read_csv(uploaded_file, encoding='utf-8', skiprows=header_idx)
        else:
            df = pd.read_excel(uploaded_file, skiprows=header_idx)
            
        return normalize_columns(df)
        
    except Exception as e:
        st.error(f"파일 읽기 오류 ({uploaded_file.name}): {e}")
        return None

def process_data(files):
    all_hang = []
    all_kyo = []

    for file in files:
        df = load_data(file)
        if df is None: continue
        
        # 필수 컬럼 확인으로 파일 유형 분류
        cols = df.columns.tolist()
        
        # 공통 전처리: 번호가 없는 행 제거 (결재란 등 쓰레기 데이터)
        if '번호' in cols:
            df = df.dropna(subset=['번호'])
            try:
                df['번호'] = pd.to_numeric(df['번호'], errors='coerce')
                df = df.dropna(subset=['번호'])
                df['번호'] = df['번호'].astype(int)
            except:
                pass
        
        # 유형 1: 행동특성 (행동특성 컬럼 존재)
        # 보통 '행동특성및종합의견' 이름이 다양할 수 있으니 키워드로 찾음
        hang_col = next((c for c in cols if '행동특성' in c), None)
        
        if hang_col:
            # 필요한 컬럼만 추출
            target_cols = ['번호', '성명', '학년', hang_col]
            # 파일에 학년이 없으면 파일명이나 추론이 필요하나, 보통 NEIS 다운 파일엔 있음.
            # 없으면 NaN 처리
            available_cols = [c for c in target_cols if c in df.columns]
            temp_df = df[available_cols].copy()
            temp_df.rename(columns={hang_col: '내용'}, inplace=True)
            if '학년' not in temp_df.columns: temp_df['학년'] = '' # 학년 정보 없으면 공란
            all_hang.append(temp_df)
            
        # 유형 2: 교과세특 (과목, 세부능력 컬럼 존재)
        kyo_col = next((c for c in cols if '세부능력' in c), None)
        subj_col = next((c for c in cols if '과목' in c), None)
        
        if kyo_col and subj_col:
            target_cols = ['번호', '성명', '학년', '학기', subj_col, kyo_col]
            available_cols = [c for c in target_cols if c in df.columns]
            temp_df = df[available_cols].copy()
            temp_df.rename(columns={kyo_col: '내용', subj_col: '과목'}, inplace=True)
            all_kyo.append(temp_df)

    # --- 데이터 병합 및 정리 ---
    
    result_dfs = {}

    # 1. 행동특성 정리
    if all_hang:
        df_hang_total = pd.concat(all_hang)
        # 포맷팅: [n학년] 내용
        df_hang_total['formatted'] = df_hang_total.apply(
            lambda x: f"[{x['학년']}학년] {x['내용']}" if str(x['학년']).strip() else f"{x['내용']}", axis=1
        )
        # 같은 번호끼리 묶기
        df_hang_grouped = df_hang_total.groupby(['번호', '성명'])['formatted'].apply(lambda x: '\n\n'.join(x)).reset_index()
        # 정렬: 번호순
        df_hang_grouped = df_hang_grouped.sort_values(by='번호')
        df_hang_grouped.columns = ['번호', '성명', '행동특성_통합']
        result_dfs['행동특성_정리'] = df_hang_grouped

    # 2. 교과세특 정리
    if all_kyo:
        df_kyo_total = pd.concat(all_kyo)
        
        # 내부 정렬 기준: 과목명 -> 학기 (groupby 전에 정렬해야 합칠 때 순서가 유지됨)
        # 학기 컬럼이 비어있을 수 있으므로 처리
        df_kyo_total['학기'] = df_kyo_total['학기'].fillna(0)
        df_kyo_total = df_kyo_total.sort_values(by=['번호', '과목', '학기'])
        
        # 포맷팅: [과목 | n학년 n학기] 내용
        def format_kyo(row):
            meta_info = f"{row['과목']}"
            if pd.notnull(row['학년']) and str(row['학년']).strip():
                meta_info += f" | {row['학년']}학년"
            if pd.notnull(row['학기']) and str(row['학기']) not in ['0', '0.0', '']:
                meta_info += f" {row['학기']}학기"
            return f"[{meta_info}]\n{row['내용']}"

        df_kyo_total['formatted'] = df_kyo_total.apply(format_kyo, axis=1)
        
        # 같은 번호끼리 묶기 (학생 1명 = 1줄)
        df_kyo_grouped = df_kyo_total.groupby(['번호', '성명'])['formatted'].apply(lambda x: '\n\n'.join(x)).reset_index()
        
        # 최종 정렬: 번호순 (요청하신 '과목순-학기순'은 텍스트가 합쳐지는 순서에 반영됨)
        df_kyo_grouped = df_kyo_grouped.sort_values(by='번호')
        df_kyo_grouped.columns = ['번호', '성명', '과목세특_통합']
        result_dfs['세부능력_정리'] = df_kyo_grouped

    return result_dfs

# --- UI 및 실행 로직 ---

uploaded_files = st.file_uploader("엑셀 또는 CSV 파일들을 업로드하세요 (복수 선택 가능)", 
                                  type=['xlsx', 'xls', 'csv'], 
                                  accept_multiple_files=True)

if uploaded_files:
    if st.button("파일 분석 및 변환하기"):
        with st.spinner('파일을 분석하고 데이터를 병합하는 중입니다...'):
            results = process_data(uploaded_files)
            
            if not results:
                st.error("처리할 수 있는 유효한 데이터가 없습니다. 파일 내용을 확인해주세요.")
            else:
                st.success("변환이 완료되었습니다!")
                
                # 엑셀 다운로드 준비
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    for sheet_name, df in results.items():
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
                        
                        # (선택) 엑셀 스타일링: 줄바꿈 허용 및 컬럼 넓이 조절
                        workbook = writer.book
                        worksheet = writer.sheets[sheet_name]
                        text_format = workbook.add_format({'text_wrap': True, 'valign': 'top'})
                        
                        # 컬럼 너비 설정 (번호: 5, 성명: 10, 내용: 80)
                        worksheet.set_column('A:A', 5, text_format)
                        worksheet.set_column('B:B', 10, text_format)
                        worksheet.set_column('C:C', 80, text_format)

                output.seek(0)
                
                st.download_button(
                    label="📥 통합 엑셀 파일 다운로드",
                    data=output,
                    file_name="학생부_통합_정리.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
                # 미리보기
                st.markdown("### 결과 미리보기")
                for name, df in results.items():
                    st.subheader(f"📑 {name}")
                    st.dataframe(df.head())
