# client_test.py
import requests

url = "http://127.0.0.1:8001/api/retrieval"
payload = {
    "query":"APT38 使用了什么软件",
    "top_k":6
}
resp = requests.post(url, json=payload)
data = resp.json()
print(data)
for r in data["results"]:
    print(f"\nid={r['id']}, score={r['score']}")
    print("actors:", r["entities"]["actors"])
    print("graph_paths:", r["graph_paths"])
    print("text:", r["text"][0:180])