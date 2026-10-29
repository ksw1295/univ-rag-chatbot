"""경로, 임베딩 모델, Chroma 컬렉션 등 여러 모듈이 같이 쓰는 설정과 자원 (프로세스당 한 번만 로드)."""
import os
import sys
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA_RAW_DIR = ROOT / "data" / "raw"
SCHOOLS_DIR = ROOT / "schools"
CHUNKS_FILE = ROOT / "data" / "chunks.jsonl"
EVAL_DIR = ROOT / "eval"
CHROMA_PATH = Path(os.environ.get("UNIV_RAG_CHROMA_DIR") or ROOT / "chroma_db")

COLLECTION_NAME = "univ_regulations"
MODEL_NAME = "nlpai-lab/KURE-v1"
MAX_SEQ_LENGTH = 512  # 조각 대부분은 이보다 짧음. 긴 표 조각의 꼬리만 잘리고 CPU 시간이 크게 줄어듦
DISTANCE_THRESHOLD = float(os.environ.get("UNIV_RAG_DISTANCE_THRESHOLD", "0.38"))  # 코사인 거리 기준 (이보다 크면 검색 유사도 부족으로 판정하여 LLM 미호출)


def setup_stdout():
    """Windows 콘솔(cp949)에서 특수문자 출력 오류가 나지 않도록 utf-8로 맞춘다."""
    enc = (getattr(sys.stdout, "encoding", None) or "").lower()
    if enc != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass


def resolve_device() -> str:
    """UNIV_RAG_DEVICE 환경변수가 있으면 그 값, 없으면 CUDA가 쓸 수 있을 때 cuda, 아니면 cpu."""
    forced = os.environ.get("UNIV_RAG_DEVICE")
    if forced:
        return forced
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


@lru_cache(maxsize=1)
def get_model():
    """임베딩 모델은 프로세스에서 한 번만 로드한다."""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL_NAME, device=resolve_device())
    model.max_seq_length = MAX_SEQ_LENGTH
    return model


@lru_cache(maxsize=1)
def get_collection():
    import chromadb

    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    return client.get_collection(name=COLLECTION_NAME)


def list_school_ids() -> list[str]:
    return sorted(p.stem for p in SCHOOLS_DIR.glob("*.yaml"))


def load_school_config(school_id: str) -> dict:
    yaml_path = SCHOOLS_DIR / f"{school_id}.yaml"
    if not yaml_path.exists():
        raise FileNotFoundError(f"학교 설정 파일을 찾을 수 없습니다: {yaml_path}")
    with open(yaml_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
