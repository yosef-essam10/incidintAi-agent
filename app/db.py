import os, urllib.parse
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, UnicodeText
from sqlalchemy.orm import declarative_base, sessionmaker
load_dotenv()
D = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server"); S = os.getenv("DB_SERVER", "localhost"); N = os.getenv("DB_NAME", "IncidentAI")
U, P = os.getenv("DB_USER"), os.getenv("DB_PASSWORD")
def _cs(db): return f"DRIVER={{{D}}};SERVER={S};DATABASE={db};" + (f"UID={U};PWD={P};" if U else "Trusted_Connection=yes;") + "TrustServerCertificate=yes;"
def ensure_database():
    import pyodbc
    c = pyodbc.connect(_cs("master"), autocommit=True)
    c.execute(f"IF DB_ID('{N}') IS NULL CREATE DATABASE [{N}]"); c.close()
engine = create_engine("mssql+pyodbc:///?odbc_connect=" + urllib.parse.quote_plus(_cs(N)), pool_pre_ping=True)
Session = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()
def pk(): return Column(Integer, primary_key=True, autoincrement=True)
class Incident(Base):
    __tablename__ = "incidents"
    id = Column(String(20), primary_key=True); service = Column(String(50)); severity = Column(String(20)); alert_type = Column(String(50)); status = Column(String(30))
    root_cause = Column(String(50)); confidence = Column(Float); evidence = Column(UnicodeText); reasoning = Column(UnicodeText); action = Column(String(50)); risk = Column(String(20))
    verification = Column(Text); tried = Column(Text); ground_truth = Column(String(50)); created_at = Column(DateTime)
class Log(Base):
    __tablename__ = "application_logs"; id = pk(); incident_id = Column(String(20), index=True); ts = Column(DateTime); service = Column(String(50)); level = Column(String(10)); message = Column(String(300))
class SystemMetric(Base):
    __tablename__ = "system_metrics"; id = pk(); incident_id = Column(String(20), index=True); ts = Column(DateTime); service = Column(String(50))
    cpu = Column(Float); memory = Column(Float); latency_ms = Column(Float); error_rate = Column(Float)
class DbMetric(Base):
    __tablename__ = "database_metrics"; id = pk(); incident_id = Column(String(20), index=True); ts = Column(DateTime)
    conn = Column(Integer); max_conn = Column(Integer); avg_query_ms = Column(Float); slow_queries = Column(Integer)
class Deployment(Base):
    __tablename__ = "deployments"; id = pk(); incident_id = Column(String(20), index=True); service = Column(String(50)); version = Column(String(20)); ts = Column(DateTime)
class InfraEvent(Base):
    __tablename__ = "infrastructure_events"; id = pk(); incident_id = Column(String(20), index=True); ts = Column(DateTime); kind = Column(String(50))
class Step(Base):
    __tablename__ = "investigation_steps"; id = pk(); incident_id = Column(String(20), index=True); ts = Column(DateTime); step = Column(String(100)); detail = Column(UnicodeText)
class Chat(Base):
    __tablename__ = "chat_messages"; id = pk(); incident_id = Column(String(20), index=True); role = Column(String(10)); content = Column(UnicodeText); ts = Column(DateTime)