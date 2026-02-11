import streamlit as st
import pandas as pd
import re
import io

# -----------------------------------------------------------------------------
# 1. 공통 유틸리티 함수
# -----------------------------------------------------------------------------

def load_data(uploaded_file):
    """파일 로드 (CSV, Excel)"""
    file_ext = uploaded_file.name.split('.')[-1].lower()
    try:
        if file_ext == 'csv':
            return pd.read_csv(uploaded_file, header=None)
        elif file_ext in ['xlsx', 'xls']:
            return pd.read_excel(uploaded_file, header=None, engine='openpyxl')
        else:
            return None
    except Exception as e:
        st.error(f"파일 오류 ({uploaded_file.name}): {e}")
        return None

def extract_grade_class(df_raw):
    """학년 반 추출"""
    limit = min(20, len(df_raw))
    for i in range(limit):
        row_values = df_raw.iloc[i].astype(str).values
        for val in row_values:
            match = re.search(r"(\d+)학년\s*(\d+)반", val)
            if match:
                return match.group(0)
    return "미상"

def detect_file_type(df_raw):
    """행특/세특 파일 유형 감지"""
    limit = min(20, len(df_raw))
    text_sample = df_raw.iloc[:limit].astype(str).to_string()
    
    if "행 동 특 성" in text_sample or "행동특성" in text_sample or "종합의견" in text_sample:
        return "HANG"
    elif "세부능력" in text_sample or "특기사항" in text_sample or "과 목" in text_sample:
        return "KYO"
    else:
        return "UNKNOWN"

# -----------------------------------------------------------------------------
# 2. 데이터 처리 및 중복 분석 로직
# -----------------------------------------------------------------------------

def process_hang(df_raw, grade_class):
    """행동특성 처리"""
    header_idx = -1
    for i, row in df_raw.iterrows():
        row_str = row.astype(str).values
        if any('번' in s and '호' in s for s in row_str) and any('성' in s and '명' in s for s in row_str):
            header_idx = i
            break
    
    if header_idx == -1: return None

    df = df_raw.iloc[header_idx+1:].copy()
    df.columns = df_raw.iloc[header_idx].astype(str).str.replace(" ", "")
    
    rename_map = {}
    for col in df.columns:
        if '번호' in col: rename_map[col] = '번호'
        elif '성명' in col: rename_map[col] = '성명'
        elif '행동특성' in col: rename_map[col] = '내용'
        elif '종합의견' in col: rename_map[col] = '내용'
    df = df.rename(columns=rename_map)
    
    if '번호' not in df.columns or '내용' not in df.columns: return None
        
    df['번호'] = pd.to_numeric(df['번호'], errors='coerce')
    df = df[df['내용'].notna()]
    df = df[~df['내용'].str.contains('행 동 특 성', na=False)]
    df = df[~df['내용'].str.contains('종 합 의 견', na=False)]
    df['번호'] = df['번호'].ffill()
    df = df.dropna(subset=['번호'])
    
    df_grouped = df.groupby('번호')['내용'].apply(lambda x: ' '.join(x.astype(str))).reset_index()
    
    df_grouped['학년 반'] = grade_class
    df_grouped['학기'] = ''
    df_grouped['과목/영역'] = '행동특성' # 행특으로 명시
    
    return df_grouped[['학년 반', '번호', '학기', '과목/영역', '내용']]

def process_kyo(df_raw, grade_class):
    """세부능력 처리"""
    header_idx = -1
    for i, row in df_raw.iterrows():
        row_str = row.astype(str).values
        if any('과' in s and '목' in s for s in row_str) and any('세부능력' in s for s in row_str):
            header_idx = i
            break
            
    if header_idx == -1: return None
        
    df = df_raw.iloc[header_idx+1:].copy()
    df.columns = df_raw.iloc[header_idx].astype(str).str.replace(" ", "")
    
    rename_map = {}
    for col in df.columns:
        if '과목' in col: rename_map[col] = '과목/영역'
        elif '학기' in col: rename_map[col] = '학기'
        elif '번호' in col: rename_map[col] = '번호'
        elif '세부능력' in col: rename_map[col] = '내용'
        elif '특기사항' in col: rename_map[col] = '내용'
    df = df.rename(columns=rename_map)
    
    if '내용' not in df.columns or '과목/영역' not in df.columns: return None

    df['번호'] = pd.to_numeric(df['번호'], errors='coerce')
    df = df[df['과목/영역'] != '과 목']
    df = df[df['과목/영역'] != '과목']
    df['번호'] = df['번호'].ffill()
    df['과목/영역'] = df['과목/영역'].ffill()
    df['학기'] = df['학기'].ffill()
    df = df.dropna(subset=['번호', '내용'])
    
    df_grouped = df.groupby(['번호', '학기', '과목/영역'])['내용'].apply(lambda x: ' '.join(x.astype(str))).reset_index()
    df_grouped['학년 반'] = grade_class
    
    return df_grouped[['학년 반', '번호', '학기', '과목/영역', '내용']]

def detect_duplicates(df):
    """
    중복 문장(복붙 의심)을 탐지하여
    1. '중복여부' (True/False)
    2. '비고(중복문장)' (겹친 문장 내용)
    컬럼을 추가함.
    """
    # 문장 분리 패턴 (마침표, 느낌표, 물음표 뒤 공백)
    sentence_pattern = re.compile(r'[^.!?]+[.!?]')
    
    # 결과 저장을 위한 컬럼 초기화
    df['중복여부'] = False
    df['비고(중복문장)'] = ''
    
    # 과목별로 그룹화하여 비교 (다른 과목 간 중복은 허용될 수 있으므로)
    # 행특은 '행동특성'이라는 과목명으로 들어와 있음.
    for subject, group in df.groupby('과목/영역'):
        if len(group) < 2: continue
        
        # 1. 모든 문장 수집 및 카운트
        sentence_counts = {}
        for idx, row in group.iterrows():
            content = str(row['내용'])
            sentences = [s.strip() for s in sentence_pattern.findall(content)]
            for s in sentences:
                if len(s) < 10: continue # 10자 미만 짧은 문장은 무시
                sentence_counts[s] = sentence_counts.get(s, 0) + 1
        
        # 2. 중복 문장 식별 (2회 이상 등장)
        duplicate_sentences = {s for s, count in sentence_counts.items() if count > 1}
        
        # 3. 각 행에 중복 정보 기록
        for idx, row in group.iterrows():
            content = str(row['내용'])
            sentences = [s.strip() for s in sentence_pattern.findall(content)]
            found_duplicates = [s for s in sentences if s in duplicate_sentences]
            
            if found_duplicates:
                df.at[idx, '중복여부'] = True
                # 중복된 문장들을 비고란에 기록 (중복 제거하여)
                unique_dupes = list(set(found_duplicates))
                df.at[idx, '비고(중복문장)'] = " / ".join(unique_dupes)

    return df

def to_excel_with_style(df):
    """
    DataFrame을 엑셀로 변환하되, '중복여부'가 True인 행의
    '내용' 셀 글자색을 빨간색으로 변경
    """
    output = io.BytesIO()
    
    # '중복여부' 컬럼은 엑셀 저장 시 제외하고 스타일링에만 사용
    save_cols = [c for c in df.columns if c != '중복여부']
    
    # Pandas Styler 사용
    def style_duplicate(row):
        # 기본 스타일
        styles = [''] * len(row)
        # 중복인 경우 '내용' 컬럼 빨간색 처리
        if row.get('중복여부', False):
            # '내용' 컬럼의 인덱스 찾기
            try:
                content_idx = row.index.get_loc('내용')
                styles[content_idx] = 'color: red; font-weight: bold;'
            except:
                pass
            
            # '비고(중복문장)' 컬럼도 빨간색
            try:
                note_idx = row.index.get_loc('비고(중복문장)')
                styles[note_idx] = 'color: red;'
            except:
                pass
                
        return styles

    # Styler 객체 생성
    styler = df.style.apply(style_duplicate, axis=1)
    
    # 엑셀 저장
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        styler.to_excel(writer, index=False, columns=save_cols, sheet_name='정리결과')
        
        # 열 너비 자동 조정 (약간의 튜닝)
        worksheet = writer.sheets['정리결과']
        for idx, col in enumerate(save_cols):
            # 내용 컬럼은 넓게, 나머지는 적당히
            width = 50 if '내용' in col or '비고' in col else 15
            worksheet.column_dimensions[chr(65 + idx)].width = width
            
    return output.getvalue()

# -----------------------------------------------------------------------------
# 3. 메인 앱 UI
# -----------------------------------------------------------------------------
st.set_page_config(page_title="생기부 정리 마법사", layout="wide")

st.title("🏫 생기부 원클릭 정리 & 복붙 탐지")
st.markdown("""
**기능 안내:**
1. **XLSX / CSV 업로드**: 파일을 올리면 자동으로 행특/세특을 구분합니다.
2. **복붙 의심 탐지**: 같은 과목 내에서 **다른 학생과 토씨 하나 안 틀리고 똑같은 문장**이 있으면 찾아냅니다.
3. **결과 다운로드**: 정리된 엑셀 파일(**.xlsx**)을 받으실 수 있으며, 의심 문장은 **빨간색**으로 표시됩니다.
""")

uploaded_files = st.file_uploader(
    "처리할 파일들을 선택하세요 (여러 개 가능)", 
    accept_multiple_files=True,
    type=['xlsx', 'xls', 'csv']
)

if uploaded_files:
    all_results = []
    
    with st.status("파일 처리 중...", expanded=True) as status:
        for file in uploaded_files:
            st.write(f"📂 {file.name} 읽는 중...")
            df_raw = load_data(file)
            
            if df_raw is None:
                st.error(f"{file.name}: 파일 읽기 실패")
                continue
                
            grade_class = extract_grade_class(df_raw)
            file_type = detect_file_type(df_raw)
            
            processed_df = None
            if file_type == 'HANG':
                processed_df = process_hang(df_raw, grade_class)
                st.write(f"  - 타입: 행동특성 / 학급: {grade_class}")
            elif file_type == 'KYO':
                processed_df = process_kyo(df_raw, grade_class)
                st.write(f"  - 타입: 세부능력 / 학급: {grade_class}")
            else:
                st.warning(f"  - {file.name}: 알 수 없는 파일 형식 (건너뜀)")
                continue
                
            if processed_df is not None and not processed_df.empty:
                all_results.append(processed_df)
            else:
                st.warning(f"  - {file.name}: 데이터 추출 실패")

        status.update(label="처리 완료!", state="complete", expanded=False)

    if all_results:
        # 1. 데이터 통합
        final_df = pd.concat(all_results, ignore_index=True)
        
        # 2. 정렬 (과목명 -> 번호)
        # 빈칸(행특)이 맨 뒤로 가게 하거나 앞으로 가게 처리 (sort_values 기본동작 활용)
        final_df = final_df.sort_values(by=['과목/영역', '번호'])
        
        # 3. 중복 문장 분석 실행
        st.write("🔍 복붙(중복) 문장 분석 중...")
        final_df = detect_duplicates(final_df)
        
        # 4. 미리보기 (스타일링 적용 전 데이터)
        st.divider()
        st.subheader("📊 결과 미리보기")
        
        # 미리보기에서는 중복 여부를 눈에 띄게 보여줌
        def highlight_row(row):
            return ['background-color: #ffe6e6' if row['중복여부'] else '' for _ in row]
            
        st.dataframe(
            final_df.style.apply(highlight_row, axis=1),
            column_config={
                "비고(중복문장)": st.column_config.TextColumn("⚠️ 복붙 의심 문장", width="medium"),
                "중복여부": None # 미리보기에서 숨김
            },
            use_container_width=True
        )
        
        # 5. 엑셀 다운로드
        excel_data = to_excel_with_style(final_df)
        
        st.download_button(
            label="📥 결과 엑셀 파일 다운로드 (.xlsx)",
            data=excel_data,
            file_name="생기부_정리_복붙체크.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        count_dupes = final_df['중복여부'].sum()
        if count_dupes > 0:
            st.error(f"⚠️ 총 {count_dupes}건의 복붙 의심 사례가 발견되었습니다. 다운로드된 파일의 빨간색 텍스트를 확인하세요.")
        else:
            st.success("✅ 복붙 의심 문장이 발견되지 않았습니다. (클린!)")
    else:
        st.info("처리할 데이터가 없습니다.")
