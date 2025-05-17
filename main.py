from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
from fastapi.responses import FileResponse
from supabase import create_client, Client
from weasyprint import HTML
import os
import uuid
from collections import defaultdict

# Load environment variables
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Connect to Supabase
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

# Set up FastAPI app
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "https://lavureai.com",
        "https://www.lavureai.com",
        "https://prodai-iyfp-bmo2s63bw-vishal-puttaguntas-projects.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request model
class ReportRequest(BaseModel):
    org_id: str

@app.post("/generate-report")
async def generate_report(request: ReportRequest):
    # Fetch tasks from Supabase
    tasks_response = supabase.table("tasks").select("*").eq("team_id", request.org_id).execute()
    tasks = tasks_response.data

    total_tasks = len(tasks)
    completed_tasks = sum(1 for t in tasks if str(t.get("status", "")).lower() == "finished")
    organization_name = tasks[0].get("organization_name", "Unknown Org") if tasks else "Unknown Org"

    # Build user summaries
    user_summary_map = defaultdict(lambda: {"assigned": 0, "completed": 0, "notes": []})

    for task in tasks:
        username = task.get("username") or "Unknown"
        user_summary_map[username]["assigned"] += 1
        if str(task.get("status", "")).lower() == "finished":
            user_summary_map[username]["completed"] += 1
        if task.get("notes"):
            user_summary_map[username]["notes"].append(task["notes"])

    user_summaries = "\n".join([
        f"{username}: {info['completed']}/{info['assigned']} tasks completed. Notes: {'; '.join(info['notes']) or 'None'}"
        for username, info in user_summary_map.items()
    ])

    # Construct GPT prompt
    prompt = (
        f"Generate a weekly productivity report for the team in clean, readable HTML format. "
        f"Use structured sections with headings, bullet points, and tables where appropriate. Avoid markdown, asterisks, or code blocks.\n\n"
        f"- Total Tasks: {total_tasks}\n"
        f"- Completed: {completed_tasks}\n"
        f"- Organization: {organization_name} (ID: {request.org_id})\n\n"
        f"Users:\n{user_summaries}\n\n"
    )

    # Generate report HTML from GPT-4o
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are an AI assistant generating clean, professional HTML reports for productivity summaries."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=1000,
        temperature=0.7
    )
    report_html = response.choices[0].message.content

    # Render final HTML for PDF
    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, sans-serif;
                font-size: 16px;
                color: #222;
                line-height: 1.7;
                padding: 40px;
            }}
            h1, h2, h3 {{
                color: #0077cc;
                margin-bottom: 10px;
            }}
            p {{
                margin-bottom: 15px;
            }}
            ul, ol {{
                margin-bottom: 20px;
                padding-left: 25px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 20px;
            }}
            th, td {{
                border: 1px solid #ccc;
                padding: 8px;
                text-align: left;
            }}
            th {{
                background-color: #f4f4f4;
            }}
        </style>
    </head>
    <body>
        {report_html}
    </body>
    </html>
    """

    filename = f"report_{uuid.uuid4().hex}.pdf"
    HTML(string=full_html).write_pdf(filename)

    return FileResponse(filename, media_type="application/pdf", filename="team-report.pdf")
