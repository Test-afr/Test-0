import os

from dotenv import load_dotenv
from fastapi import APIRouter, Response
from openai import OpenAI

load_dotenv()

API_KEY = os.environ.get("API_KEY")
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    API_KEY=API_KEY,
)

router = APIRouter()


@router.post("/chat", tags=["Qwen API"])
def chatbot(content: str) -> Response:
    completion = client.chat.completions.create(
        extra_headers={},
        extra_body={},
        model="deepseek/deepseek-r1-distill-qwen-1.5b",
        messages=[{"role": "user", "content": content}],
    )
    return completion.choices[0].message.content
