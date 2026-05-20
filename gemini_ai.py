from google import genai
from dotenv import load_dotenv
import os
import json

load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)


def resume_analyzer(resume_text, user_role):

    prompt = f"""
You are an expert ATS analyzer, senior hiring manager, and career mentor.

Analyze the resume STRICTLY for the target role.

TARGET ROLE:
{user_role}

TASKS:
1. Extract ONLY relevant technical and professional skills
2. Ignore unrelated tools and technologies
3. Identify realistic missing skills
4. Generate beginner-friendly improvement roadmap
5. Generate practical interview questions
6. Keep recommendations concise and useful
7. Tailor output specifically to the target role

IMPORTANT RULES:
- Return ONLY valid JSON
- No markdown
- No explanation
- No extra text
- No code block
- No comments

JSON FORMAT:

{{  
    "target_role": "",
    "summary": "",
    "resume_score": 0,
    "skills": [],
    "missing_skills": [],
    "roadmap": [],
    "interview_questions": []
}}

RESUME:

{resume_text[:12000]}
"""

    try:

        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt
        )

        content = response.text.strip()

        print("RAW GEMINI RESPONSE:")
        print(content)

        start = content.find("{")
        end = content.rfind("}")

        if start == -1 or end == -1:

            raise ValueError(
                "No valid JSON found in AI response"
            )

        json_text = content[start:end + 1]

        parsed = json.loads(json_text)

        # Safety fallback keys

        parsed.setdefault("target_role", "")

        parsed.setdefault("summary", "")

        parsed.setdefault("resume_score", 0)

        parsed.setdefault("skills", [])

        parsed.setdefault("missing_skills", [])

        parsed.setdefault("roadmap", [])

        parsed.setdefault("interview_questions", [])

        return parsed

    except json.JSONDecodeError as e:

        print("JSON ERROR:", e)

        return {
            "target_role": "",
            "summary": "",
            "resume_score": 0,
            "skills": [],
            "missing_skills": [],
            "roadmap": [],
            "interview_questions": [],
            "error": "AI returned invalid response"
        }

    except Exception as e:

        print("GEMINI ERROR:", e)

        return {
            "target_role": "",
            "summary": "",
            "resume_score": 0,
            "skills": [],
            "missing_skills": [],
            "roadmap": [],
            "interview_questions": [],
            "error": "AI service temporarily unavailable"
        }