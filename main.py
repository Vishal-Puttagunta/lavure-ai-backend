from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
from fastapi.responses import FileResponse
from supabase import create_client, Client
import pdfkit
from pdfkit.configuration import Configuration
import os
import uuid
from collections import defaultdict

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

config = Configuration(wkhtmltopdf=r"C:\\Program Files\\wkhtmltopdf\\bin\\wkhtmltopdf.exe")

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

app = FastAPI()

class ReportRequest(BaseModel):
    org_id: str

@app.post("/generate-report")
async def generate_report(request: ReportRequest):
    # 🔄 Fetch real data from Supabase
    tasks_response = supabase.table("tasks").select("*").eq("team_id", request.org_id).execute()
    tasks = tasks_response.data

    total_tasks = len(tasks)
    completed_tasks = sum(1 for t in tasks if t.get("status") == "done")

    user_summary_map = defaultdict(lambda: {"assigned": 0, "completed": 0, "notes": []})

    for task in tasks:
        uid = task.get("assigned_to") or "Unknown"
        user_summary_map[uid]["assigned"] += 1
        if task.get("status") == "done":
            user_summary_map[uid]["completed"] += 1
        if task.get("notes"):
            user_summary_map[uid]["notes"].append(task["notes"])

    # Format for GPT
    user_summaries = "\n".join([
        f"{uid} – {info['completed']}/{info['assigned']} tasks completed. Notes: {'; '.join(info['notes']) or 'None'}"
        for uid, info in user_summary_map.items()
    ])

    prompt = (
        f"Generate a weekly productivity report for the team.\n"
        f"- Total Tasks: {total_tasks}\n"
        f"- Completed: {completed_tasks}\n"
        f"- Org ID: {request.org_id}\n\n"
        f"Users:\n{user_summaries}\n\n"
        f"Format like a professional weekly team summary with highlights, snapshots, and upcoming goals."
    )

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
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset=\"utf-8\">
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
    pdfkit.from_string(html_content, filename, configuration=config)

    return FileResponse(filename, media_type="application/pdf", filename="team-report.pdf")
