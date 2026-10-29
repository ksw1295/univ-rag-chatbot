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


def rewrite_query(school_name: str, history: list[dict] | None, query: str) -> str:
    """대화 맥락(최근 문답)이 있는 경우, 꼬리 질문을 단독 검색이 가능한 명확한 검색 질의로 재작성한다."""
    if not history:
        return query

    recent_turns = []
    for msg in history[-4:]:
        role = "사용자" if msg.get("role") == "user" else "답변"
        content = str(msg.get("content", "")).strip()
        if role == "답변" and len(content) > 150:
            content = content[:150] + "..."
        if content:
            recent_turns.append(f"{role}: {content}")

    if not recent_turns:
        return query

    history_str = "\n".join(recent_turns)
    prompt = f"""당신은 대학 학사/규정 전문 검색 쿼리 작성기입니다.
사용자의 [이전 대화]와 [현재 질문]을 분석하여, 문서 검색(Vector Search)을 위한 명확한 "단일 검색 질의(한 문장)"로 재작성해 주세요.

[규칙]
1. 사용자의 질문이 "그럼 학점은?", "신청 기간은?", "휴학생도 돼?" 처럼 앞선 대화의 주제(예: 장학금, 수강신청, 복학 등)에 의존하는 꼬리 질문이라면, 반드시 대상 주제와 대학명({school_name})을 포함하여 완전한 독립 질문으로 재작성하십시오.
2. 이미 질문 자체에 구체적인 키워드와 주제가 명확히 포함되어 있거나 새로운 주제로 전환하는 질문이라면, 원래 질문을 그대로 유지하되 대학명({school_name})만 보완하십시오.
3. 부가 설명, 따옴표, 마크다운 없이 오직 재작성된 검색 질의 한 줄만 출력하십시오.

[이전 대화]
{history_str}

[현재 질문]
{query}

[검색 질의]"""
    try:
        rewritten = call_llm(prompt).strip()
        if rewritten and not rewritten.startswith("[") and len(rewritten) < 120:
            clean_q = rewritten.splitlines()[0].strip('"\' ')
            if clean_q:
                return clean_q
    except Exception:
        pass
    return query


def ask_question(school_id: str, query: str, top_k: int = 5, history: list[dict] | None = None) -> str:
    cfg = load_school_config(school_id)
    school_name = cfg.get("name", school_id)
    contact = cfg.get("contact", "").strip() or "해당 부서"

    search_query = rewrite_query(school_name, history, query)
    hits = retrieve(school_id, search_query, top_k)
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

    query_hint = f"{query} (검색 의도: {search_query})" if search_query != query else query

    prompt = f"""당신은 {school_name} 규정 및 학사/장학 안내 전문 챗봇입니다.
반드시 아래 제공된 [참고자료]의 내용에만 근거하여 질문에 사실대로 명확하게 답변하십시오.
제공된 자료에 언급되지 않은 사실을 추측하여 답변하거나 외부 지식을 지어내지 마십시오.
만약 주어진 자료만으로 질문에 대한 명확한 근거를 찾을 수 없다면 반드시 "자료에서 찾지 못함, {contact}로 문의"라고 답변하십시오.

답변 마지막에는 반드시 답변의 근거가 된 출처(문서명, 조항, 학년도, 쪽)를 명시하십시오.

[참고자료]
{context_str}

[질문]
{query_hint}

[답변]"""

    return call_llm(prompt).strip()


def format_sources(hits: list[dict]) -> str:
    lines = []
    for i, h in enumerate(hits, start=1):
        m = h["meta"]
        lines.append(f"  {i}. 거리 {h['distance']:.4f} | {m.get('source')} {m.get('article') or '-'} (p{m.get('page')}, {m.get('year')}학년도)")
    return "\n".join(lines)


def main():
    setup_stdout()
    parser = argparse.ArgumentParser(description="대학 규정/학사 RAG 챗봇 질의")
    parser.add_argument("--school", required=True, help="학교 ID (예: kornu, cnsu)")
    parser.add_argument("query", help="질문 내용")
    parser.add_argument("--sources", action="store_true", help="검색된 상위 조각(거리·문서·조항)도 함께 출력")
    args = parser.parse_args()

    answer = ask_question(args.school, args.query)
    print(f"\n[학교]: {args.school}")
    print(f"[질문]: {args.query}")
    if args.sources:
        print("[검색된 조각]:\n" + format_sources(retrieve(args.school, args.query)))
    print(f"[답변]:\n{answer}")


if __name__ == "__main__":
    main()
