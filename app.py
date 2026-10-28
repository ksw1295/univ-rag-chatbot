import streamlit as st
from src.common import (
    DISTANCE_THRESHOLD,
    load_school_config,
    list_school_ids,
)
from src.ask import retrieve, is_answerable
from src.llm import call_llm, get_model_name

# 1. 페이지 기본 설정
st.set_page_config(
    page_title="대학 규정 RAG 챗봇",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 2. 세션 상태 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []
if "faq_prompt" not in st.session_state:
    st.session_state.faq_prompt = None

# 학교 목록 로드
school_ids = list_school_ids()
school_meta = {}
for sid in school_ids:
    try:
        cfg = load_school_config(sid)
        school_meta[sid] = cfg
    except Exception:
        school_meta[sid] = {"name": sid, "contact": "해당 부서", "homepage": ""}

# 3. 사이드바 구성
with st.sidebar:
    st.markdown("### 🎓 대상 대학교 선택")
    
    school_options = {sid: f"{school_meta[sid].get('name', sid)} ({sid})" for sid in school_ids}
    selected_school = st.selectbox(
        "대학교를 선택하세요",
        options=school_ids,
        format_func=lambda sid: school_options.get(sid, sid),
        index=0,
    )
    
    curr_cfg = school_meta.get(selected_school, {})
    school_name = curr_cfg.get("name", selected_school)
    contact_info = curr_cfg.get("contact", "해당 부서")
    homepage = curr_cfg.get("homepage", "")
    
    st.markdown("---")
    st.markdown("#### 📞 학교 공식 안내처")
    st.info(f"**{school_name}**\n- 문의처: `{contact_info}`\n- 홈페이지: [{homepage}]({homepage})")
    
    st.markdown("---")
    st.markdown("#### ⚙️ 시스템 아키텍처 스펙")
    with st.expander("아키텍처 세부 사양", expanded=True):
        st.markdown(
            f"""
            - **임베딩 모델**: `nlpai-lab/KURE-v1` (768차원)
            - **벡터 DB**: `ChromaDB` (Persistent)
            - **생성 LLM**: `{get_model_name()}`
            - **검색 방식**: 코사인 거리(Cosine Distance)
            - **환각 차단 필터**: 거리 **`{DISTANCE_THRESHOLD}`** 초과 시 LLM 호출 차단 후 공식 문의처로 직행
            - **문서 청킹**: 조항 단위(`제N조`) 본문 및 Markdown 표 추출
            """
        )
        
    st.markdown("---")
    if st.button("🗑️ 대화 내역 초기화", use_container_width=True):
        st.session_state.messages = []
        st.session_state.faq_prompt = None
        st.rerun()

# 4. 메인 화면 구성
st.title("🎓 대학 규정 & 학사·장학 RAG 질의응답 시스템")
st.caption(f"현재 선택된 대학교: **{school_name}** | 규정집 원문 근거 기반 답변 및 환각 방지 시스템 가동 중")

# 자주 묻는 질문 (FAQ) 퀵 버튼
st.markdown("##### 💡 자주 묻는 질문 (FAQ)")
faq_dict = {
    "kornu": [
        "장학생 선발 동점자 처리 기준은?",
        "장학위원회 위원장은 누구인가요?",
        "장학금 신청 자격은 어떻게 되나요?",
        "나사렛대학교의 3대 교육목표는 무엇인가요?",
    ],
    "cnsu": [
        "충남도립대학교 본교의 위치는 어디인가요?",
        "장학위원회는 어떤 사항을 심의하나요?",
        "장학위원회 구성원은 어떻게 되나요?",
        "성적우수장학금 기준이 뭐야?",
    ],
}

faqs = faq_dict.get(selected_school, [
    "장학금 수혜 요건은 어떻게 되나요?",
    "학칙 관련 규정 문의처는 어디인가요?",
])

faq_cols = st.columns(len(faqs))
for idx, q_text in enumerate(faqs):
    if faq_cols[idx].button(q_text, use_container_width=True, key=f"faq_{selected_school}_{idx}"):
        st.session_state.faq_prompt = q_text

st.markdown("---")

# 5. 기존 대화 기록 렌더링
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        
        # 근거 자료 expander 표시 (assistant 답변인 경우)
        hits = msg.get("hits")
        if hits:
            is_unanswerable = msg.get("unanswerable", False)
            expander_title = "📚 참고한 규정집 근거 조항 및 유사도 점수 (상위 검색 결과)"
            with st.expander(expander_title, expanded=False):
                if is_unanswerable:
                    st.warning(
                        f"⚠️ 최상위 검색 결과 거리({hits[0]['distance']:.4f})가 신뢰 임계값({DISTANCE_THRESHOLD})을 초과하여 "
                        f"환각(Hallucination) 방지를 위해 LLM 답변 생성을 건너뛰었습니다."
                    )
                for h_idx, h in enumerate(hits, start=1):
                    m = h.get("meta", {})
                    dist = h.get("distance", 0.0)
                    doc_src = m.get("source", "규정집")
                    art = m.get("article") or "본문/표"
                    page = m.get("page", "-")
                    year = m.get("year", "-")
                    text_snippet = h.get("text", "").strip()
                    
                    st.markdown(f"**[{h_idx}] {doc_src}** | `{art}` (거리: `{dist:.4f}` / {year}년도 / p.{page})")
                    st.code(text_snippet, language="markdown")

# 6. 사용자 입력 처리
user_input = st.chat_input("규정이나 학사/장학 관련 질문을 입력하세요...")

# FAQ 버튼 클릭 시 입력값 대입
if st.session_state.faq_prompt:
    user_input = st.session_state.faq_prompt
    st.session_state.faq_prompt = None

if user_input:
    # 사용자 질문 등록
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # RAG 질의 처리
    with st.chat_message("assistant"):
        with st.spinner("규정집 벡터 검색 및 근거 검증 중..."):
            hits = retrieve(selected_school, user_input, top_k=5)
            
            if not hits:
                ans_text = f"자료에서 찾지 못함, {contact_info}로 문의 바랍니다."
                unanswerable = True
            elif not is_answerable(hits):
                top_dist = hits[0]["distance"]
                ans_text = (
                    f"자료에서 찾지 못함, {contact_info}로 문의 바랍니다.\n\n"
                    f"*(최고 유사도 거리 `{top_dist:.4f}`가 신뢰 임계값 `{DISTANCE_THRESHOLD}`보다 커서 허위 답변(환각)을 방지하고자 공식 안내처로 안내합니다.)*"
                )
                unanswerable = True
            else:
                unanswerable = False
                # 근거 문맥 조립
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
만약 주어진 자료만으로 질문에 대한 명확한 근거를 찾을 수 없다면 반드시 "자료에서 찾지 못함, {contact_info}로 문의"라고 답변하십시오.

답변 마지막에는 반드시 답변의 근거가 된 출처(문서명, 조항, 학년도, 쪽)를 명시하십시오.

[참고자료]
{context_str}

[질문]
{user_input}

[답변]"""
                ans_text = call_llm(prompt).strip()

            st.markdown(ans_text)
            
            # 근거 expander
            if hits:
                with st.expander("📚 참고한 규정집 근거 조항 및 유사도 점수 (상위 검색 결과)", expanded=False):
                    if unanswerable:
                        st.warning(
                            f"⚠️ 최상위 검색 결과 거리({hits[0]['distance']:.4f})가 신뢰 임계값({DISTANCE_THRESHOLD})을 초과하여 "
                            f"환각 방지를 위해 LLM 호출을 건너뛰었습니다."
                        )
                    for h_idx, h in enumerate(hits, start=1):
                        m = h.get("meta", {})
                        dist = h.get("distance", 0.0)
                        doc_src = m.get("source", "규정집")
                        art = m.get("article") or "본문/표"
                        page = m.get("page", "-")
                        year = m.get("year", "-")
                        text_snippet = h.get("text", "").strip()
                        
                        st.markdown(f"**[{h_idx}] {doc_src}** | `{art}` (거리: `{dist:.4f}` / {year}년도 / p.{page})")
                        st.code(text_snippet, language="markdown")

    # 세션 상태에 저장
    st.session_state.messages.append({
        "role": "assistant",
        "content": ans_text,
        "hits": hits,
        "unanswerable": unanswerable,
    })
