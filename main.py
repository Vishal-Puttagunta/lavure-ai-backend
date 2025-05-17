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

    # Construct the prompt for GPT
    prompt = (
        f"Generate a weekly productivity report for the team in clean, readable HTML format. "
        f"Use structured sections with headings, bullet points, and tables where appropriate. Avoid markdown or asterisks.\n\n"
        f"- Total Tasks: {total_tasks}\n"
        f"- Completed: {completed_tasks}\n"
        f"- Organization: {organization_name}\n\n"
        f"Users:\n{user_summaries}\n\n"
        f"Format like a professional weekly team summary with highlights, snapshots, and upcoming goals. "
        f"Make it pleasant to read and visually clean."
    )

    # Generate report HTML from GPT
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are an AI assistant generating professional team productivity reports in clean HTML."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=1000,
        temperature=0.7
    )
    report_html = response.choices[0].message.content

    # Render final HTML with styling
    full_html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <title>Team Productivity Report</title>
      <style>
        body {{
          font-family: 'Segoe UI', Tahoma, sans-serif;
          font-size: 16px;
          line-height: 1.6;
          color: #333;
          padding: 40px;
          max-width: 800px;
          margin: auto;
        }}
        h1, h2 {{
          color: #0057b8;
        }}
        .header {{
          border-bottom: 2px solid #eee;
          margin-bottom: 20px;
        }}
        table {{
          width: 100%;
          border-collapse: collapse;
          margin: 20px 0;
        }}
        th, td {{
          border: 1px solid #ccc;
          padding: 10px;
          text-align: left;
        }}
        th {{
          background-color: #f2f2f2;
        }}
        ul {{
          padding-left: 20px;
        }}
        .section {{
          margin-bottom: 30px;
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
