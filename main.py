from fastapi import FastAPI, Request
from pydantic import BaseModel
from google.cloud import firestore
from openai import OpenAI, OpenAIError
from datetime import datetime
import uuid
import os
import json

app = FastAPI()

# Initialize Firestore
db = firestore.Client()
categories_collection = db.collection("domain_categories")
summaries_collection = db.collection("category_summaries")

# OpenAI client using environment variable
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Local usage log file
USAGE_LOG = "usage_log.json"

if not os.path.exists(USAGE_LOG):
    with open(USAGE_LOG, "w") as f:
        json.dump({}, f)


# ---------- 📦 MODELS ----------
class UsageReport(BaseModel):
    userId: str
    timestamp: int
    usage: dict


# ---------- 🌐 ENDPOINTS ----------

@app.post("/get-category-mapping")
async def get_category_mapping(request: Request):
    data = await request.json()
    domains = data.get("domains", [])
    response = {}

    for domain in domains:
        doc = categories_collection.document(domain).get()
        if doc.exists:
            response[domain] = doc.to_dict().get("category", "Uncategorized")
        else:
            try:
                prompt = f"Categorize the domain '{domain}' into one of the following categories: Social Media, Entertainment, Work/Productivity, Shopping, Education, News, Other. Respond with just the category."

                completion = client.chat.completions.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": "You are a helpful classifier."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=10
                )
                category = completion.choices[0].message.content.strip()
                if not category:
                    category = "Uncategorized"
            except OpenAIError as e:
                print(f"❌ LLM error for domain {domain}: {str(e)}")
                category = "Uncategorized"

            categories_collection.document(domain).set({"category": category})
            response[domain] = category

    return response


@app.post("/submit-category-summary")
async def submit_category_summary(request: Request):
    data = await request.json()
    timestamp = data.get("timestamp")
    category_summary = data.get("categorySummary", {})

    if not timestamp or not category_summary:
        return {"error": "Missing timestamp or category summary"}

    summaries_collection.document(timestamp).set({
        "timestamp": timestamp,
        "summary": category_summary
    })

    return {"status": "success"}


@app.get("/get-summary-history")
async def get_summary_history():
    summaries = summaries_collection.stream()
    result = []
    for summary in summaries:
        data = summary.to_dict()
        result.append({
            "timestamp": data["timestamp"],
            "summary": data["summary"]
        })
    result.sort(key=lambda x: datetime.strptime(x["timestamp"], "%Y-%m-%d"))
    return result


@app.post("/track-usage")
async def track_usage(report: UsageReport):
    with open(USAGE_LOG, "r+") as f:
        logs = json.load(f)
        user_id = report.userId

        if user_id not in logs:
            logs[user_id] = {
                "totalCalls": 0,
                "totalCost": 0.0,
                "lastActive": None,
                "id": str(uuid.uuid4())
            }

        logs[user_id]["totalCalls"] += report.usage.get("llmCall", 0)
        logs[user_id]["totalCost"] += report.usage.get("cost", 0)
        logs[user_id]["lastActive"] = datetime.utcfromtimestamp(report.timestamp / 1000).isoformat()

        f.seek(0)
        json.dump(logs, f, indent=2)
        f.truncate()

    return {"status": "success", "userId": user_id}


@app.get("/usage")
async def get_all_usage():
    with open(USAGE_LOG, "r") as f:
        return json.load(f)


@app.get("/health")
async def health():
    return {"status": "ok"}
