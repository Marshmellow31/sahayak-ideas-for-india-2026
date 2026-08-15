# Sahayak — Prototype

Voice-first AI work assistant for deskless workers (WhatsApp-style, simulated channel).
Built for **Ideas for India: Innovation Challenge 2026** by Harshil Patel, Deep Mehta, Meet Kapadia (IIIT Vadodara).

Full requirements: [docs/SRS.md](docs/SRS.md).

## Run

```
pip install -r requirements.txt
run.bat            (or: cd backend && python -m uvicorn main:app --port 8000)
```

- Worker chat: **http://localhost:8000/** (use Chrome/Edge for the 🎤 voice input)
- Supervisor dashboard: **http://localhost:8000/dashboard**

No API keys, no internet needed (voice recognition uses the browser's own speech service).

## Demo script (maps to deck slide 5 storyboard)

Reset first with the **Reset demo** button on the dashboard.

1. **Voice HR query (Hindi):** pick worker *Ramesh*, tap 🎤 with language हिं and say
   "छुट्टी कितनी बची है?" → live balance from the mock HRMS, spoken back in Hindi.
2. **SOP guidance with citation:** type or say "Needle lag gayi, kya karu?" →
   numbered needle-stick protocol + 📄 citation card (doc + section). Try
   "Machine start kaise karu?" as worker *Suresh* for the factory side.
3. **Agentic HR action:** "मुझे कल की छुट्टी चाहिए, तबियत खराब है" → Sahayak slot-fills
   sick leave for tomorrow and files a real request (ID card, status pending).
4. **Supervisor loop:** open /dashboard → tiles update, the request sits in
   *Leave approvals* → **Approve** → back in the chat, Ramesh gets the approval
   message within ~4 s and his balance is decremented.
5. **Honesty + insight:** ask "What is the dividend policy?" → honest "I don't
   know", escalation appears in the queue; ask a grievance ("supervisor mujhe
   pareshan karta hai") → priority escalation, no automated advice. The
   **training-gap heatmap** and **language mix** now tell the insight story.

Gujarati works too: worker *Meena*, "મારી શિફ્ટ ક્યારે છે?"

## Architecture (see SRS §2.1)

- `backend/main.py` — FastAPI: chat API, mock HRMS (SQLite, seeded), approvals,
  escalations, metrics. `POST /api/reset` reseeds.
- `backend/engine.py` — deterministic rules engine: language detection
  (Devanagari/Gujarati/romanized-Hindi), 12 intents, slot-filling leave dialog,
  keyword SOP retrieval with citations, honest-escalation fallback.
  Swappable for a Claude-backed engine behind the same `answer()` contract.
- `backend/data/sops.json` — 6 SOP documents, 25 sections, bilingual bodies.
- `frontend/index.html` — WhatsApp-style chat, Web Speech API voice in/out.
- `frontend/dashboard.html` — supervisor tiles, approvals, escalations, heatmap.

Production-path stubs (not in v1): WhatsApp Business API/Twilio transport,
Bhashini/Sarvam ASR-TTS, Claude LLM engine, Keka/Zoho People/greytHR connectors.
