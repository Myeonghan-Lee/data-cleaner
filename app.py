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
    """파일 유형 감지 (행특 / 세특 / 창체)"""
    limit = min(20, len(df_raw))
    text_sample = df_raw.iloc[:limit].astype(str).to_string()
    
    if "창의적" in text_sample and ("체험활동" in text_sample or "자율" in text_sample):
        return "CHANG" # 창의적 체험활동
    elif "행 동 특 성" in text_sample or "행동특성" in text_sample or "종합의견" in text_sample:
        return "HANG" # 행동특성
    elif "세부능력" in text_sample or "특기사항" in text_sample or "과 목" in text_sample:
        return "KYO" # 세부능력(교과)
    else:
        return "UNKNOWN"

# -----------------------------------------------------------------------------
# 2. 데이터 처리 로직 (행특 / 세특 / 창체)
# -----------------------------------------------------------------------------

def process_hang(df_raw, grade_class):
    """행동특성 처리"""
    # 헤더 찾기
    header_idx = -1
    for i, row in df_raw.iterrows():
        row_str = row.astype(str).values
        if any('번' in s and '호' in s for s in row_str) and any('성' in s and '명' in s for s in row_str):
            header_idx = i
            break
    
    if header_idx == -1: return None

    df = df_raw.iloc[header_idx+1:].copy()
    df.columns = df_raw.iloc[header_idx].astype(str).str.replace(" ", "")
    
    # 컬럼 매핑
    rename_map = {}
    for col in df.columns:
        if '번호' in col: rename_map[col] = '번호'
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
    
    # 최종 포맷 맞추기
    df_grouped['학년 반'] = grade_class
    df_grouped['학기'] = ''
    df_grouped['과목/영역'] = '행동특성'
    df_grouped['시수'] = '' # 행특은 시수 없음
    
    return df_grouped[['학년 반', '번호', '학기', '과목/영역', '시수', '내용']]

def process_kyo(df_raw, grade_class):
    """세부능력(교과) 처리"""
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
    
    # 불필요한 행 제거
    df = df[df['과목/영역'] != '과 목']
    df = df[df['과목/영역'] != '과목']
    
    # 값 채우기
    df['번호'] = df['번호'].ffill()
    df['과목/영역'] = df['과목/영역'].ffill()
    df['학기'] = df['학기'].ffill()
    
    df = df.dropna(subset=['번호', '내용'])
    
    df_grouped = df.groupby(['번호', '학기', '과목/영역'])['내용'].apply(lambda x: ' '.join(x.astype(str))).reset_index()
    
    # 최종 포맷
    df_grouped['학년 반'] = grade_class
    df_grouped['시수'] = '' # 세특은 시수 없음
    
    return df_grouped[['학년 반', '번호', '학기', '과목/영역', '시수', '내용']]

def process_chang(df_raw, grade_class):
    """창의적 체험활동(자율/진로) 처리"""
    header_idx = -1
    for i, row in df_raw.iterrows():
        row_str = row.astype(str).values
        # '영 역'과 '시 간'이 포함된 헤더 찾기
        if any('영' in s and '역' in s for s in row_str) and any('시' in s and '간' in s for s in row_str):
            header_idx = i
            break
            
    if header_idx == -1: return None
        
    df = df_raw.iloc[header_idx+1:].copy()
    df.columns = df_raw.iloc[header_idx].astype(str).str.replace(" ", "")
    
    # 컬럼 매핑 (창체 특화)
    rename_map = {}
    for col in df.columns:
        if '번호' in col: rename_map[col] = '번호'
        elif '영역' in col: rename_map[col] = '과목/영역'
        elif '시간' in col: rename_map[col] = '시수'
        elif '특기사항' in col: rename_map[col] = '내용'
    
    df = df.rename(columns=rename_map)
    
    if '내용' not in df.columns or '과목/영역' not in df.columns: return None

    # 데이터 정제
    df['번호'] = pd.to_numeric(df['번호'], errors='coerce')
    
    # 1. 헤더 반복 제거
    df = df[df['과목/영역'] != '영 역']
    df = df[df['과목/영역'] != '영역']
    
    # 2. 값 채우기 (페이지 넘김 대응)
    df['번호'] = df['번호'].ffill()
    df['과목/영역'] = df['과목/영역'].ffill()
    df['시수'] = df['시수'].ffill()
    
    # 3. 유효한 데이터 필터링
    df = df.dropna(subset=['번호'])
    
    # [중요] 진로활동의 '희망분야' 행 제거
    # '내용' 컬럼에 '희망분야'라는 글자가 있거나, '조리사' 처럼 직업명만 있는 경우(보통 5글자 이하)를 주의해야 함.
    # 하지만 CSV 구조상 '희망분야' 라벨이 있는 행은 '내용' 컬럼에 '희망분야'라고 찍혀있을 확률이 높음.
    df = df[df['내용'].astype(str) != '희망분야']
    df = df[~df['내용'].astype(str).str.contains('희망분야', na=False)] # 희망분야 텍스트 포함 행 삭제
    
    # 내용이 비어있지 않은 것만 남기되, 진로활동의 경우 내용이 다음 줄에 있을 수 있으므로
    # 위에서 ffill을 했지만, 내용은 ffill하면 안됨 (서로 다른 내용이 섞임).
    # 따라서 내용은 비어있는 행을 제거해야 함.
    df = df.dropna(subset=['내용'])

    # 4. 내용 병합
    df_grouped = df.groupby(['번호', '과목/영역', '시수'])['내용'].apply(lambda x: ' '.join(x.astype(str))).reset_index()
    
    # 최종 포맷
    df_grouped['학년 반'] = grade_class
    df_grouped['학기'] = '' # 창체는 보통 학기 구분 없이 통년
    
    return df_grouped[['학년 반', '번호', '학기', '과목/영역', '시수', '내용']]


def detect_duplicates(df):
    """복붙(중복) 문장 탐지"""
    sentence_pattern = re.compile(r'[^.!?]+[.!?]')
    df['중복여부'] = False
    df['비고(중복문장)'] = ''
    
    for subject, group in df.groupby('과목/영역'):
        if len(group) < 2: continue
        
        sentence_counts = {}
        for idx, row in group.iterrows():
            content = str(row['내용'])
            sentences = [s.strip() for s in sentence_pattern.findall(content)]
            for s in sentences:
                if len(s) < 10: continue
                sentence_counts[s] = sentence_counts.get(s, 0) + 1
        
        duplicate_sentences = {s for s, count in sentence_counts.items() if count > 1}
        
        for idx, row in group.iterrows():
            content = str(row['내용'])
            sentences = [s.strip() for s in sentence_pattern.findall(content)]
            found_duplicates = [s for s in sentences if s in duplicate_sentences]
            
            if found_duplicates:
                df.at[idx, '중복여부'] = True
                unique_dupes = list(set(found_duplicates))
                df.at[idx, '비고(중복문장)'] = " / ".join(unique_dupes)

    return df

def to_excel_with_style(df):
    """엑셀 스타일링 및 저장"""
    output = io.BytesIO()
    save_cols = [c for c in df.columns if c != '중복여부']
    
    def style_duplicate(row):
        styles = [''] * len(row)
        if row.get('중복여부', False):
            try:
                content_idx = row.index.get_loc('내용')
                styles[content_idx] = 'color: red; font-weight: bold;'
            except: pass
            try:
                note_idx = row.index.get_loc('비고(중복문장)')
                styles[note_idx] = 'color: red;'
            except: pass
        return styles

    styler = df.style.apply(style_duplicate, axis=1)
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        styler.to_excel(writer, index=False, columns=save_cols, sheet_name='정리결과')
        worksheet = writer.sheets['정리결과']
        for idx, col in enumerate(save_cols):
            width = 50 if '내용' in col or '비고' in col else 10
            worksheet.column_dimensions[chr(65 + idx)].width = width
            
    return output.getvalue()

# -----------------------------------------------------------------------------
# 3. 메인 앱 UI
# -----------------------------------------------------------------------------
st.set_page_config(page_title="생기부 통합 정리 마법사", layout="wide")

st.title("🏫 생기부 통합 정리 & 복붙 탐지")
st.markdown("""
**지원 파일:** 행특, 세특(교과), 창체(자율/진로)
**기능:** 1. 엑셀/CSV 업로드 시 **자동 분류 및 정리**
2. 창체(진로)의 **'희망분야' 자동 삭제**
3. **'시수' 열 추가** 및 **과목-번호 순 정렬**
4. **복붙 의심 문장 빨간색 표시**
""")

uploaded_files = st.file_uploader(
    "처리할 파일들을 모두 올려주세요", 
    accept_multiple_files=True,
    type=['xlsx', 'xls', 'csv']
)

if uploaded_files:
    all_results = []
    
    with st.status("파일 분석 및 처리 중...", expanded=True) as status:
        for file in uploaded_files:
            df_raw = load_data(file)
            if df_raw is None:
                st.error(f"{file.name}: 읽기 실패")
                continue
                
            grade_class = extract_grade_class(df_raw)
            file_type = detect_file_type(df_raw)
            
            processed_df = None
            type_label = ""
            
            if file_type == 'HANG':
                processed_df = process_hang(df_raw, grade_class)
                type_label = "행동특성"
            elif file_type == 'KYO':
                processed_df = process_kyo(df_raw, grade_class)
                type_label = "세부능력"
            elif file_type == 'CHANG':
                processed_df = process_chang(df_raw, grade_class)
                type_label = "창의적체험"
            else:
                st.warning(f"⚠️ {file.name}: 알 수 없는 형식 (건너뜀)")
                continue
                
            if processed_df is not None and not processed_df.empty:
                all_results.append(processed_df)
                st.write(f"✅ {file.name} ({type_label} / {grade_class}) - {len(processed_df)}명 처리")
            else:
                st.warning(f"⚠️ {file.name}: 데이터 추출 실패")

        status.update(label="모든 파일 처리 완료!", state="complete", expanded=False)

    if all_results:
        # 1. 통합
        final_df = pd.concat(all_results, ignore_index=True)
        
        # 2. 정렬 (요청사항: 과목/영역 -> 번호 순)
        # 시수는 정렬에 영향 없으나 보기 좋게 포함 가능
        final_df = final_df.sort_values(by=['과목/영역', '번호'])
        
        # 3. 중복 분석
        final_df = detect_duplicates(final_df)
        
        # 4. 미리보기
        st.divider()
        st.subheader("📊 결과 미리보기")
        
        def highlight_row(row):
            return ['background-color: #ffe6e6' if row['중복여부'] else '' for _ in row]
            
        st.dataframe(
            final_df.style.apply(highlight_row, axis=1),
            column_config={
                "시수": st.column_config.TextColumn("시수", width="small"),
                "비고(중복문장)": st.column_config.TextColumn("⚠️ 복붙 의심 문장", width="medium"),
                "중복여부": None
            },
            use_container_width=True
        )
        
        # 5. 다운로드
        excel_data = to_excel_with_style(final_df)
        
        st.download_button(
            label="📥 통합 엑셀 파일 다운로드 (.xlsx)",
            data=excel_data,
            file_name="생기부_통합_정리결과.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("처리할 데이터가 없습니다.")
