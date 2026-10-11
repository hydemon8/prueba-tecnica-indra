"""Consulta la API pública de precios de Azure (sin autenticación) y guarda los medidores relevantes."""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://prices.azure.com/api/retail/prices?"
R = sys.argv[1]
OUT = sys.argv[2]
REG = f"armRegionName eq '{R}' and priceType eq 'Consumption'"


def q(flt, pages=2):
    url = BASE + urllib.parse.urlencode({"$filter": f"{flt} and {REG}", "$top": 100})
    out = []
    for _ in range(pages):
        for attempt in range(6):
            try:
                with urllib.request.urlopen(url, timeout=60) as r:
                    d = json.load(r)
                break
            except urllib.error.HTTPError as e:
                if e.code != 429:
                    raise
                time.sleep(8 * (attempt + 1))
        else:
            raise RuntimeError("429 persistente")
        out += d["Items"]
        url = d.get("NextPageLink")
        time.sleep(2)
        if not url:
            break
    return out


QUERIES = {
    "container_apps": "serviceName eq 'Azure Container Apps' and skuName eq 'Standard'",
    "postgres_burstable": "serviceName eq 'Azure Database for PostgreSQL' and contains(productName,'Flexible Server') and contains(productName,'Burstable')",
    "postgres_storage": "serviceName eq 'Azure Database for PostgreSQL' and contains(productName,'Flexible Server Storage')",
    "blob_hot_lrs": "serviceName eq 'Storage' and productName eq 'Blob Storage' and skuName eq 'Hot LRS'",
    "container_registry": "serviceName eq 'Container Registry' and skuName eq 'Basic'",
    "key_vault": "serviceName eq 'Key Vault' and skuName eq 'Standard'",
    "log_analytics": "serviceName eq 'Log Analytics'",
    "iot_hub": "serviceName eq 'IoT Hub'",
    "event_hubs": "serviceName eq 'Event Hubs' and skuName eq 'Standard'",
    "ai_search": "serviceName eq 'Azure Cognitive Search'",
    "api_management": "serviceName eq 'API Management'",
    "vm_d4s_v5": "serviceName eq 'Virtual Machines' and armSkuName eq 'Standard_D4s_v5'",
    "openai_mini": "contains(productName,'OpenAI') and contains(meterName,'mini')",
    "openai_nano": "contains(productName,'OpenAI') and contains(meterName,'nano')",
}
data = {}
for name, flt in QUERIES.items():
    try:
        items = q(flt)
    except Exception as e:  # noqa: BLE001
        print(name, "ERROR", e)
        continue
    rows = sorted({(i["productName"], i["skuName"], i["meterName"], i["unitOfMeasure"], i["retailPrice"], i.get("tierMinimumUnits", 0))
                   for i in items if i["retailPrice"] > 0 or name == "key_vault"})
    data[name] = [dict(zip(("product", "sku", "meter", "unit", "usd", "tier_min"), r)) for r in rows]
    print(f"\n=== {name} ({len(rows)})")
    for r in rows[:22]:
        print(f"  {r[0][:42]:42} | {r[1][:22]:22} | {r[2][:40]:40} | {r[4]:<11} {r[3]} (desde {r[5]})")
json.dump({"region": R, "consultado": time.strftime("%Y-%m-%d"), "fuente": "https://prices.azure.com/api/retail/prices",
           "moneda": "USD", "medidores": data}, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
