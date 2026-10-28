import argparse

from src.common import (
    DISTANCE_THRESHOLD,
    get_collection,
    get_model,
    load_school_config,
    setup_stdout,
)
from src.llm import call_llm


def retrieve(school_id: str, query: str, top_k: int = 5) -> list[dict]:
    """school_id 필터로 상위 top_k 조각을 찾는다. 가까운 순서이며 distance는 코사인 거리."""
    query_emb = get_model().encode([query], normalize_embeddings=True).tolist()
    results = get_collection().query(
        query_embeddings=query_emb,
        n_results=top_k,
        where={"school_id": {"$eq": school_id}},
    )
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]
    return [{"text": d, "meta": m, "distance": x} for d, m, x in zip(docs, metas, distances)]


def is_answerable(hits: list[dict]) -> bool:
    """가장 가까운 조각이 임계값 안이면 LLM에 넘길 만한 근거가 있다고 본다."""
    return bool(hits) and hits[0]["distance"] <= DISTANCE_THRESHOLD


def ask_question(school_id: str, query: str, top_k: int = 5) -> str:
    cfg = load_school_config(school_id)
    school_name = cfg.get("name", school_id)
    contact = cfg.get("contact", "").strip() or "해당 부서"

    hits = retrieve(school_id, query, top_k)
    if not hits:
        return f"자료에서 찾지 못함, {contact}로 문의"

    if not is_answerable(hits):
        return (
            f"자료에서 찾지 못함, {contact}로 문의\n\n"
            f"(최고 유사도 거리 {hits[0]['distance']:.4f}가 임계값 {DISTANCE_THRESHOLD}보다 커서 LLM 호출을 생략했습니다.)"
        )

    contexts = []
    for idx, h in enumerate(hits, start=1):
        meta = h["meta"]
        ref = (
            f"문서: {meta.get('source', '')}, 조항: {meta.get('article') or '본문/표'}, "
            f"학년도: {meta.get('year', '')}년, 쪽: {meta.get('page', '')}쪽"
        )
        contexts.append(f"[자료 {idx}] ({ref})\n{h['text']}")
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

    return call_llm(prompt).strip()


def main():
    setup_stdout()
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
