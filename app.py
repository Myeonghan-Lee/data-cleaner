import streamlit as st
import pandas as pd
import io

# --- 페이지 설정 ---
st.set_page_config(page_title="NEIS 학생부 데이터 통합 도구", layout="wide")

st.title("📊 학생부(행동특성/세특) 데이터 통합 정리 도구")
st.markdown("""
**[사용 안내]**
1. 엑셀(xls, xlsx) 또는 CSV 파일을 업로드하세요.
2. 파일 내용의 '번 호', '성 명' 등의 위치를 자동으로 찾아 데이터를 정리합니다.
3. **행동특성**은 [학년]별로, **세특**은 [과목]별로 묶어 학생 1명당 1줄로 만듭니다.
""")

# --- 함수 정의 ---

def find_header_row(df_raw):
    """
    데이터프레임 상단 20줄을 검사하여 
    '번호'와 '성명'이 포함된(공백 무시) 행을 헤더로 간주하고 인덱스 반환
    """
    for i in range(min(20, len(df_raw))):
        # 해당 행의 모든 값을 문자열로 합치고 공백 제거
        row_str = "".join(df_raw.iloc[i].astype(str).tolist()).replace(" ", "").replace("\n", "")
        
        # '번호'와 '성명'이라는 글자가 모두 들어있으면 헤더로 판단
        if "번호" in row_str and "성명" in row_str:
            return i
    return None

def normalize_columns(df):
    """컬럼명에서 공백과 줄바꿈을 제거하여 표준화"""
    # 컬럼이 숫자로 된 경우(헤더를 못 찾은 경우) 대비
    df.columns = df.columns.astype(str).str.replace(' ', '').str.replace('\n', '').str.strip()
    return df

def load_data(uploaded_file):
    """업로드된 파일을 읽어서 적절한 헤더를 찾아 DataFrame으로 반환"""
    file_ext = uploaded_file.name.split('.')[-1].lower()
    
    try:
        # 1. 일단 헤더 없이 전체를 읽음 (데이터 위치 파악용)
        if file_ext == 'csv':
            try:
                df_raw = pd.read_csv(uploaded_file, encoding='cp949', header=None)
            except:
                df_raw = pd.read_csv(uploaded_file, encoding='utf-8', header=None)
        else:
            df_raw = pd.read_excel(uploaded_file, header=None)
            
        # 2. 실제 헤더가 있는 행 찾기
        header_idx = find_header_row(df_raw)
        
        if header_idx is None:
            # 헤더를 못 찾으면 처리 불가
            return None
        
        # 3. 찾은 위치(header_idx)를 헤더로 하여 다시 읽기
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
    
    debug_logs = [] # 디버깅용 로그

    for file in files:
        df = load_data(file)
        if df is None: 
            debug_logs.append(f"❌ {file.name}: '번호', '성명' 헤더를 찾을 수 없음")
            continue
        
        cols = df.columns.tolist()
        
        # 필수 컬럼 확인 (공백 제거된 상태)
        if '번호' not in cols or '성명' not in cols:
            debug_logs.append(f"❌ {file.name}: 필수 컬럼(번호, 성명) 누락. (발견된 컬럼: {cols})")
            continue

        # 번호 컬럼 숫자 변환 (결재란 등 문자열 제거)
        try:
            df['번호'] = pd.to_numeric(df['번호'], errors='coerce')
            df = df.dropna(subset=['번호']) # 번호 없는 행 삭제
            df['번호'] = df['번호'].astype(int)
        except:
            debug_logs.append(f"⚠️ {file.name}: 번호 컬럼 변환 중 오류 발생")
            continue
        
        # 유형 1: 행동특성 (행동특성... 컬럼 존재 여부 확인)
        # '행동특성및종합의견' 처럼 긴 이름일 수 있으므로 포함 여부로 확인
        hang_col = next((c for c in cols if '행동특성' in c), None)
        
        if hang_col:
            debug_logs.append(f"✅ {file.name}: 행동특성 파일로 인식")
            target_cols = ['번호', '성명', '학년', hang_col]
            available_cols = [c for c in target_cols if c in df.columns]
            temp_df = df[available_cols].copy()
            temp_df.rename(columns={hang_col: '내용'}, inplace=True)
            if '학년' not in temp_df.columns: temp_df['학년'] = ''
            all_hang.append(temp_df)
            continue # 행동특성이면 세특 검사 건너뜀
            
        # 유형 2: 교과세특 (세부능력... 및 과목 컬럼 존재 여부 확인)
        kyo_col = next((c for c in cols if '세부능력' in c), None)
        subj_col = next((c for c in cols if '과목' in c), None)
        
        if kyo_col and subj_col:
            debug_logs.append(f"✅ {file.name}: 교과세특 파일로 인식")
            target_cols = ['번호', '성명', '학년', '학기', subj_col, kyo_col]
            available_cols = [c for c in target_cols if c in df.columns]
            temp_df = df[available_cols].copy()
            temp_df.rename(columns={kyo_col: '내용', subj_col: '과목'}, inplace=True)
            all_kyo.append(temp_df)
        else:
             debug_logs.append(f"❓ {file.name}: 알 수 없는 파일 형식 (주요 컬럼 미발견)")

    # --- 데이터 병합 및 정리 ---
    
    result_dfs = {}

    # 1. 행동특성 정리
    if all_hang:
        df_hang_total = pd.concat(all_hang)
        # 포맷팅
        df_hang_total['formatted'] = df_hang_total.apply(
            lambda x: f"[{x['학년']}학년] {x['내용']}" if str(x['학년']).strip() else f"{x['내용']}", axis=1
        )
        # 같은 번호끼리 묶기
        df_hang_grouped = df_hang_total.groupby(['번호', '성명'])['formatted'].apply(lambda x: '\n\n'.join(x)).reset_index()
        df_hang_grouped = df_hang_grouped.sort_values(by='번호')
        df_hang_grouped.columns = ['번호', '성명', '행동특성_통합']
        result_dfs['행동특성_정리'] = df_hang_grouped

    # 2. 교과세특 정리
    if all_kyo:
        df_kyo_total = pd.concat(all_kyo)
        
        # 학기 빈값 처리
        if '학기' in df_kyo_total.columns:
            df_kyo_total['학기'] = df_kyo_total['학기'].fillna(0)
        else:
            df_kyo_total['학기'] = 0
            
        # 정렬: 번호 -> 과목 -> 학기 순
        df_kyo_total = df_kyo_total.sort_values(by=['번호', '과목', '학기'])
        
        # 포맷팅
        def format_kyo(row):
            meta_parts = [str(row['과목'])]
            if pd.notnull(row['학년']) and str(row['학년']).strip():
                meta_parts.append(f"{row['학년']}학년")
            if pd.notnull(row['학기']) and str(row['학기']) not in ['0', '0.0', '']:
                meta_parts.append(f"{row['학기']}학기")
            
            meta_info = " | ".join(meta_parts)
            return f"[{meta_info}]\n{row['내용']}"

        df_kyo_total['formatted'] = df_kyo_total.apply(format_kyo, axis=1)
        
        # 묶기
        df_kyo_grouped = df_kyo_total.groupby(['번호', '성명'])['formatted'].apply(lambda x: '\n\n'.join(x)).reset_index()
        df_kyo_grouped = df_kyo_grouped.sort_values(by='번호')
        df_kyo_grouped.columns = ['번호', '성명', '과목세특_통합']
        result_dfs['세부능력_정리'] = df_kyo_grouped

    return result_dfs, debug_logs

# --- UI 및 실행 로직 ---

uploaded_files = st.file_uploader("엑셀 또는 CSV 파일들을 업로드하세요", 
                                  type=['xlsx', 'xls', 'csv'], 
                                  accept_multiple_files=True)

if uploaded_files:
    if st.button("파일 분석 및 변환하기"):
        with st.spinner('파일을 분석하고 데이터를 병합하는 중입니다...'):
            results, logs = process_data(uploaded_files)
            
            # 로그 출력 (오류 원인 파악용)
            with st.expander("처리 로그 확인 (문제가 있다면 눌러보세요)"):
                for log in logs:
                    st.write(log)

            if not results:
                st.error("⚠️ 처리할 수 있는 데이터가 없습니다. 위의 '처리 로그'를 확인해 보세요.")
            else:
                st.success("✅ 변환이 완료되었습니다!")
                
                # 엑셀 다운로드
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    for sheet_name, df in results.items():
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
                        
                        # 스타일링
                        workbook = writer.book
                        worksheet = writer.sheets[sheet_name]
                        text_format = workbook.add_format({'text_wrap': True, 'valign': 'top'})
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
                st.markdown("---")
                for name, df in results.items():
                    st.subheader(f"📑 {name}")
                    st.dataframe(df.head())
