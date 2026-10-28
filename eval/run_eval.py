import os
import sys
import json
import chromadb
from sentence_transformers import SentenceTransformer

CHROMA_PATH = r"D:\dev\devSandbox\univ-rag-chatbot\chroma_db"
COLLECTION_NAME = "univ_regulations"
MODEL_NAME = "nlpai-lab/KURE-v1"
EVAL_DIR = r"D:\dev\devSandbox\univ-rag-chatbot\eval"


def evaluate_school(school_id: str, collection, model):
    eval_file = os.path.join(EVAL_DIR, f"questions_{school_id}.jsonl")
    if not os.path.exists(eval_file):
        print(f"[오류] 평가 파일이 없습니다: {eval_file}")
        return 0, 0, []

    questions = []
    with open(eval_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                questions.append(json.loads(line))

    results = []
    hits = 0

    for idx, q_item in enumerate(questions, start=1):
        query = q_item["question"]
        exp_art = q_item["expected_article"]
        exp_fact = q_item["expected_fact"]

        # 질문 임베딩 및 Chroma 검색 (상위 3개, where 필터 필수)
        query_emb = model.encode([query], normalize_embeddings=True).tolist()
        res = collection.query(
            query_embeddings=query_emb,
            n_results=3,
            where={"school_id": {"$eq": school_id}}
        )

        retrieved_metas = res.get("metadatas", [[]])[0]
        retrieved_docs = res.get("documents", [[]])[0]

        retrieved_articles = []
        is_hit = False

        for doc, meta in zip(retrieved_docs, retrieved_metas):
            art = meta.get("article", "").strip()
            src = meta.get("source", "")
            pg = meta.get("page", "")
            label = f"{src}:{art}(p{pg})" if art else f"{src}(p{pg})"
            retrieved_articles.append(label)

            # 조항 메타데이터 또는 본문 텍스트에 expected_article 포함 여부
            if exp_art in art or exp_art in doc:
                is_hit = True

        if is_hit:
            hits += 1

        results.append({
            "no": idx,
            "question": query,
            "expected_article": exp_art,
            "retrieved_articles": ", ".join(retrieved_articles),
            "hit": "O" if is_hit else "X"
        })

    total = len(questions)
    hit_rate = (hits / total) * 100 if total > 0 else 0
    return hits, total, results


def run_evaluation():
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_collection(name=COLLECTION_NAME)
    model = SentenceTransformer(MODEL_NAME, device="cpu")

    schools = ["kornu", "cnsu"]
    summary_table = []

    print("================================================================================")
    print("                      대학 규정 RAG 챗봇 Hit@3 평가 결과                      ")
    print("================================================================================\n")

    for sid in schools:
        hits, total, details = evaluate_school(sid, collection, model)
        hit_rate = (hits / total * 100) if total > 0 else 0
        summary_table.append({"school": sid, "hits": hits, "total": total, "rate": hit_rate})

        print(f"[{sid.upper()}] Hit@3: {hits}/{total} ({hit_rate:.1f}%)")
        print("-" * 80)
        print(f"{'번호':<4} | {'예상조항':<8} | {'Hit':<4} | {'질문':<32} | {'검색된 상위 3개'}")
        print("-" * 80)
        for r in details:
            q_short = (r["question"][:30] + "..") if len(r["question"]) > 32 else r["question"]
            print(f"{r['no']:<4} | {r['expected_article']:<8} | {r['hit']:<4} | {q_short:<32} | {r['retrieved_articles']}")
        print("\n")

    print("================================================================================")
    print("                               종합 요약 표                                    ")
    print("================================================================================")
    print(f"{'학교 ID':<10} | {'총 문항 수':<10} | {'Hit@3 적중 수':<14} | {'Hit@3 적중률 (%)'}")
    print("-" * 60)
    for s in summary_table:
        print(f"{s['school']:<10} | {s['total']:<10} | {s['hits']:<14} | {s['rate']:.1f}%")
    print("================================================================================\n")


if __name__ == "__main__":
    run_evaluation()
