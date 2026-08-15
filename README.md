# Sahayak - Ideas for India Hackathon Submission

Sahayak is a voice-first AI work assistant for India's deskless and frontline workers. It demonstrates multilingual worker self-service, SOP guidance with citations, leave workflows, escalations, and supervisor analytics through a local prototype.

## Submission Files

- `01-Application/` - filled application form in DOCX and PDF formats.
- `02-Deck/` - concept-to-prototype execution plan deck in PPTX and PDF formats.
- `03-Sahayak-Prototype/` - runnable FastAPI + SQLite + frontend prototype.
- `04-Screenshots/` - walkthrough screenshots and prototype walkthrough PDF.
- `05-Demo-Video/` - demo video package.

## Demo Video

Use this file for submission:

`05-Demo-Video/Sahayak-Demo-Compressed.mp4`

The original MOV export is also kept in the same folder as a backup.

## Run The Prototype

From `03-Sahayak-Prototype/backend`:

```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Open:

- Worker chat: `http://127.0.0.1:8000/`
- Supervisor dashboard: `http://127.0.0.1:8000/dashboard`

The prototype runs locally without API keys.

## Core Demo Flow

1. Ask Ramesh in Hindi: `छुट्टी कितनी बची है?`
2. File sick leave for tomorrow.
3. Approve it from the supervisor dashboard.
4. Ask SOP guidance: `Needle lag gayi, kya karu?`
5. Ask Meena in Gujarati: `મારી શિફ્ટ ક્યારે છે?`
6. Ask an unknown query, such as `What is the dividend policy?`, to show human escalation instead of guessing.

## Team

Harshil Patel, Deep Mehta, Meet Kapadia  
Indian Institute of Information Technology, Vadodara
