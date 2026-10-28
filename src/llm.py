import os
from dotenv import load_dotenv
from google import genai

# .env 파일이 있으면 환경 변수로 로드 (파일 내용을 직접 출력하거나 열어보지 않음)
load_dotenv()

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")


def get_api_key() -> str | None:
    """Streamlit Secrets 및 환경 변수에서 GEMINI_API_KEY를 탐색 (폴백 지원)"""
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
            return str(st.secrets["GEMINI_API_KEY"]).strip()
    except Exception:
        pass
    return os.environ.get("GEMINI_API_KEY")


def get_model_name(default_model: str | None = None) -> str:
    """Streamlit Secrets 및 환경 변수에서 GEMINI_MODEL을 탐색"""
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "GEMINI_MODEL" in st.secrets:
            return str(st.secrets["GEMINI_MODEL"]).strip()
    except Exception:
        pass
    return os.environ.get("GEMINI_MODEL") or default_model or DEFAULT_MODEL


def call_llm(prompt: str, model_name: str | None = None) -> str:
    """Gemini LLM 호출 모듈 (단일 진입점)"""
    api_key = get_api_key()
    if not api_key:
        return "[오류] GEMINI_API_KEY가 환경 변수 또는 Streamlit Secrets에 설정되지 않았습니다."
    
    target_model = model_name or get_model_name()
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=target_model,
            contents=prompt,
        )
        return response.text or ""
    except Exception as e:
        return f"[LLM 호출 오류] {e}"
