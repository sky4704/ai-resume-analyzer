from openai import OpenAI
from dotenv import load_dotenv
import json
import os

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def resume_analyzer(resume_text, user_role):
    prompt = f"""
You are a senior software engineer and hiring manager.

Evaluate the resume based on the user's role and requirements.

User role: "{user_role}"

STRICT RULES:
- Only output the skills that are related to the user's role
- REMOVE irrelevant tools [Excel for backend, etc]
- Identify real missing gaps
- Generate roadmap only for missing fields
- Make output DIFFERENT based on user's role or goal

Return only JSON:
{{
"skills": [],
"missing_skills": [],
"roadmap": [],
"interview_questions": []
}}

Resume:
{resume_text}


"""
    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            temperature=0.3,
            messages=[
                {"role": "system", "content": "You are a strict hisring manager."},
                {"role": "user", "content": prompt},
            ]
        )

        content = response.choices[0].message.content.strip()
        start = content.find("{")
        end = content.rfind("}")+1
        return json.loads(content[start:end])
    except Exception as e:
        return {
            "skills": [],
            "missing_skills": [],
            "roadmap": [],
            "interview_questions": [],
            "error": f"Error: {str(e)}"
        }