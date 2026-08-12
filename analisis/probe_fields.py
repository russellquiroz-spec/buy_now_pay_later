"""Muestra de esquema real por coleccion relevante."""
from pymongo import MongoClient, DESCENDING

from mongo_extractor.config import load_config
from mongo_extractor.extractor import _render_uri
from mongo_extractor.tunnel import open_tunnel

TARGET = [
    "credit-order-production",
    "payment-report-production",
    "fintech-customers-production",
    "fintech-credit-request-production",
    "fintech-credit-approval-production",
    "fintech-pre-authorization-status-production",
    "state-of-delivery-report-production",
    "revenue-orders-production",
    "credit-limit-history-management-production",
    "propaga-transaction-dev",
    "propaga-transaction-attempt-dev",
    "fintech-credit-status-state-production",
]

app, profiles = load_config()
cfg = profiles["bnpl"]

with open_tunnel(cfg) as local_port:
    uri = _render_uri(cfg.uri_template, cfg.user, cfg.password)
    client = MongoClient(uri, serverSelectionTimeoutMS=app.server_selection_timeout_ms)
    db = client[cfg.db]

    for name in TARGET:
        coll = db[name]
        print(f"\n{'='*70}\n{name}")
        try:
            docs = list(coll.find({}).sort("_id", DESCENDING).limit(3))
        except Exception as ex:
            print(f"  err: {ex}")
            continue
        keys = {}
        for d in docs:
            for k, v in d.items():
                keys.setdefault(k, type(v).__name__)
        for k, t in sorted(keys.items()):
            sample = docs[0].get(k)
            s = str(sample)
            if len(s) > 70:
                s = s[:70] + "..."
            print(f"  {k} ({t}) = {s}")

    client.close()
