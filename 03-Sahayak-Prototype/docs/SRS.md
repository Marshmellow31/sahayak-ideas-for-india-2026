# Software Requirements Specification (SRS)

## Sahayak — Voice-First AI Work Assistant for Deskless Workers

| | |
|---|---|
| **Version** | 1.0 |
| **Date** | 20 July 2026 |
| **Team** | Harshil Patel, Deep Mehta, Meet Kapadia |
| **Institution** | Indian Institute of Information Technology (IIIT) Vadodara |
| **Competition** | Ideas for India: Innovation Challenge 2026 — Inclusive Innovation for Bharat (AI-Powered Enterprise Productivity) |
| **Target stage** | Functional Prototype (demo-ready, zero external API keys) |

---

## 1. Introduction

### 1.1 Purpose
This SRS defines the requirements for the **Sahayak prototype**: a voice-first, WhatsApp-style AI work assistant that lets deskless workers (hospital support staff, factory operators, field workers) ask HR questions, perform HR actions, and get step-by-step SOP guidance in their own language — plus a supervisor dashboard that turns those conversations into operational insight.

It is the single source of truth for the prototype build. The demo deck (`02-Deck/Sahayak-Concept-to-Prototype-Plan.pptx`, slide 5 storyboard) and application form Q1–Q9 answers are its parent documents; nothing in this SRS may contradict them.

### 1.2 Scope of this prototype (v1)
**In scope**
- A browser-based, WhatsApp-look chat interface (simulated channel — no Meta/Twilio account required).
- Voice input via the browser's Web Speech API (en-IN, hi-IN, gu-IN) and spoken replies via speech synthesis.
- A deterministic **rules-based NLU engine** (intent detection + keyword SOP retrieval). No LLM, no API keys, fully offline. The engine is behind an interface so a Claude-backed engine can be swapped in later without touching the UI.
- A **mock HRMS** (SQLite): employees, leave balances, leave requests, shifts, payslips, attendance.
- **HR actions**: check leave balance, apply for leave (creates a real request record), view shift schedule, payslip summary, attendance summary.
- **SOP knowledge base** (JSON) with citation-backed answers (document + section shown with every answer).
- **Escalation**: unanswered/grievance queries are logged and routed to the supervisor dashboard.
- **Supervisor dashboard**: live metrics (queries, deflection %, escalations), pending leave approvals with approve/reject, escalation queue, and a **query-cluster training-gap heatmap**.

**Out of scope for v1** (planned, stubbed where cheap)
- Real WhatsApp Business API / Twilio transport.
- Real Bhashini/Sarvam ASR-TTS.
- LLM-powered reasoning (Claude).
- Real HRMS integrations (Keka / Zoho People / greytHR).
- Authentication/SSO beyond a demo worker picker.

### 1.3 Definitions
- **Deskless worker**: employee without a company desk/laptop/email (ward boy, machine operator, delivery rider).
- **Deflection**: a query fully resolved by Sahayak without human HR/supervisor involvement.
- **SOP**: Standard Operating Procedure document.
- **First-contact resolution**: query answered correctly in the first exchange.

### 1.4 References
- Application form: `01-Application/Sahayak-IdeasForIndia-Application-FILLED.docx`
- Execution-plan deck: `02-Deck/Sahayak-Concept-to-Prototype-Plan.pptx`
- W3C Web Speech API (SpeechRecognition, SpeechSynthesis)

---

## 2. Overall Description

### 2.1 Product perspective
Sahayak v1 is a self-contained web application: a FastAPI backend serving a static frontend and a JSON API, with SQLite storage. It simulates the WhatsApp channel visually so the demo shows the exact intended user experience while remaining runnable on any laptop with Python — no accounts, keys, or internet required (voice recognition needs Chrome and internet, with graceful text-only fallback).

```
┌─────────────────────────────┐      ┌──────────────────────────────┐
│  Worker UI (chat.html)      │      │  Supervisor UI (dashboard)   │
│  WhatsApp-style chat        │      │  metrics · approvals ·       │
│  🎤 Web Speech API (browser)│      │  escalations · gap heatmap   │
└──────────┬──────────────────┘      └──────────┬───────────────────┘
           │ REST/JSON                          │ REST/JSON (poll)
┌──────────▼────────────────────────────────────▼───────────────────┐
│                    FastAPI backend (main.py)                       │
│  ┌──────────────┐  ┌───────────────┐  ┌────────────────────────┐  │
│  │ Rules engine  │  │ SOP retriever │  │ Mock HRMS (SQLite)     │  │
│  │ intent + lang │  │ keyword+score │  │ employees·leave·shifts │  │
│  │ (engine.py)   │  │ + citations   │  │ payslips·attendance    │  │
│  └──────────────┘  └───────────────┘  └────────────────────────┘  │
│            every exchange logged → metrics & heatmap               │
└────────────────────────────────────────────────────────────────────┘
```

### 2.2 User classes
| User | Description | Interface |
|---|---|---|
| **Worker** | Deskless employee; may have low literacy; prefers voice and Hindi/Gujarati | Chat UI (`/`) |
| **Supervisor / HR** | Approves leave, handles escalations, monitors training gaps | Dashboard (`/dashboard`) |
| **Demo presenter** | Team member driving the hackathon demo | Both, plus worker-picker |

### 2.3 Operating environment
- Backend: Python 3.10+, FastAPI + Uvicorn, SQLite (stdlib `sqlite3`). No other services.
- Frontend: static HTML/CSS/JS (no build step). Chrome/Edge recommended (Web Speech API).
- Runs on `http://localhost:8000`. Single command start: `python -m uvicorn main:app` (wrapped in `run.bat` / README).

### 2.4 Design constraints
- **C-1 Zero external dependencies at demo time**: no API keys, no cloud calls except the browser's own speech service.
- **C-2 Deterministic demo**: identical inputs → identical outputs (rules engine, seeded data).
- **C-3 Swappable brain**: `engine.py` exposes `answer(worker_id, text, lang) -> Reply`; an LLM implementation must be able to replace the rules implementation behind the same signature.
- **C-4 Every knowledge answer must carry a citation** (SOP doc + section) — mirrors the ≥90% citation-accuracy metric in the application (Q6).
- **C-5 UI must read as WhatsApp** (green header, bubble layout, ticks) so judges instantly grasp the channel story, with a visible "Simulated channel — WhatsApp Business API in production" label for honesty.

---

## 3. Functional Requirements

### 3.1 Worker chat (FR-C)
- **FR-C1** The chat UI shall render a WhatsApp-style conversation: worker bubbles right (green), Sahayak bubbles left (white), timestamps, day header, contact header "Sahayak — Work Assistant".
- **FR-C2** A worker picker (demo login) shall let the presenter switch between at least 3 seeded workers (e.g., hospital housekeeping, factory operator, lab technician) without restarting.
- **FR-C3** Text input shall support English, Hindi (Devanagari **and** romanized, e.g., "chhutti kitni bachi hai"), and Gujarati.
- **FR-C4** A 🎤 button shall capture speech via `SpeechRecognition` with a language selector (English en-IN / हिन्दी hi-IN / ગુજરાતી gu-IN); interim transcript shown live; final transcript sent as a normal message. If the API is unavailable, the button shows a tooltip and the UI degrades to text-only.
- **FR-C5** Sahayak replies shall optionally be spoken aloud via `speechSynthesis` in the reply's language (toggleable, default on).
- **FR-C6** Quick-reply chips (e.g., "Leave balance", "Apply leave", "My shifts", "Payslip", "How do I...?") shall be shown for discoverability.
- **FR-C7** Replies that used the SOP knowledge base shall display a citation card: 📄 document name + section number/title.
- **FR-C8** Action confirmations (e.g., leave applied) shall render as a structured card with a request ID and status "Pending supervisor approval".

### 3.2 Rules engine — NLU (FR-N)
- **FR-N1** The engine shall classify each message into one of these intents via keyword/pattern rules (multilingual keyword sets per intent): `greeting`, `help`, `leave_balance`, `apply_leave`, `my_shifts`, `payslip`, `attendance`, `sop_query`, `grievance`, `escalate`, `thanks`, `unknown`.
- **FR-N2** Language detection: Devanagari script → hi; Gujarati script → gu; else romanized-Hindi keyword hit → hi; else en. Replies use the detected language's template (templates exist in en/hi/gu for all HR intents; SOP content is bilingual en/hi where seeded).
- **FR-N3** `apply_leave` shall run a slot-filling mini-dialog: extract leave type (casual/sick/earned) and dates from the message where possible ("kal" = tomorrow, "parso" = day after, explicit dd/mm); ask one follow-up question per missing slot; confirm before writing.
- **FR-N4** `sop_query` shall fall through to the SOP retriever (FR-K). If the top score is below threshold, the engine returns an honest "I don't know yet — I've sent this to your supervisor" and files an escalation (FR-E1). **The engine shall never fabricate an answer.**
- **FR-N5** `grievance` (harassment, safety, salary-dispute keywords) shall always escalate immediately with an empathetic acknowledgment, never attempt an automated answer, and be flagged `priority` in the dashboard.
- **FR-N6** Every exchange shall be logged: worker, timestamp, detected language, intent, resolved/escalated, latency, matched SOP (if any).

### 3.3 SOP knowledge base & retrieval (FR-K)
- **FR-K1** Knowledge shall live in `backend/data/sops.json`: ≥ 6 documents, ≥ 25 sections total, spanning the two pilot verticals — hospital (housekeeping/infection control, needle-stick protocol, biomedical waste, patient-transfer) and manufacturing (machine start-up/lockout-tagout, PPE, fire/emergency), plus HR policy (leave rules, payslip queries, PF basics).
- **FR-K2** Each section shall carry: `doc`, `section_id`, `title`, `body_en`, `body_hi` (where seeded), `keywords` (multilingual list including romanized forms).
- **FR-K3** Retrieval: normalized keyword/token overlap scoring across title+keywords+body; top-1 returned with score; threshold below which FR-N4 escalation fires.
- **FR-K4** SOP answers shall be formatted as numbered steps where the source is procedural, and always end with the citation (FR-C7).

### 3.4 Mock HRMS & actions (FR-H)
- **FR-H1** SQLite schema: `employees(id, name, role, site, lang_pref)`, `leave_balances(emp_id, casual, sick, earned)`, `leave_requests(id, emp_id, type, from_date, to_date, reason, status, created_at)`, `shifts(emp_id, date, shift_code, start, end)`, `payslips(emp_id, month, gross, deductions, net)`, `attendance(emp_id, month, present, absent, leaves)`. Seeded deterministically for 3+ workers with 14 days of shifts and 3 months of payslips.
- **FR-H2** `leave_balance` shall read live from `leave_balances` and reflect any approved requests.
- **FR-H3** `apply_leave` shall insert a `leave_requests` row with status `pending` and return the request ID; balances are decremented only on supervisor approval.
- **FR-H4** `my_shifts` returns the next 7 days; `payslip` returns the latest month's net/gross/deductions summary (never full breakup in chat — privacy); `attendance` returns current-month counts.

### 3.5 Escalation & supervisor dashboard (FR-D)
- **FR-E1** Escalations (`unknown` low-score, explicit `escalate`, `grievance`) are stored with the original message, worker, language, and priority flag.
- **FR-D1** The dashboard shall show live tiles: total queries today, first-contact resolution %, deflection %, escalations open, active workers — auto-refreshing (poll ≤ 5 s).
- **FR-D2** A **pending leave approvals** table with one-click Approve / Reject; approval decrements the worker's balance and, on the worker's next chat poll, Sahayak proactively notifies them of the decision.
- **FR-D3** An **escalation queue** (priority items first) with a "mark resolved" action.
- **FR-D4** A **training-gap heatmap**: intent/topic × count grid colored by volume, computed from the query log — the "query clusters become a training-gap heatmap" claim from deck slide 10 made visible.
- **FR-D5** A language-mix breakdown (en/hi/gu query counts) to evidence the inclusion story.

### 3.6 Demo support (FR-X)
- **FR-X1** A "Demo script" note in the README mapping deck slide 5's four storyboard beats to exact utterances that exercise them (voice leave query in Hindi → SOP lookup with citation → leave application → dashboard approval + heatmap).
- **FR-X2** `POST /api/reset` restores the seeded database state between demo runs.

---

## 4. External Interface Requirements

### 4.1 REST API (JSON)
| Method & path | Purpose |
|---|---|
| `GET /` | Worker chat UI |
| `GET /dashboard` | Supervisor dashboard |
| `GET /api/workers` | Seeded workers for the picker |
| `POST /api/chat` | `{worker_id, text, lang_hint}` → `{reply, lang, intent, citation?, card?, escalated}` |
| `GET /api/chat/history?worker_id=` | Conversation history + any pending notifications (approval results) |
| `GET /api/dashboard/summary` | Tiles + language mix + heatmap data |
| `GET /api/dashboard/approvals` · `POST /api/approvals/{id}` (`approve`/`reject`) | Leave workflow |
| `GET /api/dashboard/escalations` · `POST /api/escalations/{id}/resolve` | Escalation queue |
| `POST /api/reset` | Reseed demo data |

### 4.2 UI requirements
- Chat page ≈ WhatsApp Web: dark-green header `#075E54`, chat wallpaper, bubble green `#DCF8C6`; mobile-width column centered on desktop. Simulation disclaimer visible (C-5).
- Dashboard: clean light admin theme consistent with the deck palette (teal `#0B5E63`, saffron accent `#F4A226`); cards + tables; no login (demo).
- Both pages responsive down to 375 px width.

---

## 5. Non-Functional Requirements
- **NFR-1 Latency**: chat reply < 300 ms locally (rules engine is in-process).
- **NFR-2 Reliability**: backend restart-safe; SQLite file persists; `/api/reset` recovers any demo state.
- **NFR-3 Portability**: Windows/macOS/Linux; only `pip install fastapi uvicorn`.
- **NFR-4 Privacy**: payslip details summarized, never full data in chat; no real personal data anywhere (all seeded data fictional); logs stay local.
- **NFR-5 Honesty/safety**: no fabricated answers (FR-N4); grievances always reach a human (FR-N5); every knowledge answer cites its source (C-4).
- **NFR-6 Extensibility**: engine interface (C-3), transport adapter seam for Twilio, ASR seam for Bhashini/Sarvam — each documented as a stub in code comments.
- **NFR-7 Accessibility**: voice-first interaction, large touch targets, minimal text entry required for every core flow.

---

## 6. Acceptance Test Cases

| # | Scenario | Expected |
|---|---|---|
| T1 | Worker asks "How many casual leaves do I have left?" | Balance from DB, in English |
| T2 | "छुट्टी कितनी बची है?" (voice or text) | Same balance, reply in Hindi |
| T3 | "kal ki chhutti chahiye, tabiyat kharab hai" | Slot-filled sick-leave request for tomorrow, confirmation card with request ID, appears in dashboard approvals |
| T4 | Supervisor approves T3's request | Balance decremented; worker's chat shows approval notification on next message/poll |
| T5 | "Needle stick ho gaya, kya karu?" | Numbered needle-stick protocol steps + citation card (doc + section), marked resolved |
| T6 | "What is the company's dividend policy?" (out of KB) | Honest "don't know" + escalation created; visible in dashboard queue |
| T7 | Grievance phrasing ("supervisor mujhe pareshan karta hai") | Empathetic reply, priority escalation, no automated advice |
| T8 | "મારી શિફ્ટ ક્યારે છે?" (Gujarati) | Next-7-day shifts in Gujarati template |
| T9 | Dashboard after T1–T8 | Tiles, language mix, and heatmap all reflect the traffic; deflection math correct |
| T10 | `POST /api/reset` | All state back to seed; history cleared |

---

## 7. Traceability to competition claims
| Application/deck claim | Prototype evidence |
|---|---|
| Voice-first, Indic languages (Q2, slide 3) | FR-C4/C5, FR-N2, T2/T8 |
| Answers + Actions + Insight triad (slide 3) | FR-K, FR-H, FR-D |
| ≥90% citation accuracy metric (Q6) | C-4, FR-C7, FR-K4 |
| 30–40% HR-query deflection (Q6, slide 8) | Deflection tile FR-D1, T9 |
| Training-gap heatmap wedge (slide 10) | FR-D4 |
| Guardrails: no fabrication, human escalation (slide 9) | FR-N4/N5, NFR-5 |
| Proof-of-concept stage, honestly labeled (Q4) | C-5 disclaimer, stubs documented (NFR-6) |

---

## 8. Future work (post-hackathon backlog)
1. Twilio WhatsApp sandbox transport adapter (webhook ↔ same `/api/chat` contract).
2. Claude-backed engine implementation behind C-3 interface (intent + RAG generation with citations).
3. Bhashini/Sarvam ASR-TTS replacing browser speech.
4. pgvector embedding retrieval replacing keyword scoring.
5. Keka/Zoho People/greytHR connector replacing mock HRMS.
6. Worker authentication via phone-number identity (WhatsApp-native).
