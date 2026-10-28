import re
import json
import collections

import pdfplumber

from src.common import CHUNKS_FILE, DATA_RAW_DIR, list_school_ids, load_school_config, setup_stdout

# 줄 맨 앞의 "제N조(제목)" 만 조항 머리로 본다. 본문 중 "제53조에 따라" 같은 인용은 쪼개지 않는다.
# 삭제 조항("제28조 삭제", "제30조의3 <삭제>")도 머리로 인정한다.
ARTICLE_HEAD_RE = re.compile(r"^제\s*(\d+)\s*조(?:\s*의\s*(\d+))?\s*(?=\(|<?\s*삭제)")
CHAPTER_RE = re.compile(r"^제\s*\d+\s*(?:장|절)(?:\s|$)")
# "[별표 1-1]", "<별표2>", "[별지 제9호 서식]" 처럼 괄호로 시작하는 줄만 별표·별지 머리로 본다.
ATTACHMENT_HEAD_RE = re.compile(r"^[\[<〈［]\s*(별표|별지)\s*(?:제\s*)?(\d+(?:-\d+)?)\s*호?\s*(?:서식)?\s*[\]>〉〕］](?![,，])")
SUPPLEMENT_HEAD_RE = re.compile(r"^부\s*칙")
PAGE_FOOTER_RE = re.compile(r"^-\s*\d+\s*-(\s*-\s*\d+\s*-)*$")  # "- 3 -", 2쪽 모아찍기의 "- 3 - - 4 -"


def table_to_markdown(table):
    """2차원 배열의 표 데이터를 마크다운 표 문자열로 변환"""
    if not table or not table[0]:
        return ""

    clean_table = []
    for row in table:
        clean_row = [str(cell).replace("\n", " ").strip() if cell is not None else "" for cell in row]
        clean_table.append(clean_row)

    max_cols = max(len(row) for row in clean_table)
    if max_cols == 0:
        return ""

    padded_table = [row + [""] * (max_cols - len(row)) for row in clean_table]
    lines = [
        "| " + " | ".join(padded_table[0]) + " |",
        "| " + " | ".join(["---"] * max_cols) + " |",
    ]
    for row in padded_table[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def is_real_table(table):
    """밑줄·구분선을 표로 잘못 읽은 조각(1행짜리, 대부분 빈 칸)을 걸러낸다."""
    if not table or len(table) < 2 or len(table[0]) < 2:
        return False
    cells = [str(c).strip() for row in table for c in row if c is not None]
    if not cells:
        return False
    filled = [c for c in cells if c]
    return len(filled) / len(cells) >= 0.4 and sum(len(c) for c in filled) >= 20


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


def page_regions(page):
    """가로로 놓인 2쪽 모아찍기 페이지는 왼쪽·오른쪽 반쪽으로 잘라 읽는다. 그대로 읽으면 두 단이 줄마다 섞인다."""
    if page.width > page.height:
        half = page.width / 2
        return [page.crop((0, 0, half, page.height)), page.crop((half, 0, page.width, page.height))]
    return [page]


def squash(line):
    """머리글 비교용: 쪽마다 띄어쓰기가 달라도("장학 규정"/"장학규정") 같은 줄로 본다."""
    return re.sub(r"\s+", "", line)


def running_headers(regions_text, min_pages=3, ratio=0.4):
    """여러 쪽의 맨 윗줄에 반복되는 머리글(예: "장학 규정 (3-3-4)")을 찾는다."""
    firsts = collections.Counter()
    for text in regions_text:
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if lines:
            firsts[squash(lines[0])] += 1
    n = len(regions_text)
    return {ln for ln, c in firsts.items() if c >= min_pages and c / n >= ratio}


def article_label(num, sub):
    return f"제{num}조의{sub}" if sub else f"제{num}조"


def header_prefix(school_name, doc_title):
    """조각 머리말 앞부분. 문서명이 이미 학교명으로 시작하면 학교명을 반복하지 않는다."""
    return doc_title if doc_title.startswith(school_name) else f"{school_name} {doc_title}"


def ingest_document(pdf_path, school_id, school_name, doc_title, year, doc_type, source_name):
    """단일 PDF 파일 파싱 및 조각 생성 (학교명·문서명·조항 문맥 접두사 포함)"""
    chunks = []
    prefix = header_prefix(school_name, doc_title)

    def add_chunk(text, page_idx, label, is_table):
        chunks.append({
            "text": text,
            "school_id": school_id,
            "year": year,
            "doc_type": doc_type,
            "source": source_name,
            "page": page_idx,
            "article": label,
            "is_table": is_table,
        })

    with pdfplumber.open(pdf_path) as pdf:
        regions_by_page = [page_regions(p) for p in pdf.pages]
        region_texts = [[r.extract_text() or "" for r in regions] for regions in regions_by_page]
        headers = running_headers([t for texts in region_texts for t in texts])

        label = ""  # 지금 읽고 있는 조항·별표·부칙 이름
        in_supplement = False
        seg_lines = []
        seg_label = ""

        def flush(page_idx):
            nonlocal seg_lines
            body = "\n".join(seg_lines).strip()
            seg_lines = []
            if not body:
                return
            tag = f" {seg_label}" if seg_label else ""
            for sub in split_long_text(body):
                add_chunk(f"[{prefix}{tag}]\n{sub}", page_idx, seg_label, False)

        for page_idx, (regions, texts) in enumerate(zip(regions_by_page, region_texts), start=1):
            for region_idx, (region, text) in enumerate(zip(regions, texts)):
                if region_idx > 0:
                    in_supplement = False  # 모아찍기 오른쪽 반쪽은 왼쪽 부칙과 이어지지 않는 새 흐름으로 본다
                # 1. 표 (현재 조항 이름을 붙임)
                for t in region.extract_tables():
                    if is_real_table(t):
                        tag = f" {label}" if label else ""
                        add_chunk(f"[{prefix}{tag} - {page_idx}쪽 표]\n{table_to_markdown(t)}", page_idx, label, True)

                # 2. 본문: 줄 단위로 읽으며 조항·별표·부칙 머리에서만 끊는다
                seg_label = label
                for raw in text.splitlines():
                    line = raw.strip()
                    if not line or squash(line) in headers or PAGE_FOOTER_RE.match(line):
                        continue

                    m = ARTICLE_HEAD_RE.match(line)
                    a = ATTACHMENT_HEAD_RE.match(line)
                    if m or a or SUPPLEMENT_HEAD_RE.match(line):
                        flush(page_idx)
                        if m:
                            label = article_label(m.group(1), m.group(2))
                            if in_supplement:
                                label = f"부칙 {label}"
                        elif a:
                            in_supplement = False
                            label = f"{a.group(1)} {a.group(2)}"
                        else:
                            in_supplement = True
                            label = "부칙"
                        seg_label = label
                    elif CHAPTER_RE.match(line):
                        flush(page_idx)  # 장·절 제목은 앞 조항 조각에 붙지 않도록 버린다
                        continue
                    seg_lines.append(line)
                flush(page_idx)
                seg_label = label

    return chunks


def require(doc, key, school_id):
    if doc.get(key) in (None, ""):
        raise ValueError(f"schools/{school_id}.yaml: documents 항목에 '{key}' 값이 필요합니다: {doc}")
    return doc[key]


def run_ingest():
    all_chunks = []
    stats = {}

    CHUNKS_FILE.parent.mkdir(parents=True, exist_ok=True)

    for sid in list_school_ids():
        cfg = load_school_config(sid)
        if cfg.get("school_id") != sid:
            raise ValueError(f"schools/{sid}.yaml: school_id({cfg.get('school_id')})가 파일명과 다릅니다")
        sname = require(cfg, "name", sid)
        stats[sid] = {"total": 0, "text": 0, "table": 0}

        for doc in cfg.get("documents", []):
            fname = require(doc, "filename", sid)
            dtitle = require(doc, "title", sid)
            doc_type = require(doc, "doc_type", sid)
            year = int(require(doc, "year", sid))
            pdf_path = DATA_RAW_DIR / sid / fname
            if not pdf_path.exists():
                print(f"[경고] 파일을 찾을 수 없습니다: {pdf_path}")
                continue

            doc_chunks = ingest_document(
                pdf_path=pdf_path,
                school_id=sid,
                school_name=sname,
                doc_title=dtitle,
                year=year,
                doc_type=doc_type,
                source_name=fname,
            )

            for c in doc_chunks:
                stats[sid]["total"] += 1
                stats[sid]["table" if c["is_table"] else "text"] += 1
            all_chunks.extend(doc_chunks)

    with open(CHUNKS_FILE, "w", encoding="utf-8") as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    print("=== Ingest 완료 ===")
    for sid, s in stats.items():
        print(f"[{sid}] 총 조각 수: {s['total']}개, 본문 조각 수: {s['text']}개, 표 조각 수: {s['table']}개")
    print(f"저장 위치: {CHUNKS_FILE} (총 {len(all_chunks)}개 조각)")


if __name__ == "__main__":
    setup_stdout()
    run_ingest()
