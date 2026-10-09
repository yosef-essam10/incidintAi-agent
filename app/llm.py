import os
from dotenv import load_dotenv
load_dotenv()

def ask(system, user):
    key = os.getenv("GROQ_API_KEY")
    if not key:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")
        r = client.chat.completions.create(
            model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
            temperature=0.2,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return r.choices[0].message.content
    except Exception as e:
        print("LLM error:", e)
        return None