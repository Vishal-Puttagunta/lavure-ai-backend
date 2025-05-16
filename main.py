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
    allow_origins=["http://localhost:3000", "https://your-frontend-production-url.com", "https://prodai-iyfp-bmo2s63bw-vishal-puttaguntas-projects.vercel.app"],
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
        f"{username} – {info['completed']}/{info['assigned']} tasks completed. Notes: {'; '.join(info['notes']) or 'None'}"
        for username, info in user_summary_map.items()
    ])

    # Construct the prompt for GPT
    prompt = (
        f"Generate a weekly productivity report for the team.\n"
        f"- Total Tasks: {total_tasks}\n"
        f"- Completed: {completed_tasks}\n"
        f"- Organization: {organization_name} (ID: {request.org_id})\n\n"
        f"Users:\n{user_summaries}\n\n"
        f"Format like a professional weekly team summary with highlights, snapshots, and upcoming goals."
    )

    # Generate report text
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are an AI assistant generating professional team productivity reports."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=800,
        temperature=0.7
    )
    report_text = response.choices[0].message.content

    # Render HTML and PDF
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, sans-serif;
                font-size: 16px;
                color: #222;
                line-height: 1.8;
                padding: 40px;
            }}
            h1 {{
                font-size: 28px;
                color: #0077cc;
                margin-bottom: 10px;
            }}
            hr {{
                margin: 20px 0;
            }}
            pre {{
                white-space: pre-wrap;
                word-wrap: break-word;
                font-size: 16px;
            }}
        </style>
    </head>
    <body>
        <h1>Team Productivity Report</h1>
        <hr>
        <pre>{report_text}</pre>
    </body>
    </html>
    """

    filename = f"report_{uuid.uuid4().hex}.pdf"
    HTML(string=html_content).write_pdf(filename)

    return FileResponse(filename, media_type="application/pdf", filename="team-report.pdf")
