import json, time
from collections import Counter
from datetime import datetime, timedelta
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt
from .db import *
from . import simulator, rag, llm

LABEL = {"db_connection": "Database Connection Exhaustion", "bad_deployment": "Bad Deployment", "memory_leak": "Memory Leak", "slow_query": "Slow Database Query"}
ACTIONS = {"db_connection": ["restart_service", "scale_service"], "bad_deployment": ["rollback_deployment", "restart_service"],
           "memory_leak": ["restart_service", "scale_service"], "slow_query": ["clear_workload", "restart_service"]}
RISK = {"restart_service": "medium", "rollback_deployment": "medium", "scale_service": "low", "clear_workload": "low"}

class State(TypedDict, total=False):
    incident_id: str; evidence: dict; cause: str; action: str; approved: bool; verified: bool

def step(iid, name, detail=""):
    with Session() as s: s.add(Step(incident_id=iid, ts=datetime.utcnow(), step=name, detail=detail)); s.commit()
def setf(iid, **kw):
    with Session() as s:
        i = s.get(Incident, iid)
        for k, v in kw.items(): setattr(i, k, v)
        s.commit()

def tools(iid):  # read-only investigation tools over SQL Server
    with Session() as s:
        inc = s.get(Incident, iid)
        logs = [r for r in s.query(Log).filter_by(incident_id=iid) if r.level != "INFO"]
        sm = s.query(SystemMetric).filter_by(incident_id=iid).order_by(SystemMetric.ts).all()
        dm = s.query(DbMetric).filter_by(incident_id=iid).order_by(DbMetric.ts).all()
        dep = [d for d in s.query(Deployment).filter_by(incident_id=iid, service=inc.service) if inc.created_at - timedelta(minutes=30) <= d.ts <= inc.created_at]
        infra = [e.kind for e in s.query(InfraEvent).filter_by(incident_id=iid)]
        avg = lambda rows, k: sum(getattr(r, k) for r in rows[:10]) / 10
        return dict(
            logs=dict(count=len(logs), top=Counter(r.message for r in logs).most_common(3)),
            metrics=dict(lat0=avg(sm, "latency_ms"), lat=sm[-1].latency_ms, err0=avg(sm, "error_rate"), err=sm[-1].error_rate, mem0=avg(sm, "memory"), mem=sm[-1].memory, cpu=sm[-1].cpu),
            db=dict(conn=dm[-1].conn, max=dm[-1].max_conn, q=dm[-1].avg_query_ms, slow=dm[-1].slow_queries),
            deploys=[f"{d.service} {d.version} deployed {int((inc.created_at - d.ts).total_seconds() // 60)} min before alert" for d in dep], infra=infra)

def facts(e):
    m, d = e["metrics"], e["db"]
    f = [f"DB connections: {d['conn']}/{d['max']}", f"Error rate: {m['err0']:.1f}% to {m['err']:.1f}%", f"API latency: {m['lat0']:.0f}ms to {m['lat']:.0f}ms",
         f"Memory: {m['mem0']:.0f}% to {m['mem']:.0f}%", f"Slow queries: {d['slow']}, avg query {d['q']:.0f}ms"]
    f.append(e["deploys"][0] if e["deploys"] else "No deployment in the last 30 minutes")
    if e["infra"]: f.append(f"Infrastructure: {len(e['infra'])}x {e['infra'][0]}")
    if e["logs"]["top"]: f.append(f"Top log: {e['logs']['top'][0][0]}")
    return f

def score(e):
    m, d, dep, inf = e["metrics"], e["db"], e["deploys"], e["infra"]; msg = " ".join(x[0].lower() for x in e["logs"]["top"])
    return {"db_connection": (d["conn"] / d["max"] > .85) * .5 + ("connection" in msg) * .3 + (not dep) * .1 + (m["cpu"] < 60) * .1,
            "bad_deployment": bool(dep) * .5 + (m["err"] > 10) * .2 + ("exception" in msg) * .3,
            "memory_leak": (m["mem"] > 85) * .5 + bool(inf) * .3 + ("memory" in msg or "gc" in msg) * .2,
            "slow_query": (d["slow"] > 40) * .4 + (d["q"] > 1000) * .3 + ("query" in msg) * .2 + (d["conn"] / d["max"] < .7) * .1}

def triage(st):
    setf(st["incident_id"], status="investigating"); step(st["incident_id"], "Triage", "Checking logs, metrics, database and deployments"); return {}

def investigate(st):
    iid = st["incident_id"]; setf(iid, status="investigating"); e = tools(iid)
    for name, d in [("Logs analysis", f"{e['logs']['count']} warnings/errors. Top: {e['logs']['top'][:2]}"),
                    ("Metrics analysis", f"Error rate {e['metrics']['err']:.1f}%, latency {e['metrics']['lat']:.0f}ms, CPU {e['metrics']['cpu']:.0f}%, memory {e['metrics']['mem']:.0f}%"),
                    ("Database analysis", f"Connections {e['db']['conn']}/{e['db']['max']}, slow queries {e['db']['slow']}"),
                    ("Deployment analysis", "; ".join(e["deploys"]) or "No deployment in the last 30 minutes")]:
        time.sleep(.8); step(iid, name, d)
    return {"evidence": e}

def root_cause(st):
    iid, e = st["incident_id"], st["evidence"]; sc = score(e); top = max(sc, key=sc.get); f = facts(e)
    why = llm.ask("You are IncidentAI, an SRE agent. Explain the root cause in 2 short sentences using only the evidence.", f"Root cause: {LABEL[top]}\nEvidence:\n" + "\n".join(f)) \
        or f"{LABEL[top]} is the strongest candidate: " + "; ".join(f[:4]) + "."
    setf(iid, root_cause=top, confidence=round(min(.99, sc[top]), 2), reasoning=why, evidence=json.dumps({"facts": f, "scores": sc}))
    step(iid, "Root cause identified", f"{LABEL[top]} ({min(.99, sc[top]):.0%})"); return {"cause": top}

def recommend(st):
    iid, cause = st["incident_id"], st["cause"]
    with Session() as s: tried = json.loads(s.get(Incident, iid).tried)
    hits = rag.search(LABEL[cause] + " " + " ".join(facts(st["evidence"])))
    step(iid, "Knowledge retrieval (RAG)", ", ".join(h["title"] for h in hits))
    nxt = next((a for a in ACTIONS[cause] if a not in tried), None)
    if not nxt: return {"action": ""}
    with Session() as s:
        i = s.get(Incident, iid); i.action, i.risk, i.status = nxt, RISK[nxt], "awaiting_approval"; i.reasoning = i.reasoning.split("\n\nRunbook:")[0] + "\n\nRunbook: " + hits[0]["text"]; s.commit()
    step(iid, "Recommendation generated", f"{nxt} (risk: {RISK[nxt]})"); return {"action": nxt}

def approval(st):
    return {"approved": bool(interrupt({"incident_id": st["incident_id"], "action": st["action"]})["approved"])}

def reject(st):
    with Session() as s: i = s.get(Incident, st["incident_id"]); i.tried = json.dumps(json.loads(i.tried) + [st["action"]]); s.commit()
    return {}

def execute(st):
    iid = st["incident_id"]; setf(iid, status="executing")
    with Session() as s: i = s.get(Incident, iid); i.tried = json.dumps(json.loads(i.tried) + [st["action"]]); s.commit()
    step(iid, "Action executed", simulator.apply_action(iid, st["action"])); return {}

def verify(st):
    iid = st["incident_id"]; time.sleep(1)
    with Session() as s:
        sm = s.query(SystemMetric).filter_by(incident_id=iid).order_by(SystemMetric.ts).all(); dm = s.query(DbMetric).filter_by(incident_id=iid).order_by(DbMetric.ts).all()
        b, a, bd, ad = sm[-4], sm[-1], dm[-4], dm[-1]
    ok = a.error_rate < 5 and a.latency_ms < 500 and ad.conn < 100
    v = dict(passed=ok, before=dict(error_rate=b.error_rate, latency_ms=b.latency_ms, conn=bd.conn), after=dict(error_rate=a.error_rate, latency_ms=a.latency_ms, conn=ad.conn))
    setf(iid, verification=json.dumps(v), status="resolved" if ok else "investigating")
    step(iid, "Verification passed" if ok else "Verification failed", f"Error rate {b.error_rate}% to {a.error_rate}%, latency {b.latency_ms}ms to {a.latency_ms}ms, connections {bd.conn} to {ad.conn}")
    return {"verified": ok}

def escalate(st):
    setf(st["incident_id"], status="escalated", action=None); step(st["incident_id"], "Escalated to on-call engineer", "No remaining safe actions"); return {}

g = StateGraph(State)
for n, f in [("triage", triage), ("investigate", investigate), ("root_cause", root_cause), ("recommend", recommend), ("approval", approval),
             ("reject", reject), ("execute", execute), ("verify", verify), ("escalate", escalate)]: g.add_node(n, f)
g.add_edge(START, "triage"); g.add_edge("triage", "investigate"); g.add_edge("investigate", "root_cause"); g.add_edge("root_cause", "recommend")
g.add_conditional_edges("recommend", lambda s: "approval" if s["action"] else "escalate", {"approval": "approval", "escalate": "escalate"})
g.add_conditional_edges("approval", lambda s: "execute" if s["approved"] else "reject", {"execute": "execute", "reject": "reject"})
g.add_edge("reject", "investigate"); g.add_edge("execute", "verify")
g.add_conditional_edges("verify", lambda s: END if s["verified"] else "investigate", {END: END, "investigate": "investigate"})
g.add_edge("escalate", END)
graph = g.compile(checkpointer=MemorySaver())
