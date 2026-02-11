import pandas as pd
import io

def process_student_data(hang_file, kyo_file, grade_prefix):
    # 1. 파일 읽기 (헤더 위치가 다르므로 skiprows 조정)
    # 행동특성 파일: 4번째 줄이 헤더 (index 3)
    df_hang = pd.read_csv(hang_file, skiprows=3)
    # 교과세특 파일: 5번째 줄이 헤더 (index 4)
    df_kyo = pd.read_csv(kyo_file, skiprows=4)

    # 2. 컬럼명 공백 제거 및 통일 (오류 방지)
    df_hang.columns = df_hang.columns.str.replace(' ', '').str.replace('\n', '')
    df_kyo.columns = df_kyo.columns.str.replace(' ', '').str.replace('\n', '')

    # 3. 필요한 컬럼만 선택 및 정리
    # 행동특성: 번호, 성명, 행동특성및종합의견
    df_hang = df_hang[['번호', '성명', '행동특성및종합의견']].dropna(subset=['번호'])
    
    # 교과세특: 번호, 성명, 과목, 세부능력및특기사항
    df_kyo = df_kyo[['번호', '성명', '과목', '세부능력및특기사항']].dropna(subset=['번호'])

    # 4. [핵심] 교과세특 내용을 학생별로 하나로 합치기
    # 형식: "[과목명] 세특내용" 형태로 변환 후 줄바꿈으로 연결
    df_kyo['통합세특'] = '[' + df_kyo['과목'] + '] ' + df_kyo['세부능력및특기사항']
    
    # 학생별(번호, 성명)로 그룹화하여 텍스트 합치기
    df_kyo_grouped = df_kyo.groupby(['번호', '성명'])['통합세특'].apply(lambda x: '\n'.join(x)).reset_index()

    # 5. 행동특성과 교과세특 병합 (번호와 성명 기준)
    df_merged = pd.merge(df_hang, df_kyo_grouped, on=['번호', '성명'], how='left')
    
    # 6. 보기 좋게 컬럼 순서 정리
    df_merged = df_merged[['번호', '성명', '행동특성및종합의견', '통합세특']]
    df_merged.columns = ['번호', '성명', f'{grade_prefix}_행동특성', f'{grade_prefix}_과목세특_통합']
    
    return df_merged

# 파일 경로 (실제 실행 시 업로드된 파일 경로 사용)
# 예시 실행 로직
# h1_result = process_student_data('H1_hang_data.csv', 'H1_kyo_data.csv', '1학년')
# h2_result = process_student_data('H2_hang_data.csv', 'H2-kyo-data.csv', '2학년')
