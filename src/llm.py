import os
from dotenv import load_dotenv
from google import genai

# .env 파일이 있으면 환경 변수로 로드 (파일 내용을 직접 출력하거나 열어보지 않음)
load_dotenv()

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")


def call_llm(prompt: str, model_name: str = DEFAULT_MODEL) -> str:
    """Gemini LLM 호출 모듈 (단일 진입점)"""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "[오류] GEMINI_API_KEY 환경변수가 설정되지 않았습니다."
    
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
        )
        return response.text or ""
    except Exception as e:
        return f"[LLM 호출 오류] {e}"
