import asyncio
import httpx
import json
import time

SCENARIOS = [
    {
        "description": "Refonte du SI hospitalier et intégration de la télémédecine avec haute disponibilité et sécurité HDS.",
        "mode": "standard"
    },
    {
        "description": "Audit de sécurité cyber, test d'intrusion, et mise en place d'un SOC/SIEM pour un opérateur d'importance vitale.",
        "mode": "brief"
    },
    {
        "description": "Développement d'une plateforme de traitement de données géospatiales et satellitaires en temps réel.",
        "mode": "standard"
    },
    {
        "description": "Migration Cloud AWS de l'infrastructure e-commerce avec architecture microservices et Kubernetes.",
        "mode": "standard"
    },
    {
        "description": "Système de détection des fraudes bancaires basé sur l'IA et le Machine Learning pour la banque de détail.",
        "mode": "brief"
    }
]

async def get_token(client):
    resp = await client.post("http://backend:8080/api/auth/login", json={"username": "admin", "password": "medord"})
    if resp.status_code == 200:
        return resp.json().get("token")
    return None

async def run_scenario(client, token, index, payload):
    print(f"\n--- Running Scenario {index + 1} ({payload['mode']} mode) ---")
    print(f"Description: {payload['description']}")
    
    start_time = time.monotonic()
    
    try:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        response = await client.post(
            "http://backend:8080/api/rfp/generate",
            json=payload,
            headers=headers,
            timeout=120.0
        )
        latency = time.monotonic() - start_time
        
        if response.status_code == 200:
            data = response.json()
            metrics = data.get("metrics", {})
            status = data.get("status", "unknown")
            mode_final = data.get("quality", {}).get("generation_mode", "unknown")
            tokens = metrics.get("word_count", 0) * 1.5 # rough token estimation since we don't have exact token count in metrics, wait, let's just use word count.
            
            print(f"SUCCESS in {latency:.2f}s")
            print(f"Status: {status}")
            print(f"Final Generation Mode: {mode_final}")
            print(f"Total Sections: {metrics.get('section_count', 0)}")
            print(f"Total Words: {metrics.get('word_count', 0)}")
            
            # Save the JSON
            with open(f"scenario_{index+1}_output.json", "w") as f:
                json.dump(data, f, indent=2)
                
        else:
            print(f"FAILED in {latency:.2f}s with status {response.status_code}")
            print(response.text)
            
    except Exception as e:
        latency = time.monotonic() - start_time
        print(f"ERROR in {latency:.2f}s: {e}")

async def main():
    async with httpx.AsyncClient() as client:
        token = await get_token(client)
        if not token:
            print("Failed to get token!")
            return
            
        for i, scenario in enumerate(SCENARIOS):
            await run_scenario(client, token, i, scenario)
            
if __name__ == "__main__":
    asyncio.run(main())
