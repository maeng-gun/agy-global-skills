import os, json, httpx
from dotenv import load_dotenv
load_dotenv()

headers = {
    "Authorization": f"Bearer {os.getenv('NOTION_API_KEY')}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

db_id = os.getenv("NOTION_DB_ID")
res = httpx.post(f"https://api.notion.com/v1/databases/{db_id}/query", headers=headers)
data = res.json()
if "results" in data and len(data["results"]) > 0:
    print(json.dumps(data["results"][0].get("properties", {}), ensure_ascii=False, indent=2))
else:
    print(data)
