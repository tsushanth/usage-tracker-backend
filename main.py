from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from google.cloud import firestore
from openai import OpenAI, OpenAIError
from datetime import datetime
import uuid
import os
import re
import json
from dotenv import load_dotenv
load_dotenv()

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
        # Skip empty or invalid domains
        if not domain or domain.strip() == "/":
            response[domain] = "Uncategorized"
            continue
            
        try:
            doc = categories_collection.document(domain).get()
            if doc.exists:
                response[domain] = doc.to_dict().get("category", "Uncategorized")
            else:
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

                categories_collection.document(domain).set({"category": category})
                response[domain] = category
                
        except Exception as e:
            print(f"❌ Error processing domain {domain}: {str(e)}")
            response[domain] = "Uncategorized"

    return response

def is_valid_domain(domain):
    if not domain:
        return False
    # Simple domain format validation
    return bool(re.match(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', domain))

@app.post("/submit-category-summary")
async def submit_category_summary(request: Request):
    data = await request.json()
    timestamp = data.get("timestamp")
    category_summary = data.get("categorySummary", {})
    user_id = data.get("userId")

    if not timestamp or not category_summary or not user_id:
        return {"error": "Missing required fields: timestamp, categorySummary, or userId"}

    summaries_collection.document(timestamp).set({
        "timestamp": timestamp,
        "userId": user_id,  # Added userId to Firestore document
        "summary": category_summary
    })

    return {"status": "success"}


@app.get("/get-summary-history")
async def get_summary_history(userId: str = None):
    try:
        summaries = summaries_collection.stream()
        result = []

        for summary in summaries:
            data = summary.to_dict()

            # Validate required fields exist
            timestamp = data.get("timestamp")
            summary_data = data.get("summary")
            doc_user_id = data.get("userId")

            if not timestamp or not summary_data:
                continue  # Skip if required fields are missing

            # Filter by userId if provided
            if userId and doc_user_id != userId:
                continue

            try:
                # Attempt to parse date for sorting
                parsed_date = datetime.strptime(timestamp, "%Y-%m-%d")
            except ValueError:
                continue  # Skip if timestamp is not in valid format

            result.append({
                "timestamp": timestamp,
                "userId": doc_user_id,  # Include userId in response
                "summary": summary_data
            })

        # Sort using parsed datetime for accuracy
        result.sort(key=lambda x: datetime.strptime(x["timestamp"], "%Y-%m-%d"))
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch summary history: {str(e)}")


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
