import os
import re
import json
import glob
import yaml
import pdfplumber

DATA_RAW_DIR = r"D:\dev\devSandbox\univ-rag-chatbot\data\raw"
SCHOOLS_DIR = r"D:\dev\devSandbox\univ-rag-chatbot\schools"
OUTPUT_FILE = r"D:\dev\devSandbox\univ-rag-chatbot\data\chunks.jsonl"


def table_to_markdown(table):
    """2차원 배열의 표 데이터를 마크다운 표 문자열로 변환"""
    if not table or not table[0]:
        return ""
    
    # 빈 값 정리 및 줄바꿈 공백화
    clean_table = []
    for row in table:
        clean_row = [str(cell).replace("\n", " ").strip() if cell is not None else "" for cell in row]
        clean_table.append(clean_row)
    
    # 열 수 맞추기
    max_cols = max(len(row) for row in clean_table)
    if max_cols == 0:
        return ""
    
    padded_table = []
    for row in clean_table:
        padded_row = row + [""] * (max_cols - len(row))
        padded_table.append(padded_row)
    
    header = padded_table[0]
    separator = ["---"] * max_cols
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(separator) + " |"
    ]
    for row in padded_table[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def split_long_text(text, max_len=800):
    """긴 본문 텍스트를 문장/문단 단위로 분할"""
    if len(text) <= max_len:
        return [text]
    
    # 번호 매겨진 항(①, ②, 1., 2.) 또는 줄바꿈 기준으로 분할
    paragraphs = re.split(r"(?=\n\s*(?:[①-⑮]|\d+\.))|\n\n+", text)
    chunks = []
    current_chunk = []
    current_len = 0
    
    for p in paragraphs:
        p_strip = p.strip()
        if not p_strip:
            continue
        if current_len + len(p_strip) > max_len and current_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = [p_strip]
            current_len = len(p_strip)
        else:
            current_chunk.append(p_strip)
            current_len += len(p_strip)
            
    if current_chunk:
        chunks.append("\n".join(current_chunk))
    return chunks or [text]


def ingest_document(pdf_path, school_id, school_name, doc_title, year, doc_type, source_name):
    """단일 PDF 파일 파싱 및 조각 생성 (학교명·문서명·조항 문맥 접두사 포함)"""
    chunks = []
    
    with pdfplumber.open(pdf_path) as pdf:
        current_article = ""
        current_article_title = ""
        
        for page_idx, page in enumerate(pdf.pages, start=1):
            # 1. 표 추출
            tables = page.extract_tables()
            for t in tables:
                if len(t) >= 1 and len(t[0]) >= 2:
                    md_table = table_to_markdown(t)
                    if md_table:
                        art_tag = f" {current_article}" if current_article else ""
                        chunk_text = f"[{school_name} {doc_title}{art_tag} - {page_idx}쪽 표]\n{md_table}"
                        chunks.append({
                            "text": chunk_text,
                            "school_id": school_id,
                            "year": year,
                            "doc_type": doc_type,
                            "source": source_name,
                            "page": page_idx,
                            "article": current_article if current_article else "",
                            "is_table": True
                        })
            
            # 2. 본문 텍스트 추출
            page_text = page.extract_text() or ""
            if not page_text.strip():
                continue
            
            # 본문을 '제N조' 패턴으로 분리
            pattern = r"(제\s*\d+(?:의\d+)?\s*조(?:의\d+)?\s*(?:\([^)]*\))?)"
            parts = re.split(pattern, page_text)
            
            if len(parts) == 1:
                content = parts[0].strip()
                if content:
                    for sub in split_long_text(content):
                        art_tag = f" {current_article}" if current_article else ""
                        chunk_text = f"[{school_name} {doc_title}{art_tag}]\n{sub}"
                        chunks.append({
                            "text": chunk_text,
                            "school_id": school_id,
                            "year": year,
                            "doc_type": doc_type,
                            "source": source_name,
                            "page": page_idx,
                            "article": current_article if current_article else "",
                            "is_table": False
                        })
            else:
                prefix = parts[0].strip()
                if prefix:
                    for sub in split_long_text(prefix):
                        art_tag = f" {current_article}" if current_article else ""
                        chunk_text = f"[{school_name} {doc_title}{art_tag}]\n{sub}"
                        chunks.append({
                            "text": chunk_text,
                            "school_id": school_id,
                            "year": year,
                            "doc_type": doc_type,
                            "source": source_name,
                            "page": page_idx,
                            "article": current_article if current_article else "",
                            "is_table": False
                        })
                
                for i in range(1, len(parts), 2):
                    art_header = parts[i].strip()
                    art_body = parts[i+1].strip() if i+1 < len(parts) else ""
                    
                    m = re.match(r"(제\s*\d+(?:의\d+)?\s*조(?:의\d+)?)", art_header)
                    if m:
                        current_article = re.sub(r"\s+", "", m.group(1))
                    else:
                        current_article = art_header
                        
                    full_text = f"{art_header}\n{art_body}".strip()
                    for sub in split_long_text(full_text):
                        chunk_text = f"[{school_name} {doc_title} {current_article}]\n{sub}"
                        chunks.append({
                            "text": chunk_text,
                            "school_id": school_id,
                            "year": year,
                            "doc_type": doc_type,
                            "source": source_name,
                            "page": page_idx,
                            "article": current_article,
                            "is_table": False
                        })
                        
    return chunks


def run_ingest():
    all_chunks = []
    stats = {}
    
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    yaml_files = glob.glob(os.path.join(SCHOOLS_DIR, "*.yaml"))
    
    for yf in yaml_files:
        with open(yf, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
            
        sid = cfg["school_id"]
        sname = cfg.get("name", sid)
        stats[sid] = {"total": 0, "text": 0, "table": 0}
        
        for doc in cfg.get("documents", []):
            fname = doc["filename"]
            dtitle = doc.get("title", fname)
            pdf_path = os.path.join(DATA_RAW_DIR, sid, fname)
            if not os.path.exists(pdf_path):
                print(f"[경고] 파일을 찾을 수 없습니다: {pdf_path}")
                continue
                
            doc_chunks = ingest_document(
                pdf_path=pdf_path,
                school_id=sid,
                school_name=sname,
                doc_title=dtitle,
                year=doc.get("year", 2026),
                doc_type=doc.get("doc_type", "rule"),
                source_name=fname
            )
            
            for c in doc_chunks:
                stats[sid]["total"] += 1
                if c.get("is_table"):
                    stats[sid]["table"] += 1
                else:
                    stats[sid]["text"] += 1
                    
            all_chunks.extend(doc_chunks)


    # chunks.jsonl 저장
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
            
    print("=== Ingest 완료 ===")
    for sid, s in stats.items():
        print(f"[{sid}] 총 조각 수: {s['total']}개, 본문 조각 수: {s['text']}개, 표 조각 수: {s['table']}개")
    print(f"저장 위치: {OUTPUT_FILE} (총 {len(all_chunks)}개 조각)")


if __name__ == "__main__":
    import sys
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
    run_ingest()

