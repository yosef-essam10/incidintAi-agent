# IncidentAI

**AI-Powered Incident Investigation and Resolution**

IncidentAI is an AI-assisted incident-management system designed to help IT, SRE, and DevOps engineers investigate incidents, identify likely root causes, recommend remediation actions, and verify whether those actions resolved the issue.

Rather than acting as a chatbot that only explains an alert, IncidentAI coordinates an end-to-end, stateful workflow. It combines structured evidence, deterministic scoring rules, retrieval from operational knowledge, LLM-generated explanations, human approval, and post-action verification.

## Table of Contents

- [Overview](#overview)
- [Problem Statement](#problem-statement)
- [Core Capabilities](#core-capabilities)
- [Architecture](#architecture)
- [End-to-End Workflow](#end-to-end-workflow)
- [Root Cause Analysis](#root-cause-analysis)
- [RAG and Knowledge Retrieval](#rag-and-knowledge-retrieval)
- [Human-in-the-Loop Remediation](#human-in-the-loop-remediation)
- [Verification and Escalation](#verification-and-escalation)
- [Incident Chat](#incident-chat)
- [Technology Stack](#technology-stack)
- [Design Principles](#design-principles)
- [Example Investigation](#example-investigation)
- [Project Scope](#project-scope)

## Overview

When an incident occurs, engineers often need to correlate information from multiple systems before they can explain what happened and decide how to recover. IncidentAI organizes this investigation into a repeatable workflow.

The system uses an incident simulator to generate representative failure scenarios. Incident records and associated operational data—such as logs, metrics, and deployment history—are stored in SQL Server. A FastAPI backend connects the application interface to the database and the LangGraph agent. The agent collects evidence, evaluates possible causes, retrieves relevant operational guidance, and proposes a remediation action.

Potentially disruptive actions are not executed automatically. The workflow pauses for an engineer's approval, then executes an approved action and checks whether the relevant metrics improved. If verification fails, the workflow can investigate again or escalate the incident.

## Problem Statement

Incident investigation can require engineers to manually correlate several sources of operational evidence:

- Application logs
- System and infrastructure metrics
- Database metrics
- Deployment history
- Infrastructure events
- Previously resolved incidents and operational runbooks

This process can be time-consuming and inconsistent, especially when several possible causes produce similar symptoms.

IncidentAI aims to make the process more structured by collecting evidence in one workflow, ranking likely causes, explaining recommendations, preserving human control over remediation, and checking the result instead of assuming that an action worked.

## Core Capabilities

- **Incident simulation:** Generate representative scenarios, including database connection exhaustion, bad deployments, memory leaks, and slow queries.
- **Evidence collection:** Retrieve incident-related logs, metrics, database information, and deployment records from SQL Server.
- **Evidence-based root cause analysis:** Apply deterministic rules and scoring to rank possible explanations based on the available evidence.
- **LLM-assisted explanations:** Use an LLM through Groq's OpenAI-compatible API to explain findings in natural language and answer questions about the incident.
- **Knowledge retrieval:** Search incident runbooks and previously resolved incidents using TF-IDF and cosine similarity.
- **Human approval:** Pause before remediation and wait for an engineer to approve or reject the proposed action.
- **Action execution:** Execute the approved remediation through the application's action-handling logic.
- **Post-action verification:** Compare relevant metrics before and after execution to assess whether the incident has improved.
- **Re-investigation and escalation:** Return to investigation when verification fails, or escalate when no safe action remains.
- **Incident chat:** Answer questions using the incident evidence and retrieved knowledge rather than relying only on general model knowledge.

## Architecture

The application is organized around the following logical components:

```text
Incident Simulator
       |
       v
SQL Server
(Incidents, Logs, Metrics, Deployments)
       |
       v
FastAPI Backend
       |
       +------------------------------+
       |                              |
       v                              v
LangGraph Agent                 Incident Chat
       |                              |
       |                              v
       |                     Incident Context + RAG
       |
       v
Evidence Collection
       |
       v
Root Cause Scoring
       |
       +------> Runbook / Resolved-Incident Retrieval
       |                     (TF-IDF + Cosine Similarity)
       v
Recommendation and Explanation
       |
       v
Human Approval (LangGraph Interrupt)
       |
       +------ Reject ------> Re-investigation
       |
       +------ Approve -----> Remediation Execution
                                      |
                                      v
                              Metric Verification
                                      |
                        +-------------+-------------+
                        |                           |
                    Improved                    Not improved
                        |                           |
                        v                           v
                    Resolved              Re-investigate or
                                           Escalate to Engineer
```

This diagram describes the logical flow. Exact API routes, database table names, and deployment instructions depend on the implementation and are not assumed here.

### Component Responsibilities

| Component | Responsibility |
|---|---|
| Incident Simulator | Produces test incidents and representative failure conditions. |
| SQL Server | Stores incidents and related operational evidence. |
| FastAPI | Exposes backend functionality and connects the interface, database, and agent. |
| SQLAlchemy | Provides database access from Python. |
| LangGraph | Coordinates the investigation as a stateful workflow and controls transitions between stages. |
| Deterministic analysis rules | Evaluate available signals and score candidate root causes. |
| Groq-hosted LLM | Produces readable explanations and supports incident-related questions. |
| RAG module | Retrieves relevant runbooks and historical incidents using TF-IDF and cosine similarity. |
| Approval step | Requires an engineer's decision before a remediation action is executed. |
| Verification step | Checks relevant metrics after an action and determines the next workflow state. |
| Frontend | Presents incident information, recommendations, approval choices, and the chat interface. |

## End-to-End Workflow

The primary LangGraph workflow follows these stages:

`Triage → Investigation → Root Cause Analysis → Recommendation → Human Approval → Execution → Verification`

The workflow is stateful: each stage uses information collected earlier, and the outcome of a stage determines what happens next.

### 1. Triage

The workflow starts with an incident to investigate. It identifies the incident context and prepares the investigation state so the subsequent stages can work with the same incident.

### 2. Investigation

The agent collects relevant evidence from SQL Server, including the available application logs, system metrics, database metrics, deployment history, and infrastructure events.

The goal is to build a timeline and identify signals that distinguish one possible failure from another. For example, a spike in database connections may be more relevant to a connection-exhaustion incident than an unrelated deployment event.

### 3. Root Cause Analysis

The system evaluates candidate causes using deterministic rules and evidence-based scoring. The result is a ranked or prioritized explanation based on the signals available to the workflow.

The LLM can help express the result in understandable language, but critical decisions are not delegated to free-form LLM reasoning alone. This separation makes the investigation more controlled and easier to explain.

### 4. Recommendation

The system selects or proposes a remediation action based on the investigation results and relevant knowledge retrieved from runbooks or previously resolved incidents.

A recommendation should include the suspected cause, supporting evidence, proposed action, and relevant risk information where available. For example:

```text
Likely Root Cause: Database connection exhaustion
Supporting Evidence: Elevated database connections and connection-related errors
Recommended Action: restart_service
Risk: Medium
```

This is an illustrative example, not a claim that these exact values are generated for every incident.

### 5. Human Approval

Before a remediation action is executed, the LangGraph workflow pauses using an interrupt. The engineer reviews the proposed action and chooses whether to approve or reject it.

- **Approve:** Continue to execution.
- **Reject:** Return to investigation or recommendation so the system can reassess the available evidence and options.

This checkpoint prevents the agent from autonomously performing potentially disruptive remediation without human authorization.

### 6. Execution

If the engineer approves the action, the workflow passes it to the application's remediation execution logic. The action handler performs the approved operation and records or returns the outcome needed by the workflow.

The specific operations available depend on which remediation handlers are implemented and configured.

### 7. Verification

After execution, the system evaluates whether the incident improved. It compares relevant metrics from before and after the action, such as:

- Error rate
- Request latency
- Database connection usage

The verification step is important because an action completing successfully does not necessarily mean the incident itself has been resolved.

### 8. Re-investigation or Escalation

If the metrics improve sufficiently according to the application's verification criteria, the incident can be marked as resolved.

If they do not improve, the workflow returns to investigation to reassess the evidence and consider another appropriate action. If no safe or suitable action remains, the workflow escalates the incident to an engineer rather than repeatedly trying actions without a clear basis.

## Root Cause Analysis

IncidentAI combines deterministic analysis with LLM-assisted interpretation.

### Deterministic Evidence Evaluation

Rules and scoring evaluate evidence associated with candidate causes. This approach is intended to keep the core assessment grounded in observable signals rather than asking an LLM to invent a diagnosis.

Examples of signals that may support an investigation include:

- Database connection counts and connection errors
- Application error patterns
- Changes in latency
- Memory usage trends
- Recent deployment activity
- Infrastructure events correlated with the incident timeline

The exact scoring formula and thresholds are implementation-specific. A score should be understood as a measure of support from the available evidence, not as a guarantee that a root cause is correct.

### LLM-Assisted Interpretation

The LLM, accessed through Groq's OpenAI-compatible API, is used to:

- Explain the likely root cause in natural language
- Summarize the evidence behind a finding
- Make recommendations easier for engineers to understand
- Answer questions about the incident context

The LLM complements the evidence-based analysis; it does not replace deterministic checks or the human approval requirement.

## RAG and Knowledge Retrieval

IncidentAI includes a lightweight Retrieval-Augmented Generation (RAG) component based on:

- **TF-IDF** for representing text and emphasizing informative terms
- **Cosine similarity** for comparing a query with available knowledge documents

The knowledge collection includes:

- Incident runbooks
- Previously resolved incidents

When the system needs guidance for a current incident, it searches for relevant documents and uses the retrieved results as supporting context for recommendations or explanations.

For example, an incident involving slow database queries may retrieve a runbook describing how to inspect query latency or a previous incident with similar symptoms. Retrieval provides relevant context; it does not, by itself, prove that the historical cause applies to the current incident.

## Human-in-the-Loop Remediation

Human approval is a control point in the workflow, not an optional chat suggestion.

A typical approval sequence is:

1. The agent completes its investigation.
2. It proposes a remediation action and presents the supporting evidence.
3. LangGraph interrupts the workflow and waits for the engineer's decision.
4. If approved, execution continues.
5. If rejected, the workflow returns to investigation or recommendation.

This design helps keep operational responsibility with the engineer, especially for actions that could affect service availability.

## Verification and Escalation

IncidentAI treats remediation as a hypothesis that must be checked.

The verification stage compares selected metrics before and after execution. The result determines the next transition:

| Verification outcome | Workflow response |
|---|---|
| Relevant metrics improve according to the configured criteria | Mark the incident as resolved. |
| Metrics do not improve | Return to investigation and reassess the evidence. |
| No safe or suitable remediation remains | Escalate to an engineer. |

The comparison criteria and thresholds should be configured for the relevant service and metric. A single metric may not be sufficient to confirm recovery, so verification should use the signals that best reflect the incident being investigated.

## Incident Chat

The frontend includes an incident-focused chat interface. It uses the current incident context and retrieved knowledge to help engineers understand the investigation.

Example questions include:

- "Why was this identified as the root cause?"
- "What evidence was used?"
- "Was the incident actually resolved?"
- "Which metrics changed after the remediation?"
- "What runbook or previous incident supports this recommendation?"

The chat is intended to explain the workflow's findings and evidence. It should distinguish confirmed observations from likely explanations and should not claim that an action succeeded unless the execution and verification results support that conclusion.

## Technology Stack

| Technology | Role |
|---|---|
| Python | Core application and analysis logic |
| FastAPI | Backend API |
| LangGraph | Stateful agent workflow, transitions, and approval interrupt |
| SQL Server | Persistent storage for incident data and operational evidence |
| SQLAlchemy | Python database access |
| Groq | LLM access through an OpenAI-compatible API |
| LLM | Natural-language explanations and incident chat |
| TF-IDF | Text representation for knowledge retrieval |
| Cosine Similarity | Ranking relevant runbooks and historical incidents |
| Scikit-learn | Machine-learning utilities, including text retrieval components |
| HTML, CSS, JavaScript | Frontend and user interaction |

## Design Principles

- **Evidence before explanation:** Findings should be grounded in collected operational data.
- **Deterministic control for critical decisions:** Rules and scoring support the core analysis instead of relying exclusively on an LLM.
- **Human authorization:** Remediation pauses for engineer approval before execution.
- **Verification over assumption:** Successful execution is not treated as proof of incident resolution.
- **Knowledge reuse:** Runbooks and historical incidents help inform recommendations.
- **Traceable workflow:** Investigation, approval, execution, and verification are distinct stages with explicit transitions.
- **Safe fallback:** When the system cannot identify a suitable next action, it should escalate rather than continue blindly.

## Example Investigation

Consider a simulated incident caused by database connection exhaustion.

1. The simulator creates the incident and its related operational records.
2. The records are stored in SQL Server.
3. The FastAPI backend starts or exposes the incident investigation.
4. LangGraph coordinates the triage and evidence-collection stages.
5. The agent retrieves connection metrics, application errors, and other relevant evidence.
6. Deterministic scoring evaluates whether connection exhaustion is a plausible root cause.
7. The RAG component searches runbooks and previously resolved incidents for relevant guidance.
8. The system presents the likely cause, evidence, and a proposed remediation action.
9. LangGraph pauses for engineer approval.
10. If approved, the remediation handler executes the action.
11. The workflow compares relevant metrics before and after execution.
12. If the configured verification criteria are met, the incident is marked as resolved. Otherwise, the workflow investigates again or escalates.

This example illustrates the intended workflow. Actual results depend on the evidence in the database, the implemented rules, available remediation handlers, and verification thresholds.

## Project Scope

IncidentAI demonstrates how an AI agent can coordinate a structured operational workflow rather than simply generate text. Its central idea is the combination of:

`State → Tools → Evidence → Analysis → RAG → Human Approval → Action → Verification`

The system is designed as an incident-investigation and decision-support workflow. Its reliability depends on the quality of the collected evidence, the scoring rules, the retrieved knowledge, the safety of configured remediation handlers, and the verification criteria.

For production use, remediation handlers should be explicitly allow-listed, protected by appropriate permissions, audited, and tested in a safe environment. Secrets should be supplied through environment variables or a secrets manager rather than committed to source control. Approval and verification policies should be tailored to the operational risk of each action.
