from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from .db import Session, Incident
RUNBOOKS = [
    dict(title="Runbook: database connection exhaustion", text="Symptoms: active connections near max, connection timeout errors, pool exhausted, high latency, no recent deployment. Fix: restart the service to release stale connections, then scale or tune the pool."),
    dict(title="Runbook: bad deployment", text="Symptoms: error rate and latency rise minutes after a deployment, exceptions in new release. Fix: roll back the deployment to the previous version."),
    dict(title="Runbook: memory leak", text="Symptoms: memory climbing continuously, container restarts, GC pressure, out of memory warnings. Fix: restart the service, then investigate the leak and scale out."),
    dict(title="Runbook: slow database query", text="Symptoms: slow queries, high average query time, table scans, query timeouts while connections stay moderate. Fix: clear the problematic workload, then add indexes."),
]
def search(q, k=2):
    docs = list(RUNBOOKS)
    with Session() as s:
        for i in s.query(Incident).filter_by(status="resolved"):
            docs.append(dict(title=f"Past incident {i.id}", text=f"{i.root_cause} {i.reasoning} resolved by {i.action}"))
    X = TfidfVectorizer(stop_words="english").fit_transform([d["title"] + " " + d["text"] for d in docs] + [q])
    sims = cosine_similarity(X[-1], X[:-1])[0]
    return [docs[j] for j in sims.argsort()[::-1][:k]]
