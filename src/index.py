import argparse
import json
import time
from collections import defaultdict

import chromadb

from src.common import (
    CHROMA_PATH,
    CHUNKS_FILE,
    COLLECTION_NAME,
    MAX_SEQ_LENGTH,
    MODEL_NAME,
    get_model,
    resolve_device,
    setup_stdout,
)

REQUIRED_FIELDS = ("text", "school_id", "year", "doc_type", "source")


def load_chunks():
    chunks = []
    with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            c = json.loads(line)
            missing = [k for k in REQUIRED_FIELDS if c.get(k) in (None, "")]
            if missing:
                raise ValueError(f"{CHUNKS_FILE}:{line_no} 조각에 필수 값이 없습니다: {missing}")
            chunks.append(c)
    return chunks


def build_records(chunks):
    """(id, text, metadata) 목록. id는 학교·자료·자료 안 순번이라 같은 자료를 다시 넣으면 같은 id가 된다."""
    seq = defaultdict(int)
    records = []
    for c in chunks:
        key = (c["school_id"], c["source"])
        chunk_id = f"{c['school_id']}:{c['source']}:{seq[key]:05d}"
        seq[key] += 1
        meta = {
            "school_id": str(c["school_id"]),
            "year": int(c["year"]),
            "doc_type": str(c["doc_type"]),
            "source": str(c["source"]),
            "page": int(c.get("page", 1)),
            "article": str(c.get("article", "")),
            "is_table": bool(c.get("is_table", False)),
        }
        records.append((chunk_id, c["text"], meta))
    return records, sorted(seq)


def run_index(batch_size=32, reset=False):
    setup_stdout()
    started = time.perf_counter()

    if not CHUNKS_FILE.exists():
        print(f"[오류] 조각 파일이 없습니다: {CHUNKS_FILE}")
        print("먼저 python -m src.ingest 를 실행하세요.")
        return

    print("=== 1. 조각 파일 로딩 ===", flush=True)
    chunks = load_chunks()
    print(f"로딩된 총 조각 수: {len(chunks)}개", flush=True)

    device = resolve_device()
    print(f"\n=== 2. 임베딩 모델 로딩 ({MODEL_NAME}, {device}, max_seq_length={MAX_SEQ_LENGTH}) ===", flush=True)
    model = get_model()
    print("임베딩 모델 로딩 완료.", flush=True)

    print(f"\n=== 3. Chroma DB 연결 ({CHROMA_PATH}) ===", flush=True)
    CHROMA_PATH.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    if reset:
        try:
            client.delete_collection(name=COLLECTION_NAME)
            print(f"기존 컬렉션 '{COLLECTION_NAME}'을(를) 통째로 지웠습니다 (--reset).", flush=True)
        except Exception:
            pass
    collection = client.get_or_create_collection(name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"})

    records, sources = build_records(chunks)
    # 다시 넣을 자료의 옛 기록은 먼저 지운다. 조각 수가 줄어든 자료에도 옛 조각이 남지 않는다.
    for school_id, source in sources:
        collection.delete(where={"$and": [{"school_id": {"$eq": school_id}}, {"source": {"$eq": source}}]})
    print(f"기존 기록 정리 완료: {len(sources)}개 자료 (school_id, source) 단위", flush=True)

    # 길이순으로 정렬해 한 배치 안의 패딩 낭비를 줄인다 (CPU에서 시간 차이가 큼)
    records.sort(key=lambda r: len(r[1]))
    total = len(records)

    print(f"\n=== 4. 임베딩 생성 및 Chroma upsert (배치 크기: {batch_size}) ===", flush=True)
    done = 0
    for i in range(0, total, batch_size):
        batch = records[i:i + batch_size]
        texts = [r[1] for r in batch]
        embeddings = model.encode(texts, batch_size=batch_size, show_progress_bar=False, normalize_embeddings=True)
        collection.upsert(
            ids=[r[0] for r in batch],
            embeddings=embeddings.tolist(),
            documents=texts,
            metadatas=[r[2] for r in batch],
        )
        done += len(batch)
        elapsed = time.perf_counter() - started
        print(f"진행: {done}/{total} ({done * 100 // total}%) 경과 {elapsed:.0f}초", flush=True)

    elapsed = time.perf_counter() - started
    print("\n=== Index 완료 ===")
    print(f"컬렉션 이름: {COLLECTION_NAME}")
    print(f"저장된 총 레코드 수: {collection.count()}개")
    print(f"걸린 시간(모델 로딩 포함): {elapsed:.1f}초 / device={device}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="data/chunks.jsonl을 임베딩해 Chroma에 적재")
    parser.add_argument("--reset", action="store_true", help="컬렉션을 통째로 지우고 처음부터 다시 만든다")
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()
    run_index(batch_size=args.batch_size, reset=args.reset)
