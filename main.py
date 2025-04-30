from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from google.cloud import firestore
from openai import OpenAI, OpenAIError
from datetime import datetime, timedelta
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
    try:
        data = await request.json()
        timestamp_str = data.get("timestamp")  # Expects ISO format "2025-05-01T12:00:00Z"
        category_summary = data.get("categorySummary", {})
        user_id = data.get("userId")

        if not timestamp_str or not category_summary or not user_id:
            return {"error": "Missing required fields"}

        try:
            # Parse and store with full timestamp precision
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            day = timestamp.date().isoformat()  # Extract just the date part
            
            summaries_collection.document(timestamp_str).set({
                "timestamp": timestamp_str,
                "day": day,  # Store date separately for querying
                "userId": user_id,
                "summary": category_summary
            })
            
            return {"status": "success"}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid timestamp format: {str(e)}")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/get-summary-history")
async def get_summary_history(day: str, userId: str = None):
    try:
        # Validate date format
        datetime.strptime(day, "%Y-%m-%d")
        
        # Query for the entire day
        query = summaries_collection.where("day", "==", day)
        if userId:
            query = query.where("userId", "==", userId)
            
        docs = query.stream()
        
        result = []
        for doc in docs:
            data = doc.to_dict()
            result.append({
                "timestamp": data["timestamp"],
                "userId": data["userId"],
                "summary": data["summary"]
            })
            
        # Sort by timestamp
        result.sort(key=lambda x: x["timestamp"])
        return result
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
