import os
import sys
import json
import hashlib
import chromadb

from src.common import (
    CHROMA_PATH,
    CHUNKS_FILE,
    COLLECTION_NAME,
    MODEL_NAME,
    get_model,
    resolve_device,
    setup_stdout,
)


def run_index(batch_size=64):
    setup_stdout()

    if not os.path.exists(CHUNKS_FILE):
        print(f"[오류] 조각 파일이 없습니다: {CHUNKS_FILE}")
        print("먼저 python -m src.ingest 를 실행하세요.")
        return

    print("=== 1. 조각 파일 로딩 ===")
    chunks = []
    with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    print(f"로딩된 총 조각 수: {len(chunks)}개")

    print(f"\n=== 2. 임베딩 모델 로딩 ({MODEL_NAME}, {resolve_device()}) ===")
    model = get_model()
    print("임베딩 모델 로딩 완료.")

    print(f"\n=== 3. Chroma DB 연결 ({CHROMA_PATH}) ===")
    os.makedirs(CHROMA_PATH, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    try:
        client.delete_collection(name=COLLECTION_NAME)
        print(f"기존 컬렉션 '{COLLECTION_NAME}' 초기화 완료.")
    except Exception:
        pass
    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )


    print(f"\n=== 4. 임베딩 생성 및 Chroma Upsert (배치 크기: {batch_size}) ===")
    total = len(chunks)
    upserted_count = 0

    # 각 청크에 고유 ID 사전 부여 (재실행 멱등성 보장: school_id + source + chunk_index + text_hash)
    chunk_records = []
    for idx, c in enumerate(chunks):
        text_hash = hashlib.sha256(c["text"].encode("utf-8")).hexdigest()[:10]
        chunk_id = f"{c['school_id']}_{c['source']}_c{idx:05d}_{text_hash}"
        meta = {
            "school_id": str(c.get("school_id", "")),
            "year": int(c.get("year", 2026)),
            "doc_type": str(c.get("doc_type", "")),
            "source": str(c.get("source", "")),
            "page": int(c.get("page", 1)),
            "article": str(c.get("article", "")),
            "is_table": bool(c.get("is_table", False))
        }
        chunk_records.append((chunk_id, c["text"], meta))

    for i in range(0, total, batch_size):
        batch = chunk_records[i:i+batch_size]
        ids = [item[0] for item in batch]
        texts = [item[1] for item in batch]
        metadatas = [item[2] for item in batch]

        # 임베딩 생성
        embeddings = model.encode(texts, batch_size=batch_size, show_progress_bar=False, normalize_embeddings=True)
        
        # Chroma upsert
        collection.upsert(
            ids=ids,
            embeddings=embeddings.tolist(),
            documents=texts,
            metadatas=metadatas
        )
        upserted_count += len(batch)
        print(f"진행: {upserted_count}/{total} ({upserted_count*100//total}%) 완료")


    print("\n=== Index 완료 ===")
    print(f"컬렉션 이름: {COLLECTION_NAME}")
    print(f"저장된 총 레코드 수: {collection.count()}개")


if __name__ == "__main__":
    run_index()
