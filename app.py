import streamlit as st
import pandas as pd
import re

# -----------------------------------------------------------------------------
# 1. 공통 함수: 학년 반 추출
# -----------------------------------------------------------------------------
def extract_grade_class(df_raw):
    """
    데이터프레임 상단(10행 이내)에서 '1학년 1반' 같은 패턴을 찾아 반환합니다.
    못 찾으면 '미상'을 반환합니다.
    """
    for i in range(min(10, len(df_raw))):
        row_values = df_raw.iloc[i].astype(str).values
        for val in row_values:
            match = re.search(r"(\d+)학년\s*(\d+)반", val)
            if match:
                return match.group(0) # 예: "1학년 1반"
    return "미상"

# -----------------------------------------------------------------------------
# 2. 행동특성 및 종합의견(Hang) 처리 함수
# -----------------------------------------------------------------------------
def process_hang_file(uploaded_file):
    # 헤더 위치를 찾기 위해 앞부분을 읽음
    df_raw = pd.read_csv(uploaded_file, header=None)
    grade_class = extract_grade_class(df_raw)
    
    # 실제 헤더('번 호'가 있는 행) 찾기
    header_idx = -1
    for i, row in df_raw.iterrows():
        if '번 호' in row.values and '성  명' in row.values:
            header_idx = i
            break
            
    if header_idx == -1:
        st.error("행동특성 파일에서 헤더를 찾을 수 없습니다.")
        return None

    # 헤더를 적용하여 다시 로드
    df = pd.read_csv(uploaded_file, header=header_idx)
    
    # 컬럼 공백 제거 (예: "번 호" -> "번호")
    df.columns = [str(col).replace(" ", "") for col in df.columns]
    
    # 필요한 컬럼만 선택 ('번호', '성명', '행동특성및종합의견')
    # 파일마다 컬럼명이 조금 다를 수 있으므로 확인
    target_cols = ['번호', '성명', '행동특성및종합의견']
    
    # 실제 존재하는 컬럼 매핑
    col_mapping = {}
    for col in df.columns:
        if '번호' in col: col_mapping[col] = '번호'
        elif '성명' in col: col_mapping[col] = '성명'
        elif '행동특성' in col: col_mapping[col] = '내용' # 컬럼명을 '내용'으로 통일
    
    df = df.rename(columns=col_mapping)
    
    # 필수 컬럼이 있는지 확인
    if '번호' not in df.columns or '내용' not in df.columns:
        return None

    # 1. 불필요한 행 제거 (헤더 반복, 날짜, 페이지 번호 등)
    # 번호가 숫자가 아니거나 NaN인 경우 제거 (단, 내용이 이어진 경우를 위해 처리 필요)
    # 로직: '번호'가 있고 '성명'이 있으면 새로운 학생 시작.
    # '번호'가 NaN인데 '내용'만 있으면 이전 학생의 내용 연결.
    
    df['번호'] = pd.to_numeric(df['번호'], errors='coerce') # 숫자가 아니면 NaN
    
    # 번호와 성명을 아래로 채우기 (페이지 넘김으로 분리된 행 처리용)
    # 주의: 원본 엑셀에서 페이지가 넘어가면 '번호'가 다시 나오지 않고 내용만 나오는 경우가 있음.
    # 하지만 이 파일 구조상 중간에 헤더가 반복되므로, 헤더행을 먼저 날려야 함.
    
    # '내용' 컬럼이 비어있지 않은 행만 살리되, 헤더 반복행 제거
    df = df[df['내용'].notna()]
    df = df[~df['내용'].str.contains('행 동 특 성', na=False)] # 헤더 텍스트 제거
    
    # 번호 채우기 (Forward Fill)
    df['번호'] = df['번호'].ffill()
    
    # 번호가 여전히 없는 행(문서 꼬리말 등) 제거
    df = df.dropna(subset=['번호'])
    
    # 2. 내용 합치기 (행 분리된 텍스트 병합)
    # 번호 기준으로 그룹화하여 내용 합침
    df_grouped = df.groupby('번호')['내용'].apply(lambda x: ' '.join(x.astype(str))).reset_index()
    
    # 3. 최종 포맷 만들기
    df_grouped['학년 반'] = grade_class
    df_grouped['학기'] = '' # 행동특성은 보통 학기 구분 없음 (또는 1,2학기 통합)
    df_grouped['과목/영역'] = '' # 과목 없음
    
    # 4. 정렬: 번호 순
    df_grouped = df_grouped.sort_values(by='번호')
    
    # 컬럼 순서 정리
    final_cols = ['학년 반', '번호', '학기', '과목/영역', '내용']
    return df_grouped[final_cols]

# -----------------------------------------------------------------------------
# 3. 세부능력 및 특기사항(Kyo) 처리 함수
# -----------------------------------------------------------------------------
def process_kyo_file(uploaded_file):
    df_raw = pd.read_csv(uploaded_file, header=None)
    grade_class = extract_grade_class(df_raw)
    
    # 헤더 찾기
    header_idx = -1
    for i, row in df_raw.iterrows():
        if '과 목' in row.values and '성  명' in row.values:
            header_idx = i
            break
            
    if header_idx == -1:
        st.error("세특 파일에서 헤더를 찾을 수 없습니다.")
        return None

    df = pd.read_csv(uploaded_file, header=header_idx)
    df.columns = [str(col).replace(" ", "") for col in df.columns] # 공백 제거
    
    # 컬럼 매핑
    # 예상 컬럼: 과목, 학년, 학기, 번호, 성명, 세부능력및특기사항
    rename_map = {}
    for col in df.columns:
        if '과목' in col: rename_map[col] = '과목/영역'
        elif '학기' in col: rename_map[col] = '학기'
        elif '번호' in col: rename_map[col] = '번호'
        elif '세부능력' in col: rename_map[col] = '내용'
    
    df = df.rename(columns=rename_map)
    
    # 데이터 정제
    # 1. 헤더 반복 및 불필요한 행 제거
    df['번호'] = pd.to_numeric(df['번호'], errors='coerce')
    
    # 과목, 학기, 번호 Forward Fill (페이지 넘김 대응)
    # 주의: 중간에 끼어든 헤더 행('과목', '학기' 등이 적힌 행)은 fill하기 전에 제외해야 꼬이지 않음
    # 하지만 fill을 해야 헤더인지 알 수 있는 경우도 있음.
    # 전략: 일단 내용을 기준으로 필터링 후 ffill
    
    # 의미 없는 행 제거 (내용이 NaN인 경우) -> 단, 내용이 다음 줄로 넘어간 경우 내용이 NaN일 수 있나?
    # 분석 결과: 세특은 보통 [과목, ..., 내용]이 한 줄에 있거나, 내용만 다음 줄에 있음.
    # 내용만 있는 줄은 과목, 번호가 NaN임.
    
    # 우선 '내용'이 있는 행만 남기기 전에, 번호가 있는 행을 기준으로 ffill을 해야 함.
    # 그러나 중간에 '페이지 번호'나 '학교명' 등은 번호도 없고 내용도 쓸모 없음.
    
    # 과목/영역이 '과목'인 행(반복 헤더) 제거
    df = df[df['과목/영역'] != '과 목']
    df = df[df['과목/영역'] != '과목']
    
    # ffill 수행
    df['번호'] = df['번호'].ffill()
    df['과목/영역'] = df['과목/영역'].ffill()
    df['학기'] = df['학기'].ffill()
    
    # 번호가 NaN인 행은(맨 위 헤더 이전의 쓰레기값) 제거
    df = df.dropna(subset=['번호'])
    
    # 내용이 비어있지 않은 행만 선택 (페이지 번호 등 제거)
    df = df.dropna(subset=['내용'])
    
    # 2. 내용 합치기 (행 분리 병합)
    # 그룹 키: 번호, 학기, 과목
    df_grouped = df.groupby(['번호', '학기', '과목/영역'])['내용'].apply(lambda x: ' '.join(x.astype(str))).reset_index()
    
    # 3. 최종 포맷
    df_grouped['학년 반'] = grade_class
    
    # 4. 정렬: 과목명 - 번호 순
    df_grouped = df_grouped.sort_values(by=['과목/영역', '번호'])
    
    final_cols = ['학년 반', '번호', '학기', '과목/영역', '내용']
    return df_grouped[final_cols]

# -----------------------------------------------------------------------------
# 메인 UI
# -----------------------------------------------------------------------------
st.title("🏫 생기부(행특/세특) 정리 도구")
st.markdown("""
**사용 방법:**
1. 엑셀에서 변환된 **CSV 파일**을 업로드하세요.
2. 페이지 넘김으로 분리된 텍스트가 합쳐지고, 불필요한 행이 제거됩니다.
3. **학생 이름은 자동으로 익명화**됩니다.
""")

col1, col2 = st.columns(2)

with col1:
    st.subheader("1. 행동특성(행특) 파일")
    file_hang = st.file_uploader("행동특성 CSV 업로드", type=['csv'], key='hang')

with col2:
    st.subheader("2. 세부능력(세특) 파일")
    file_kyo = st.file_uploader("세특 CSV 업로드", type=['csv'], key='kyo')

if st.button("파일 처리 및 결과 보기"):
    result_dfs = []
    
    if file_hang:
        try:
            file_hang.seek(0)
            df_hang = process_hang_file(file_hang)
            if df_hang is not None:
                st.success(f"행동특성 처리 완료: {len(df_hang)}명 데이터")
                result_dfs.append(df_hang)
        except Exception as e:
            st.error(f"행동특성 처리 중 오류 발생: {e}")

    if file_kyo:
        try:
            file_kyo.seek(0)
            df_kyo = process_kyo_file(file_kyo)
            if df_kyo is not None:
                st.success(f"세특 처리 완료: {len(df_kyo)}건 데이터")
                result_dfs.append(df_kyo)
        except Exception as e:
            st.error(f"세특 처리 중 오류 발생: {e}")

    if result_dfs:
        # 두 결과 합치기 (행특 + 세특)
        final_df = pd.concat(result_dfs, ignore_index=True)
        
        # 학년 반 - 번호 순으로 최종 정렬하고 싶다면 아래 주석 해제 (현재 요구사항은 파일별 정렬)
        # final_df = final_df.sort_values(by=['번호']) 
        
        st.write("### 처리 결과 미리보기")
        st.dataframe(final_df)
        
        # 다운로드 버튼
        # CSV 변환
        csv = final_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="CSV로 다운로드",
            data=csv,
            file_name='생기부_정리_완료.csv',
            mime='text/csv',
        )
    else:
        st.warning("처리할 파일이 없거나 오류가 발생했습니다.")
