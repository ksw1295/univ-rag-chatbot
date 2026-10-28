"""검색 평가: Hit@3(같은 문서 + 정확한 조항)와 '자료에 없는 질문'이 임계값에서 걸러지는지를 학교별로 잰다.

문항 형식 (eval/questions_<학교ID>.jsonl, '#'로 시작하는 줄은 주석):
  type: scholarship | rule | academic | unanswerable
  expected_source, expected_article: 정답 문서 파일명과 조항 (unanswerable은 null)
  evidence: 정답 조항 조각 안에 있어야 하는 원문 구절(공백 제거 기준). 문항이 원문과 맞는지 자동 확인용.
"""
import json
import re
import sys

from src.ask import retrieve
from src.common import (
    DISTANCE_THRESHOLD,
    EVAL_DIR,
    get_collection,
    list_school_ids,
    load_school_config,
    setup_stdout,
)

TOP_K = 3


def squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def article_matches(expected: str, actual: str) -> bool:
    """조항 이름이 정확히 같을 때만 True. '제2조'는 '제12조'·'제2조의2'·'부칙 제2조'와 맞지 않는다."""
    return re.fullmatch(re.escape(squash(expected)), squash(actual or "")) is not None


def is_hit(item: dict, meta: dict) -> bool:
    return meta.get("source") == item["expected_source"] and article_matches(item["expected_article"], meta.get("article", ""))


def load_questions(school_id: str) -> list[dict]:
    path = EVAL_DIR / f"questions_{school_id}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"평가 파일이 없습니다: {path}")
    sources = {d["filename"] for d in load_school_config(school_id).get("documents", [])}
    questions = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            q = json.loads(line)
            if q["type"] != "unanswerable" and q["expected_source"] not in sources:
                raise ValueError(f"{path}:{line_no} expected_source가 학교 설정의 문서 목록에 없습니다: {q['expected_source']}")
            questions.append(q)
    return questions


def evidence_found(school_id: str, item: dict) -> bool:
    """문항의 evidence 구절이 정답 조항 조각들 안에 실제로 있는지 (인덱스 기준)."""
    got = get_collection().get(
        where={"$and": [
            {"school_id": {"$eq": school_id}},
            {"source": {"$eq": item["expected_source"]}},
        ]},
        include=["documents", "metadatas"],
    )
    body = "".join(
        squash(doc) for doc, meta in zip(got["documents"], got["metadatas"])
        if article_matches(item["expected_article"], meta.get("article", ""))
    )
    return squash(item["evidence"]) in body


def label_of(meta: dict) -> str:
    art = meta.get("article", "").strip()
    base = f"{meta.get('source', '')}:{art}" if art else meta.get("source", "")
    return f"{base}(p{meta.get('page', '')})"


def evaluate_school(school_id: str) -> dict:
    rows = []
    for q in load_questions(school_id):
        hits = retrieve(school_id, q["question"], top_k=TOP_K)
        best = hits[0]["distance"] if hits else float("inf")
        passes = best <= DISTANCE_THRESHOLD  # ask가 LLM에 넘기는 질문이면 True
        row = {
            "id": q["id"], "type": q["type"], "question": q["question"],
            "expected": f"{q['expected_source']}:{q['expected_article']}" if q["type"] != "unanswerable" else "-",
            "best": best, "passes": passes,
            "top3": ", ".join(label_of(h["meta"]) for h in hits),
        }
        if q["type"] == "unanswerable":
            row["ok"] = not passes  # 걸러져야 정상
        else:
            row["hit"] = any(is_hit(q, h["meta"]) for h in hits)
            row["evidence_ok"] = evidence_found(school_id, q)
            row["ok"] = row["hit"]
        rows.append(row)
    return {"school": school_id, "rows": rows}


def short(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def print_school(res: dict):
    rows = res["rows"]
    answerable = [r for r in rows if r["type"] != "unanswerable"]
    unans = [r for r in rows if r["type"] == "unanswerable"]
    hits = sum(r["hit"] for r in answerable)
    passed = sum(r["passes"] for r in answerable)
    filtered = sum(r["ok"] for r in unans)

    print(f"[{res['school'].upper()}] Hit@{TOP_K}: {hits}/{len(answerable)}  |  "
          f"답변 시도(거리≤{DISTANCE_THRESHOLD}): {passed}/{len(answerable)}  |  "
          f"자료 없는 질문 걸러짐: {filtered}/{len(unans)}")
    print("-" * 150)
    print(f"{'id':<10} | {'유형':<12} | {'판정':<6} | {'최고거리':<7} | {'정답(문서:조항)':<30} | {'질문':<40} | 검색된 상위 {TOP_K}개")
    print("-" * 150)
    for r in rows:
        if r["type"] == "unanswerable":
            verdict = "걸러짐" if r["ok"] else "통과(X)"
        else:
            verdict = "Hit" if r["hit"] else "Miss"
        print(f"{r['id']:<10} | {r['type']:<12} | {verdict:<6} | {r['best']:<7.4f} | {short(r['expected'], 30):<30} | "
              f"{short(r['question'], 40):<40} | {r['top3']}")
    bad = [r["id"] for r in answerable if not r["evidence_ok"]]
    print(f"문항 근거 구절 확인: {len(answerable) - len(bad)}/{len(answerable)} 문항이 정답 조항 조각 안에서 확인됨"
          + (f" (확인 안 됨: {', '.join(bad)})" if bad else ""))
    if answerable and unans:
        worst_ans = max(r["best"] for r in answerable)
        best_unans = min(r["best"] for r in unans)
        print(f"거리 분포: 자료 있는 질문 중 최대 {worst_ans:.4f} / 자료 없는 질문 중 최소 {best_unans:.4f} "
              f"(임계값 {DISTANCE_THRESHOLD}, 간격 {best_unans - worst_ans:+.4f})")
    print()


def run_evaluation():
    setup_stdout()
    results = [evaluate_school(sid) for sid in list_school_ids()]

    print("=" * 150)
    print(f"대학 규정 RAG 챗봇 검색 평가 (Hit@{TOP_K}: 같은 문서 + 정확한 조항 / 임계값 {DISTANCE_THRESHOLD})")
    print("=" * 150 + "\n")
    for res in results:
        print_school(res)

    print("=" * 150)
    print("종합 요약")
    print("=" * 150)
    print(f"{'학교 ID':<10} | {'자료 있는 문항':<13} | {f'Hit@{TOP_K}':<12} | {'답변 시도':<10} | {'자료 없는 문항':<13} | {'걸러짐'}")
    print("-" * 90)
    for res in results:
        ans = [r for r in res["rows"] if r["type"] != "unanswerable"]
        un = [r for r in res["rows"] if r["type"] == "unanswerable"]
        h, p, f = sum(r["hit"] for r in ans), sum(r["passes"] for r in ans), sum(r["ok"] for r in un)
        print(f"{res['school']:<10} | {len(ans):<13} | {h}/{len(ans)} ({h / len(ans) * 100:.0f}%)".ljust(48)
              + f" | {p}/{len(ans)}".ljust(13) + f" | {len(un):<13} | {f}/{len(un)}")
    print("=" * 150)


if __name__ == "__main__":
    run_evaluation()
