import streamlit as st
from src.common import (
    DISTANCE_THRESHOLD,
    load_school_config,
    list_school_ids,
)
from src.ask import retrieve, is_answerable, rewrite_query
from src.llm import call_llm, get_model_name

# 1. 페이지 기본 설정
st.set_page_config(
    page_title="스마트 캠퍼스 학사·장학 규정 안내 시스템",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 2. 커스텀 CSS (모던 대학 포털 디자인 & Pretendard 폰트)
st.markdown(
    """
    <style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
    
    @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');
    
    /* 1. 기본 본문 텍스트에만 Pretendard 적용 (아이콘 폰트 간섭 방지) */
    html, body {
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, sans-serif;
    }
    
    /* 텍스트 요소 폰트 지정 */
    p, span:not([data-testid="stIcon"]):not([class*="material-"]):not([aria-hidden="true"]), 
    div:not([data-testid="stIcon"]):not([class*="material-"]):not([aria-hidden="true"]), 
    input, textarea, select, h1, h2, h3, h4, h5, h6 {
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, sans-serif;
    }

    /* 상태 도트 (Status Dots) 및 벡터 아이콘 */
    .status-dot {
        display: inline-block;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        flex-shrink: 0;
        vertical-align: middle;
        margin-right: 6px;
    }
    .status-dot-active {
        background-color: #10B981;
        box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.25);
    }
    .status-dot-warning {
        background-color: #F59E0B;
        box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.25);
    }
    .status-dot-danger {
        background-color: #EF4444;
        box-shadow: 0 0 0 2px rgba(239, 68, 68, 0.25);
    }
    .status-dot-info {
        background-color: #3B82F6;
        box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.25);
    }
    .status-dot-neutral {
        background-color: #94A3B8;
    }
    .icon-inline {
        font-family: 'Material Symbols Rounded' !important;
        font-size: 16px;
        vertical-align: -2px;
        margin-right: 5px;
        color: inherit;
        display: inline-block;
        line-height: 1;
    }

    /* 2. Material Symbols / Streamlit 내장 아이콘 폰트 강제 복원 (keyboard_double, arrow_down 텍스트 노출 버그 해결) */
    [data-testid="stIcon"],
    [data-testid="stIcon"] *,
    [data-testid="stSidebarCollapseButton"] *,
    [data-testid="stSidebarHeader"] button *,
    [data-testid="stExpanderToggleIcon"],
    [data-testid="stExpanderToggleIcon"] *,
    button[data-testid*="Collapse"] *,
    div[data-testid="stExpander"] summary svg,
    div[data-testid="stExpander"] summary span:first-child,
    .material-symbols-rounded,
    .material-symbols-outlined,
    .material-icons {
        font-family: 'Material Symbols Rounded', 'Material Symbols Outlined', 'Material Icons', sans-serif !important;
        font-style: normal !important;
        font-weight: normal !important;
        line-height: 1 !important;
        letter-spacing: normal !important;
        text-transform: none !important;
        display: inline-block !important;
        white-space: nowrap !important;
        word-wrap: normal !important;
        direction: ltr !important;
        -webkit-font-smoothing: antialiased !important;
    }
    
    /* 메인 배경색 및 여백 조정 */
    .main .block-container {
        padding-top: 2rem !important;
        padding-bottom: 3rem !important;
        max-width: 950px !important;
    }
    
    /* FAQ 칩 버튼 스타일링 */
    div[data-testid="stHorizontalBlock"] button {
        border-radius: 20px !important;
        border: 1px solid #E2E8F0 !important;
        background-color: #FFFFFF !important;
        color: #334155 !important;
        font-size: 13.5px !important;
        font-weight: 500 !important;
        padding: 8px 16px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.03) !important;
        transition: all 0.2s ease !important;
        white-space: nowrap !important;
        text-overflow: ellipsis !important;
        overflow: hidden !important;
    }
    div[data-testid="stHorizontalBlock"] button:hover {
        border-color: #3B82F6 !important;
        color: #1D4ED8 !important;
        background-color: #EFF6FF !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 6px -1px rgba(59, 130, 246, 0.1) !important;
    }
    
    /* 사이드바 스타일링 */
    section[data-testid="stSidebar"] {
        background-color: #F8FAFC !important;
        border-right: 1px solid #E2E8F0 !important;
    }

    /* 사이드바 상단 여백 및 닫기 버튼 정돈 */
    [data-testid="stSidebarHeader"] {
        padding-top: 0.8rem !important;
        padding-bottom: 0.4rem !important;
    }

    /* Expander 접이식 박스 스타일링 및 아이콘 겹침 방지 */
    div[data-testid="stExpander"] {
        border: 1px solid #E2E8F0 !important;
        border-radius: 10px !important;
        background-color: #FFFFFF !important;
        margin-bottom: 14px !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.02) !important;
    }
    div[data-testid="stExpander"] summary {
        border-radius: 10px !important;
        padding: 8px 12px !important;
    }
    div[data-testid="stExpander"] summary:hover {
        background-color: #F8FAFC !important;
    }
    
    /* 카드 컴포넌트 */
    .portal-card {
        background: white;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 18px;
        margin-bottom: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    
    /* 규정 근거 박스 */
    .evidence-card {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-left: 4px solid #2563EB;
        border-radius: 8px;
        padding: 14px 16px;
        margin-top: 10px;
        margin-bottom: 12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# 3. 세션 상태 초기화 (대학별 독립 대화 채널 분리)
if "school_messages" not in st.session_state:
    st.session_state.school_messages = {}
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

# 4. 사이드바 구성 (포털 스타일 서비스 네비게이션)
with st.sidebar:
    st.markdown(
        """
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 20px;">
            <div style="background: #1E3A8A; color: white; width: 38px; height: 38px; border-radius: 8px; display: flex; align-items: center; justify-content: center;">
                <span class="material-symbols-rounded" style="font-size: 22px;">account_balance</span>
            </div>
            <div>
                <div style="font-size: 16px; font-weight: 700; color: #0F172A; line-height: 1.2;">캠퍼스 규정 도우미</div>
                <div style="font-size: 12px; color: #64748B;">공식 규정·학사 실시간 질의</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    school_options = {sid: school_meta[sid].get("name", sid) for sid in school_ids}
    selected_school = st.selectbox(
        "소속 대학교 선택",
        options=school_ids,
        format_func=lambda sid: school_options.get(sid, sid),
        index=0,
    )

    if "current_school" not in st.session_state:
        st.session_state.current_school = selected_school
    elif st.session_state.current_school != selected_school:
        st.session_state.current_school = selected_school
        st.session_state.faq_prompt = None
        st.rerun()

    # 대학별 독립 대화 채널 바인딩
    if selected_school not in st.session_state.school_messages:
        st.session_state.school_messages[selected_school] = []
    current_messages = st.session_state.school_messages[selected_school]
    st.session_state.messages = current_messages

    curr_cfg = school_meta.get(selected_school, {})
    school_name = curr_cfg.get("name", selected_school)
    contact_info = curr_cfg.get("contact", "해당 부서")
    homepage = curr_cfg.get("homepage", "")

    # 학교 공식 안내 데스크 카드
    st.markdown(
        f"""
        <div class="portal-card">
            <div style="font-size: 13px; font-weight: 600; color: #2563EB; margin-bottom: 6px;">공식 부서 안내 창구</div>
            <div style="font-size: 15px; font-weight: 700; color: #1E293B; margin-bottom: 8px;">{school_name}</div>
            <div style="font-size: 13px; color: #475569; margin-bottom: 4px; display: flex; align-items: center;">
                <span class="material-symbols-rounded icon-inline">call</span>
                <span><b>직통 문의:</b> {contact_info}</span>
            </div>
            <div style="font-size: 13px; color: #475569; display: flex; align-items: center;">
                <span class="material-symbols-rounded icon-inline">language</span>
                <span><b>홈페이지:</b> <a href="{homepage}" target="_blank" style="color: #2563EB; text-decoration: none;">바로가기 ↗</a></span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 챗봇 이용 안내
    st.markdown(
        """
        <div style="background: #EFF6FF; border: 1px solid #DBEAFE; border-radius: 10px; padding: 14px; font-size: 12.5px; color: #1E40AF; line-height: 1.5; margin-bottom: 16px;">
            <span class="material-symbols-rounded icon-inline" style="color: #2563EB;">info</span><b>스마트 규정 도우미 활용 안내</b><br>
            • 학칙, 장학금 지급 기준, 휴·복학, 성적, 재입학 규정에 대해 질문해 보세요.<br>
            • 대학 공인 규정 원문만을 근거로 답변하여 허위 정보(환각)를 철저히 방지합니다.
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 아키텍처 안내 (개발자 스펙은 접이식으로 하단 배치)
    with st.expander("시스템 기술 사양 (RAG Spec)", expanded=False):
        st.markdown(
            f"""
            <div style="font-size: 12px; color: #64748B; line-height: 1.6;">
            • <b>임베딩 모델:</b> <code>nlpai-lab/KURE-v1</code> (768-dim)<br>
            • <b>벡터 엔진:</b> <code>ChromaDB (Persistent)</code><br>
            • <b>응답 생성 LLM:</b> <code>{get_model_name()}</code><br>
            • <b>환각 방지 신뢰 임계값:</b> <code>거리 ≤ {DISTANCE_THRESHOLD}</code><br>
            • <b>청킹:</b> 조항 단위(제N조) 및 표 Markdown 추출
            </div>
            """,
            unsafe_allow_html=True,
        )

    col_c1, col_c2 = st.columns(2)
    if col_c1.button(f"현재 대학 비우기", use_container_width=True):
        st.session_state.school_messages[selected_school] = []
        st.session_state.faq_prompt = None
        st.rerun()
    if col_c2.button("전체 대학 비우기", use_container_width=True):
        st.session_state.school_messages = {sid: [] for sid in school_ids}
        st.session_state.faq_prompt = None
        st.rerun()

# 5. 메인 포털 배너 헤더
school_theme_colors = {
    "kornu": ("#831843", "#BE185D"),  # 나사렛대 버건디 톤
    "cnsu": ("#1E3A8A", "#2563EB"),   # 충남도립대 블루 톤
}
c1, c2 = school_theme_colors.get(selected_school, ("#1E3A8A", "#2563EB"))

msg_count = len(current_messages) // 2
count_badge = f" (진행 질의 {msg_count}건)" if msg_count > 0 else ""

st.markdown(
    f"""
    <div style="background: linear-gradient(135deg, {c1} 0%, {c2} 100%); padding: 26px 30px; border-radius: 16px; color: white; margin-bottom: 22px; box-shadow: 0 4px 15px rgba(30, 58, 138, 0.12);">
        <span style="background: rgba(255, 255, 255, 0.18); padding: 5px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; letter-spacing: 0.3px; display: inline-flex; align-items: center;">
            <span class="status-dot status-dot-active"></span> {school_name} 전용 독립 상담 채널{count_badge}
        </span>
        <h2 style="color: white; margin: 10px 0 6px 0; font-size: 23px; font-weight: 700; letter-spacing: -0.5px;">
            {school_name} 학사·장학 규정 도우미
        </h2>
        <div style="color: rgba(255, 255, 255, 0.9); font-size: 13.5px; line-height: 1.5;">
            학칙, 장학 규정, 학사 시행세칙 원문만을 바탕으로 정확한 사실만을 답변해 드립니다.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# 6. 자주 묻는 질문 (FAQ) 퀵 칩스
st.markdown(
    """
    <div style='font-size: 13.5px; font-weight: 600; color: #475569; margin-bottom: 8px; display: flex; align-items: center;'>
        <span class="material-symbols-rounded icon-inline" style="font-size: 18px; color: #64748B;">quick_reference_all</span>
        <span>추천 질문 바로가기</span>
    </div>
    """,
    unsafe_allow_html=True,
)
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

st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)

# 7. 대화 내역 렌더링 (현재 대학 독립 채널)
for msg in current_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        
        # 규정 근거 박스
        hits = msg.get("hits")
        if hits and msg["role"] == "assistant":
            is_unanswerable = msg.get("unanswerable", False)
            search_q = msg.get("search_query")
            with st.expander("공식 규정집 발췌 근거 및 조항 확인", expanded=False):
                if search_q:
                    st.markdown(
                        f"<div style='font-size: 12px; color: #64748B; margin-bottom: 8px; display: flex; align-items: center;'>"
                        f"<span class='material-symbols-rounded icon-inline' style='font-size: 15px; color: #3B82F6;'>manage_search</span>"
                        f"맥락 반영 검색어: <code style='color: #1E293B; background: #F1F5F9; padding: 2px 6px; border-radius: 4px; margin-left: 4px;'>{search_q}</code>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                if is_unanswerable:
                    st.markdown(
                        f'''
                        <div style="background: #FEF3C7; border: 1px solid #FDE68A; border-radius: 6px; padding: 10px 12px; font-size: 12px; color: #92400E; margin-bottom: 10px; display: flex; align-items: flex-start; gap: 8px;">
                            <span class="status-dot status-dot-warning" style="margin-top: 4px;"></span>
                            <div>규정집 검색 결과와의 유사도 거리(<b>{hits[0]['distance']:.4f}</b>)가 신뢰 기준을 벗어나 부정확한 답변(환각)을 방지하고자 공식 문의처 안내로 대체되었습니다.</div>
                        </div>
                        ''',
                        unsafe_allow_html=True,
                    )
                for h_idx, h in enumerate(hits, start=1):
                    m = h.get("meta", {})
                    dist = h.get("distance", 0.0)
                    doc_src = m.get("source", "규정집")
                    art = m.get("article") or "본문/표"
                    page = m.get("page", "-")
                    year = m.get("year", "-")
                    text_snippet = h.get("text", "").strip()
                    
                    st.markdown(
                        f"""
                        <div class="evidence-card">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                                <span style="font-weight: 700; color: #1E293B; font-size: 13.5px; display: flex; align-items: center;">
                                    <span class="status-dot status-dot-info"></span>
                                    [{h_idx}] {doc_src} · {art}
                                </span>
                                <span style="background: #E0E7FF; color: #3730A3; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600;">
                                    기준거리: {dist:.4f} (p.{page})
                                </span>
                            </div>
                            <div style="font-size: 12.8px; color: #334155; line-height: 1.6; white-space: pre-wrap; background: white; padding: 10px; border-radius: 6px; border: 1px solid #E2E8F0;">{text_snippet}</div>
                            <div style="font-size: 11px; color: #94A3B8; margin-top: 5px;">발행 학년도: {year}년도 규정집 기준</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

# 8. 사용자 입력 처리
user_input = st.chat_input("규정집이나 학사/장학 관련 질문을 입력해 주세요...")

if st.session_state.faq_prompt:
    user_input = st.session_state.faq_prompt
    st.session_state.faq_prompt = None

if user_input:
    # 1. 현재 대학 전용 직전 대화 기록 확보 (재작성용)
    prev_history = list(current_messages)

    current_messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("대학 규정집 검색 및 사실 검증 중..."):
            # 2. 대화 맥락이 있을 경우 꼬리 질문을 완전한 독립 질의로 재작성
            search_query = rewrite_query(school_name, prev_history, user_input)

            # 3. 규정집 벡터 검색 수행
            hits = retrieve(selected_school, search_query, top_k=5)
            
            if not hits:
                ans_text = f"해당 내용은 대학 규정집에서 명시적인 근거를 찾지 못했습니다. 보다 정확한 확인을 위해 **{school_name} {contact_info}**로 직접 문의해 주시기 바랍니다."
                unanswerable = True
            elif not is_answerable(hits):
                top_dist = hits[0]["distance"]
                ans_text = (
                    f"해당 질문은 공식 규정 자료에서 충분히 신뢰할 만한 근거를 찾지 못했습니다.\n\n"
                    f"부정확한 정보 제공을 방지하기 위해 안내를 제한하오니, **{school_name} {contact_info}**로 직접 문의해 주시기 바랍니다."
                )
                unanswerable = True
            else:
                unanswerable = False
                contexts = []
                for idx, h in enumerate(hits, start=1):
                    meta = h["meta"]
                    ref = (
                        f"문서: {meta.get('source', '')}, 조항: {meta.get('article') or '본문/표'}, "
                        f"학년도: {meta.get('year', '')}년, 쪽: {meta.get('page', '')}쪽"
                    )
                    contexts.append(f"[자료 {idx}] ({ref})\n{h['text']}")
                context_str = "\n\n".join(contexts)

                query_context = f"{user_input} (검색 의도: {search_query})" if search_query != user_input else user_input

                prompt = f"""당신은 {school_name} 규정 및 학사/장학 안내 전문 챗봇입니다.
반드시 아래 제공된 [참고자료]의 내용에만 근거하여 질문에 사실대로 명확하게 답변하십시오.
제공된 자료에 언급되지 않은 사실을 추측하여 답변하거나 외부 지식을 지어내지 마십시오.
만약 주어진 자료만으로 질문에 대한 명확한 근거를 찾을 수 없다면 반드시 "자료에서 찾지 못함, {contact_info}로 문의"라고 답변하십시오.

답변 마지막에는 반드시 답변의 근거가 된 출처(문서명, 조항, 학년도, 쪽)를 명시하십시오.

[참고자료]
{context_str}

[질문]
{query_context}

[답변]"""
                ans_text = call_llm(prompt).strip()

            st.markdown(ans_text)

            if hits:
                with st.expander("공식 규정집 발췌 근거 및 조항 확인", expanded=False):
                    if search_query != user_input:
                        st.markdown(
                            f"<div style='font-size: 12px; color: #64748B; margin-bottom: 8px; display: flex; align-items: center;'>"
                            f"<span class='material-symbols-rounded icon-inline' style='font-size: 15px; color: #3B82F6;'>manage_search</span>"
                            f"맥락 반영 검색어: <code style='color: #1E293B; background: #F1F5F9; padding: 2px 6px; border-radius: 4px; margin-left: 4px;'>{search_query}</code>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
                    if unanswerable:
                        st.markdown(
                            f'''
                            <div style="background: #FEF3C7; border: 1px solid #FDE68A; border-radius: 6px; padding: 10px 12px; font-size: 12px; color: #92400E; margin-bottom: 10px; display: flex; align-items: flex-start; gap: 8px;">
                                <span class="status-dot status-dot-warning" style="margin-top: 4px;"></span>
                                <div>규정집 검색 결과와의 유사도 거리(<b>{hits[0]['distance']:.4f}</b>)가 신뢰 기준을 벗어나 부정확한 답변(환각)을 방지하고자 공식 문의처 안내로 대체되었습니다.</div>
                            </div>
                            ''',
                            unsafe_allow_html=True,
                        )
                    for h_idx, h in enumerate(hits, start=1):
                        m = h.get("meta", {})
                        dist = h.get("distance", 0.0)
                        doc_src = m.get("source", "규정집")
                        art = m.get("article") or "본문/표"
                        page = m.get("page", "-")
                        year = m.get("year", "-")
                        text_snippet = h.get("text", "").strip()
                        
                        st.markdown(
                            f"""
                            <div class="evidence-card">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                                    <span style="font-weight: 700; color: #1E293B; font-size: 13.5px;">
                                        [{h_idx}] {doc_src} · {art}
                                    </span>
                                    <span style="background: #E0E7FF; color: #3730A3; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600;">
                                        기준거리: {dist:.4f} (p.{page})
                                    </span>
                                </div>
                                <div style="font-size: 12.8px; color: #334155; line-height: 1.6; white-space: pre-wrap; background: white; padding: 10px; border-radius: 6px; border: 1px solid #E2E8F0;">{text_snippet}</div>
                                <div style="font-size: 11px; color: #94A3B8; margin-top: 5px;">발행 학년도: {year}년도 규정집 기준</div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

    current_messages.append({
        "role": "assistant",
        "content": ans_text,
        "hits": hits,
        "unanswerable": unanswerable,
        "search_query": search_query,
    })