import streamlit as st
import pandas as pd
import re
import io

# -----------------------------------------------------------------------------
# 1. 공통 유틸리티 함수
# -----------------------------------------------------------------------------

def load_data(uploaded_file):
    """
    업로드된 파일을 Pandas DataFrame으로 로드합니다.
    CSV와 XLSX 모두 지원합니다.
    """
    file_ext = uploaded_file.name.split('.')[-1].lower()
    
    try:
        if file_ext == 'csv':
            # CSV: 헤더 없이 읽어서 내용 분석 후 처리
            return pd.read_csv(uploaded_file, header=None)
        elif file_ext in ['xlsx', 'xls']:
            # Excel: 엔진 지정
            return pd.read_excel(uploaded_file, header=None, engine='openpyxl')
        else:
            return None
    except Exception as e:
        st.error(f"파일을 읽는 중 오류가 발생했습니다 ({uploaded_file.name}): {e}")
        return None

def extract_grade_class(df_raw):
    """
    데이터프레임 상단에서 '1학년 1반' 같은 패턴을 추출합니다.
    """
    # 상단 20행 정도만 탐색
    limit = min(20, len(df_raw))
    for i in range(limit):
        row_values = df_raw.iloc[i].astype(str).values
        for val in row_values:
            # "1학년 1반" 또는 "1학년1반" 패턴 찾기
            match = re.search(r"(\d+)학년\s*(\d+)반", val)
            if match:
                return match.group(0)
    return "미상"

def detect_file_type(df_raw):
    """
    데이터 내용을 분석하여 '행특'인지 '세특'인지 판별합니다.
    """
    # 상단 20행의 텍스트를 모두 합쳐서 키워드 검색
    limit = min(20, len(df_raw))
    text_sample = df_raw.iloc[:limit].astype(str).to_string()
    
    if "행 동 특 성" in text_sample or "행동특성" in text_sample or "종합의견" in text_sample:
        return "HANG"
    elif "세부능력" in text_sample or "특기사항" in text_sample or "과 목" in text_sample:
        return "KYO"
    else:
        return "UNKNOWN"

# -----------------------------------------------------------------------------
# 2. 데이터 처리 로직 (행특/세특)
# -----------------------------------------------------------------------------

def process_hang(df_raw, grade_class):
    """행동특성 및 종합의견 처리"""
    # 1. 실제 헤더 위치 찾기 ('번 호'와 '성 명'이 있는 행)
    header_idx = -1
    for i, row in df_raw.iterrows():
        row_str = row.astype(str).values
        if any('번' in s and '호' in s for s in row_str) and any('성' in s and '명' in s for s in row_str):
            header_idx = i
            break
            
    if header_idx == -1:
        return None

    # 헤더 설정 및 다시 로드 (슬라이싱 이용)
    df = df_raw.iloc[header_idx+1:].copy()
    df.columns = df_raw.iloc[header_idx].astype(str).str.replace(" ", "")
    
    # 컬럼 매핑 (유연하게)
    rename_map = {}
    for col in df.columns:
        if '번호' in col: rename_map[col] = '번호'
        elif '성명' in col: rename_map[col] = '성명'
        elif '행동특성' in col: rename_map[col] = '내용'
        elif '종합의견' in col: rename_map[col] = '내용'
            
    df = df.rename(columns=rename_map)
    
    # 필수 컬럼 체크
    if '번호' not in df.columns or '내용' not in df.columns:
        return None
        
    # 데이터 정제
    # 번호가 숫자가 아니거나 '내용'이 비어있는 행 처리
    df['번호'] = pd.to_numeric(df['번호'], errors='coerce')
    
    # 1. 내용이 있는 행만 남기기 (쓰레기 데이터 1차 필터)
    df = df[df['내용'].notna()]
    
    # 2. 헤더가 반복된 행 제거 ('행 동 특 성' 등의 텍스트가 내용에 있는 경우)
    #    (헤더 행은 보통 번호가 NaN이거나 문자열임. 이미 numeric변환으로 NaN됨)
    #    단, 내용 컬럼 자체가 '행 동 특 성 ...' 인 행을 제거해야 함.
    df = df[~df['내용'].str.contains('행 동 특 성', na=False)]
    df = df[~df['내용'].str.contains('종 합 의 견', na=False)]
    
    # 3. 페이지 넘김 처리 (번호 채우기)
    df['번호'] = df['번호'].ffill()
    
    # 4. 번호가 없는 행(문서 꼬리말 등) 제거
    df = df.dropna(subset=['번호'])
    
    # 5. 내용 병합 (같은 번호끼리)
    df_grouped = df.groupby('번호')['내용'].apply(lambda x: ' '.join(x.astype(str))).reset_index()
    
    # 6. 최종 포맷
    df_grouped['학년 반'] = grade_class
    df_grouped['학기'] = ''
    df_grouped['과목/영역'] = ''
    
    # 정렬: 번호 순
    df_grouped = df_grouped.sort_values(by='번호')
    
    return df_grouped[['학년 반', '번호', '학기', '과목/영역', '내용']]

def process_kyo(df_raw, grade_class):
    """세부능력 및 특기사항 처리"""
    # 1. 헤더 위치 찾기
    header_idx = -1
    for i, row in df_raw.iterrows():
        row_str = row.astype(str).values
        if any('과' in s and '목' in s for s in row_str) and any('세부능력' in s for s in row_str):
            header_idx = i
            break
            
    if header_idx == -1:
        return None
        
    df = df_raw.iloc[header_idx+1:].copy()
    df.columns = df_raw.iloc[header_idx].astype(str).str.replace(" ", "")
    
    # 컬럼 매핑
    rename_map = {}
    for col in df.columns:
        if '과목' in col: rename_map[col] = '과목/영역'
        elif '학기' in col: rename_map[col] = '학기'
        elif '번호' in col: rename_map[col] = '번호'
        elif '세부능력' in col: rename_map[col] = '내용'
        elif '특기사항' in col: rename_map[col] = '내용'
            
    df = df.rename(columns=rename_map)
    
    if '내용' not in df.columns or '과목/영역' not in df.columns:
        return None

    # 데이터 정제
    df['번호'] = pd.to_numeric(df['번호'], errors='coerce')
    
    # 1. 중간 헤더(페이지 넘김 시 반복되는 컬럼명) 제거
    df = df[df['과목/영역'] != '과 목']
    df = df[df['과목/영역'] != '과목']
    
    # 2. 값 채우기 (페이지 넘김 대응)
    df['번호'] = df['번호'].ffill()
    df['과목/영역'] = df['과목/영역'].ffill()
    df['학기'] = df['학기'].ffill()
    
    # 3. 유효한 데이터만 남기기
    df = df.dropna(subset=['번호', '내용'])
    
    # 4. 내용 병합 (번호, 학기, 과목 기준)
    #    과목명이 같고 번호가 같으면 내용은 합쳐져야 함 (페이지 분리 시)
    df_grouped = df.groupby(['번호', '학기', '과목/영역'])['내용'].apply(lambda x: ' '.join(x.astype(str))).reset_index()
    
    # 5. 최종 포맷
    df_grouped['학년 반'] = grade_class
    
    # 정렬: 과목명 - 번호 순
    df_grouped = df_grouped.sort_values(by=['과목/영역', '번호'])
    
    return df_grouped[['학년 반', '번호', '학기', '과목/영역', '내용']]

# -----------------------------------------------------------------------------
# 3. 메인 앱 UI
# -----------------------------------------------------------------------------
st.set_page_config(page_title="생기부 정리 마법사", layout="wide")

st.title("🏫 생기부(행특/세특) 원클릭 정리")
st.markdown("""
**안내:**
1. 엑셀(xlsx) 또는 CSV 파일을 **한꺼번에 업로드**하세요. (여러 파일 가능)
2. 자동으로 **행동특성**인지 **세부능력**인지 구분하여 정리합니다.
3. 결과는 **미리보기**로 확인하고 **하나의 파일**로 다운로드할 수 있습니다.
""")

uploaded_files = st.file_uploader(
    "파일을 이곳에 드래그하거나 선택하세요 (XLSX, CSV 지원)", 
    accept_multiple_files=True,
    type=['xlsx', 'xls', 'csv']
)

if uploaded_files:
    all_results = []
    
    # 진행 상황 표시
    progress_text = st.empty()
    
    for file in uploaded_files:
        progress_text.text(f"처리 중: {file.name}...")
        
        # 1. 파일 로드
        df_raw = load_data(file)
        if df_raw is None:
            continue
            
        # 2. 정보 추출
        grade_class = extract_grade_class(df_raw)
        file_type = detect_file_type(df_raw)
        
        # 3. 타입별 처리
        processed_df = None
        if file_type == 'HANG':
            processed_df = process_hang(df_raw, grade_class)
        elif file_type == 'KYO':
            processed_df = process_kyo(df_raw, grade_class)
        else:
            st.warning(f"⚠️ '{file.name}' 파일 형식을 인식할 수 없습니다. (행동특성 또는 세부능력 텍스트가 포함되어야 함)")
            continue
            
        if processed_df is not None and not processed_df.empty:
            all_results.append(processed_df)
            st.success(f"✅ {file.name} ({grade_class}, {file_type}) - {len(processed_df)}명 처리 완료")
        else:
            st.warning(f"⚠️ {file.name} 처리 실패: 유효한 데이터가 없거나 구조가 다릅니다.")

    progress_text.empty()

    # 결과 통합 및 다운로드
    if all_results:
        # 통합
        final_df = pd.concat(all_results, ignore_index=True)
        
        # 최종 정렬 (사용자 요청: 세특은 과목-번호, 행특은 번호)
        # 이미 개별 처리 시 정렬했으나, 합쳐졌으므로 다시 정렬 필요
        # 하지만 행특/세특 정렬 기준이 다르므로, 섞지 않고 '과목/영역' 유무로 구분해서 보여주는 게 나을 수 있음.
        # 여기서는 파일별로 처리된 순서(리스트 순서)대로 합쳐지되, 
        # 사용자가 보기 편하게 [학년반 -> 번호 -> 과목] 순으로 전체 정렬을 한 번 더 하는 것을 추천하지만,
        # 사용자의 "정렬 방법" 조건을 엄격히 지키기 위해 그대로 둡니다.
        # (각 파트별로 이미 정렬되어 있음)
        
        st.divider()
        st.subheader("📊 처리 결과 미리보기")
        st.dataframe(final_df, use_container_width=True)
        
        # CSV 변환
        csv_buffer = io.BytesIO()
        final_df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
        csv_data = csv_buffer.getvalue()
        
        st.download_button(
            label="📥 정리된 파일 다운로드 (CSV)",
            data=csv_data,
            file_name="생기부_정리_완료.csv",
            mime="text/csv"
        )
