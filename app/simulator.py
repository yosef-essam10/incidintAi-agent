import random
from datetime import datetime, timedelta
from .db import *
SVC = "payment-api"
BASE = dict(cpu=42, memory=55, latency_ms=180, error_rate=1.2, conn=45, avg_query_ms=80, slow_queries=2)
TARGET = {
    "db_connection": dict(cpu=48, memory=58, latency_ms=4800, error_rate=31, conn=196, avg_query_ms=1200, slow_queries=71),
    "bad_deployment": dict(cpu=60, memory=60, latency_ms=2600, error_rate=24, conn=52, avg_query_ms=90, slow_queries=3),
    "memory_leak": dict(cpu=72, memory=95, latency_ms=1800, error_rate=9, conn=50, avg_query_ms=85, slow_queries=2),
    "slow_query": dict(cpu=55, memory=58, latency_ms=3000, error_rate=12, conn=85, avg_query_ms=2500, slow_queries=90)}
FIX = {"db_connection": "restart_service", "bad_deployment": "rollback_deployment", "memory_leak": "restart_service", "slow_query": "clear_workload"}
ALLOWED = {"restart_service", "rollback_deployment", "scale_service", "clear_workload"}
LOGS = {
    "db_connection": [("ERROR", "Database connection timeout"), ("ERROR", "Connection pool exhausted"), ("WARNING", "Unable to acquire connection")],
    "bad_deployment": [("ERROR", "Unhandled exception in PaymentProcessor.charge"), ("ERROR", "Exception rate rising after new release"), ("WARNING", "Elevated 500 responses")],
    "memory_leak": [("WARNING", "GC pressure high, heap at 94%"), ("ERROR", "Out of memory warning in worker pool"), ("WARNING", "Container memory limit near")],
    "slow_query": [("WARNING", "Slow query detected on orders table"), ("ERROR", "Query timeout after 30s"), ("WARNING", "Full table scan on orders")]}

def _rows(s, iid, ts, v):
    s.add(SystemMetric(incident_id=iid, ts=ts, service=SVC, cpu=v["cpu"], memory=v["memory"], latency_ms=v["latency_ms"], error_rate=v["error_rate"]))
    s.add(DbMetric(incident_id=iid, ts=ts, conn=int(v["conn"]), max_conn=200, avg_query_ms=v["avg_query_ms"], slow_queries=int(v["slow_queries"])))

def generate(gt):
    n = 30; now = datetime.utcnow().replace(microsecond=0); t0 = now - timedelta(minutes=n - 1); ramp = n if gt == "memory_leak" else 8
    with Session() as s:
        iid = f"INC-{1001 + s.query(Incident).count()}"
        s.add(Incident(id=iid, service=SVC, severity="critical", alert_type="high_error_rate", status="detected", ground_truth=gt, tried="[]", created_at=now))
        for i in range(n):
            f = min(1, max(0, (i - (n - ramp)) / ramp)); ts = t0 + timedelta(minutes=i)
            v = {k: round((BASE[k] + (TARGET[gt][k] - BASE[k]) * f) * random.uniform(.97, 1.03), 1) for k in BASE}
            _rows(s, iid, ts, v); s.add(Log(incident_id=iid, ts=ts, service=SVC, level="INFO", message="Request processed"))
            if f > .2:
                for _ in range(1 + int(f * 3)):
                    lv, m = random.choice(LOGS[gt]); s.add(Log(incident_id=iid, ts=ts, service=SVC, level=lv, message=m))
        s.add(Deployment(incident_id=iid, service=SVC, version="v1.2.0", ts=now - timedelta(hours=6)))
        s.add(Deployment(incident_id=iid, service="order-api", version="v2.1.1", ts=now - timedelta(hours=3)))
        if gt == "bad_deployment": s.add(Deployment(incident_id=iid, service=SVC, version="v1.2.1", ts=t0 + timedelta(minutes=n - 12)))
        if gt == "memory_leak":
            for m in (n - 8, n - 4): s.add(InfraEvent(incident_id=iid, ts=t0 + timedelta(minutes=m), kind="container_restart"))
        s.commit()
    return iid

def apply_action(iid, action):
    if action not in ALLOWED: raise ValueError("Action not allowed")
    with Session() as s:
        gt = s.get(Incident, iid).ground_truth
        last = s.query(SystemMetric).filter_by(incident_id=iid).order_by(SystemMetric.ts.desc()).first().ts
        T = BASE if FIX[gt] == action else TARGET[gt]
        for i in range(1, 4):
            _rows(s, iid, last + timedelta(minutes=i), {k: round(T[k] * random.uniform(.97, 1.03), 1) for k in BASE})
        s.add(Log(incident_id=iid, ts=last, service=SVC, level="INFO", message=f"Action executed: {action}")); s.commit()
    return f"{action} executed on {SVC} (simulated)"
