import os
import sys
import argparse
import yaml
import chromadb
from sentence_transformers import SentenceTransformer
from src.llm import call_llm

CHROMA_PATH = r"D:\dev\devSandbox\univ-rag-chatbot\chroma_db"
COLLECTION_NAME = "univ_regulations"
MODEL_NAME = "nlpai-lab/KURE-v1"
SCHOOLS_DIR = r"D:\dev\devSandbox\univ-rag-chatbot\schools"
DISTANCE_THRESHOLD = 0.35  # 코사인 거리 기준 (이보다 크면 검색 유사도 부족으로 판정하여 LLM 미호출)



def load_school_config(school_id: str) -> dict:
    yaml_path = os.path.join(SCHOOLS_DIR, f"{school_id}.yaml")
    if not os.path.exists(yaml_path):
        raise FileNotFoundError(f"학교 설정 파일을 찾을 수 없습니다: {yaml_path}")
    with open(yaml_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def ask_question(school_id: str, query: str, top_k: int = 5) -> str:
    # 1. 학교 설정 로드
    cfg = load_school_config(school_id)
    school_name = cfg.get("name", school_id)
    contact = cfg.get("contact", "").strip() or "해당 부서"

    # 2. Chroma DB 및 임베딩 모델 연결
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_collection(name=COLLECTION_NAME)
    model = SentenceTransformer(MODEL_NAME, device="cpu")

    # 3. 질문 임베딩 생성 및 검색 (where={'school_id': school_id} 필수 필터)
    query_emb = model.encode([query], normalize_embeddings=True).tolist()
    results = collection.query(
        query_embeddings=query_emb,
        n_results=top_k,
        where={"school_id": {"$eq": school_id}}
    )

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    if not docs:
        return f"자료에서 찾지 못함, {contact}로 문의"

    # 4. 검색 점수 임계값 검사 (가장 유사한 문서의 코사인 거리)
    best_distance = distances[0]
    if best_distance > DISTANCE_THRESHOLD:
        return (
            f"자료에서 찾지 못함, {contact}로 문의\n\n"
            f"(최고 유사도 거리 {best_distance:.4f}가 임계값 {DISTANCE_THRESHOLD}보다 커서 LLM 호출을 생략했습니다.)"
        )

    # 5. 프롬프트 구성 (학교 정보, 컨텍스트, 질문)
    contexts = []
    sources_summary = []
    for idx, (doc, meta, dist) in enumerate(zip(docs, metas, distances), start=1):
        src = meta.get("source", "")
        art = meta.get("article", "")
        yr = meta.get("year", "")
        pg = meta.get("page", "")
        ref = f"문서: {src}, 조항: {art or '본문/표'}, 학년도: {yr}년, 쪽: {pg}쪽"
        contexts.append(f"[자료 {idx}] ({ref})\n{doc}")
        sources_summary.append(ref)

    context_str = "\n\n".join(contexts)

    prompt = f"""당신은 {school_name} 규정 및 학사/장학 안내 전문 챗봇입니다.
반드시 아래 제공된 [참고자료]의 내용에만 근거하여 질문에 사실대로 명확하게 답변하십시오.
제공된 자료에 언급되지 않은 사실을 추측하여 답변하거나 외부 지식을 지어내지 마십시오.
만약 주어진 자료만으로 질문에 대한 명확한 근거를 찾을 수 없다면 반드시 "자료에서 찾지 못함, {contact}로 문의"라고 답변하십시오.

답변 마지막에는 반드시 답변의 근거가 된 출처(문서명, 조항, 학년도, 쪽)를 명시하십시오.

[참고자료]
{context_str}

[질문]
{query}

[답변]"""

    # 6. LLM 호출
    answer = call_llm(prompt)
    return answer.strip()


def main():
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="대학 규정/학사 RAG 챗봇 질의")
    parser.add_argument("--school", required=True, help="학교 ID (예: kornu, cnsu)")
    parser.add_argument("query", help="질문 내용")
    args = parser.parse_args()

    answer = ask_question(args.school, args.query)
    print(f"\n[학교]: {args.school}")
    print(f"[질문]: {args.query}")
    print(f"[답변]:\n{answer}")


if __name__ == "__main__":
    main()
