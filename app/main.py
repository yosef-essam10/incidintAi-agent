import json, traceback
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from langgraph.types import Command
from .db import *
from . import simulator, rag, llm
from .agent import graph, LABEL, step
ROOT = Path(__file__).resolve().parent.parent

@asynccontextmanager
async def life(app):
    ensure_database(); Base.metadata.create_all(engine); yield
app = FastAPI(title="IncidentAI", lifespan=life)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

def run(iid, payload):
    try: graph.invoke(payload, {"configurable": {"thread_id": iid}})
    except Exception as e:
        traceback.print_exc()
        with Session() as s: s.get(Incident, iid).status = "error"; s.commit()
        step(iid, "Agent error", str(e)[:300])

def brief(i): return dict(id=i.id, service=i.service, severity=i.severity, status=i.status, root_cause=LABEL.get(i.root_cause, "Investigating"))

@app.get("/")
def index(): return FileResponse(ROOT / "static" / "index.html")

class Sim(BaseModel): scenario: str
@app.post("/api/simulate")
def simulate(b: Sim, bg: BackgroundTasks):
    if b.scenario not in simulator.TARGET: raise HTTPException(400, "Unknown scenario")
    iid = simulator.generate(b.scenario); bg.add_task(run, iid, {"incident_id": iid}); return {"id": iid}

@app.get("/api/incidents")
def incidents():
    with Session() as s: return [brief(i) for i in s.query(Incident).order_by(Incident.id.desc())]

@app.get("/api/incidents/{iid}")
def detail(iid: str):
    with Session() as s:
        i = s.get(Incident, iid)
        if not i: raise HTTPException(404)
        sm = s.query(SystemMetric).filter_by(incident_id=iid).order_by(SystemMetric.ts).all(); dm = s.query(DbMetric).filter_by(incident_id=iid).order_by(DbMetric.ts).all()
        return {**brief(i), "confidence": i.confidence, "evidence": json.loads(i.evidence or "{}").get("facts", []), "reasoning": i.reasoning, "action": i.action, "risk": i.risk,
                "verification": json.loads(i.verification) if i.verification else None,
                "timeline": [dict(step=t.step, detail=t.detail) for t in s.query(Step).filter_by(incident_id=iid).order_by(Step.id)],
                "chat": [dict(role=c.role, content=c.content) for c in s.query(Chat).filter_by(incident_id=iid).order_by(Chat.id)],
                "series": [dict(t=m.ts.strftime("%H:%M"), latency=m.latency_ms, errors=m.error_rate, conn=d.conn) for m, d in zip(sm, dm)]}

def decide(iid, ok, bg):
    with Session() as s:
        i = s.get(Incident, iid)
        if not i or i.status != "awaiting_approval": raise HTTPException(409, "Incident is not awaiting approval")
        i.status = "executing" if ok else "investigating"; s.commit()
    step(iid, "Engineer approved" if ok else "Engineer rejected", i.action)
    bg.add_task(run, iid, Command(resume={"approved": ok})); return {"ok": True}
@app.post("/api/incidents/{iid}/approve")
def approve(iid: str, bg: BackgroundTasks): return decide(iid, True, bg)
@app.post("/api/incidents/{iid}/reject")
def reject(iid: str, bg: BackgroundTasks): return decide(iid, False, bg)

class Msg(BaseModel): message: str
def fallback(i, q, facts):
    q = q.lower(); v = json.loads(i.verification) if i.verification else None
    if "evidence" in q: return "Evidence:\n" + "\n".join("- " + f for f in facts)
    if "rollback" in q: return ("No deployment was detected before the incident, so rollback was not supported by the evidence." if any("No deployment" in f for f in facts) else "A recent deployment was detected, so rollback is a valid option.")
    if any(w in q for w in ("resolved", "work", "fixed")): return f"Verification: {v['before']} -> {v['after']}. Passed: {v['passed']}" if v else "Not verified yet."
    if any(w in q for w in ("did you do", "action")): return f"Action: {i.action or 'none'}. Status: {i.status}."
    return i.reasoning or "Investigation in progress."

@app.post("/api/incidents/{iid}/chat")
def chat(iid: str, b: Msg):
    with Session() as s:
        i = s.get(Incident, iid)
        if not i: raise HTTPException(404)
        facts = json.loads(i.evidence or "{}").get("facts", []); steps = [f"{t.step}: {t.detail}" for t in s.query(Step).filter_by(incident_id=iid).order_by(Step.id)]
        ctx = json.dumps(dict(incident=brief(i), confidence=i.confidence, action=i.action, risk=i.risk, reasoning=i.reasoning, evidence=facts, verification=i.verification, steps=steps))
        kb = "\n".join(d["text"] for d in rag.search(b.message + " " + (i.root_cause or ""), 2))
        ans = llm.ask("You are IncidentAI, an incident investigation assistant. Answer only from the context. Be concise.", f"Context: {ctx}\nKnowledge base: {kb}\nQuestion: {b.message}") or fallback(i, b.message, facts)
        s.add(Chat(incident_id=iid, role="user", content=b.message, ts=datetime.utcnow())); s.add(Chat(incident_id=iid, role="agent", content=ans, ts=datetime.utcnow())); s.commit()
    return {"answer": ans}
