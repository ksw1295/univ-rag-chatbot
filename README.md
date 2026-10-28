# 대학 RAG 챗봇 (univ-rag-chatbot)

여러 대학의 공개 규정 자료(학칙, 장학 규정, 학사 규정)를 근거로 질문에 답변하는 RAG(검색 증강 생성) 챗봇입니다.

---

## 1. 개요 및 설계 원칙
* **학교 설정 기반 확장**: 각 학교는 `schools/<school_id>.yaml` 설정 파일 하나로 관리됩니다.
* **단일 벡터 컬렉션 & 메타데이터 필터**: 모든 문서는 단일 Chroma 컬렉션에 적재되며, 질의 시 `school_id` 메타데이터 필터링을 통해 학교 간 데이터 혼선을 원천 차단합니다.
* **근거 기반 답변**: 주어진 참고자료에 명시된 내용으로만 답변하며, 자료에 없거나 검색 유사도가 낮을 경우 답변을 지어내지 않고 학교별 문의처로 안내합니다.
* **표(Table) 구조 보존**: `pdfplumber`를 이용해 격자형 표를 Markdown Table 형식의 독립 청크로 추출합니다.

---

## 2. 설치 방법 (Python 3.11 이상 권장)

### (1) 가상환경 생성 및 패키지 설치
```bash
# 가상환경 생성 (uv 또는 python venv 사용)
python -m uv venv .venv --python 3.12
# 또는: python -m venv .venv

# 가상환경 활성화 (Windows)
.venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
```

### (2) 환경 변수 설정
LLM 응답 생성을 위해 프로젝트 루트 디렉터리에 `.env` 파일을 생성하고 Gemini API 키를 설정합니다.
```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
```
*(주의: 검색 유사도가 임계값 미만인 경우 LLM을 호출하지 않고 즉시 문의처를 안내하므로, API 키 없이도 필터링 기능은 정상 작동합니다.)*

---

## 3. 자료 넣는 법
자료는 학교 홈페이지의 `robots.txt` 준수 여부를 확인한 후, 직접 수동 다운로드하여 아래 경로 규칙에 맞춰 배치합니다.
```
data/raw/<school_id>/
├── original/               # 수동 다운로드한 원본 HWP/HWPX 파일
└── <doc_type>_<학년도>.pdf # PDF 변환본 (doc_type: rule / scholarship / academic)
```

예시:
* `data/raw/kornu/rule_2026.pdf` (나사렛대학교 학칙)
* `data/raw/kornu/scholarship_2026.pdf` (나사렛대학교 장학 규정)
* `data/raw/kornu/academic_2026.pdf` (나사렛대학교 학사에 관한 규정)
* `data/raw/cnsu/rule_2026.pdf` (충남도립대학교 학칙)
* `data/raw/cnsu/scholarship_2024.pdf` (충남도립대학교 장학 규정)
* `data/raw/cnsu/academic_2025.pdf` (충남도립대학교 학칙 시행세칙)

---

## 4. 실행 순서

### Step 1: 문서 파싱 및 조각(청킹) 생성
PDF 파일에서 본문(`제N조` 단위 분할) 및 표(Markdown 형식)를 추출하여 `data/chunks.jsonl`에 저장합니다.
```bash
python -m src.ingest
```
* 출력: 학교별 총 조각 수, 본문 조각 수, 표 조각 수

### Step 2: 벡터 임베딩 및 Chroma DB 인덱싱
로컬 한국어 임베딩 모델(`nlpai-lab/KURE-v1`)을 통해 조각별 벡터를 생성하고 Chroma DB에 저장합니다. CUDA를 쓸 수 있으면 GPU, 아니면 CPU로 돌며 `UNIV_RAG_DEVICE=cpu` 처럼 직접 지정할 수도 있습니다. CPU에서는 수 분이 걸립니다.
```bash
python -m src.index            # 자료(학교·파일) 단위로 옛 기록을 지우고 다시 넣음
python -m src.index --reset    # 컬렉션을 통째로 지우고 처음부터
```
* 출력: 진행률(경과 초), 최종 저장된 레코드 수, 걸린 시간

### Step 3: 질문 및 답변 질의 (ask)
특정 학교 ID를 지정하여 질문하고, 검색된 문맥을 바탕으로 답변을 받습니다.
```bash
# 나사렛대학교 질의 예시
python -m src.ask --school kornu "나사렛대학교의 3대 교육목표는 무엇인가요?"

# 충남도립대학교 질의 예시
python -m src.ask --school cnsu "충남도립대학교 본교의 위치는 어디인가요?"

# 검색된 조각(거리·문서·조항)도 같이 보기
python -m src.ask --school cnsu --sources "충남도립대학교 본교의 위치는 어디인가요?"
```

### Step 4: 검색 정확도 평가 (Hit@3)
골든 질문 세트(`eval/questions_<학교ID>.jsonl`)를 대상으로 상위 3개 검색 결과에 **정답 문서(`expected_source`)의 정확한 조항(`expected_article`)**이 있는지(Hit@3) 평가합니다. 자료에 없는 질문(`type: unanswerable`)은 임계값(0.35)에서 실제로 걸러지는지 함께 보여 줍니다.
> **참고**: 현재 평가 문항은 규정 원문을 기반으로 생성된 **사람 확인 전 초안**입니다.
```bash
python -m eval.run_eval
```
