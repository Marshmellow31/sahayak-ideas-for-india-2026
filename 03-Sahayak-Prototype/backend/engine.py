# -*- coding: utf-8 -*-
"""
Sahayak rules engine (SRS C-3): deterministic intent detection + SOP retrieval.

Interface contract (C-3): answer(worker_id, text, lang_hint, db) -> dict
A future Claude-backed engine must implement the same signature.
No external services, no API keys (C-1). Never fabricates answers (FR-N4).
"""
import json
import re
import unicodedata
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
SOPS = json.loads((DATA_DIR / "sops.json").read_text(encoding="utf-8"))

# Flattened sections for retrieval
SECTIONS = []
for _doc in SOPS["documents"]:
    for _s in _doc["sections"]:
        SECTIONS.append({**_s, "doc": _doc["doc"], "doc_id": _doc["doc_id"]})

RETRIEVAL_THRESHOLD = 3.0  # FR-K3: below this -> honest escalation

# In-memory slot-filling sessions per worker (FR-N3)
_sessions = {}

# ---------------------------------------------------------------- language

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
GUJARATI = re.compile(r"[઀-૿]")
ROMAN_HI = [
    "chhutti", "chutti", "kitni", "kitna", "chahiye", "chaahiye", "karu",
    "karun", "kya", "kaise", "mujhe", "meri", "mera", "nahi", "nahin",
    "hai", "hain", "gaya", "gayi", "kal", "aaj", "parso", "pagar",
    "tabiyat", "bimar", "shikayat", "pareshan", "batao", "bata", "kab",
]


def detect_lang(text, hint=None):
    if DEVANAGARI.search(text):
        return "hi"
    if GUJARATI.search(text):
        return "gu"
    toks = set(norm(text).split())
    if len(toks & set(ROMAN_HI)) >= 1:
        return "hi"
    return hint if hint in ("en", "hi", "gu") else "en"


def norm(text):
    text = unicodedata.normalize("NFC", text.lower())
    text = re.sub(r"[^\wऀ-ॿ઀-૿/\-]+", " ", text)
    return text.strip()

# ---------------------------------------------------------------- intents

# Grievance checked FIRST (FR-N5) — never auto-answered.
INTENT_RULES = [
    ("grievance", [
        "harass", "pareshan", "torture", "tang karta", "tang karti", "abuse",
        "gaali", "misbehav", "उत्पीड़न", "परेशान", "salary not paid", "salary nahi",
        "pagar nahi", "पगार नहीं", "unsafe", "threat", "dhamki", "complaint against",
        "shikayat karni", "शिकायत करनी", "sataave", "સતાવે", "હેરાન",
    ]),
    ("escalate", [
        "talk to hr", "human", "hr se baat", "supervisor se baat", "escalate",
        "call hr", "hr ko", "baat karni hai", "વાત કરવી",
    ]),
    ("apply_leave", [
        "apply leave", "leave chahiye", "chhutti chahiye", "chutti chahiye",
        "want leave", "need leave", "leave lena", "chhutti leni", "take leave",
        "leave for", "छुट्टी चाहिए", "छुट्टी लेनी", "रजा जोईए", "રજા જોઈએ",
        "રજા લેવી", "leave apply", "chhutti do", "leave daal",
    ]),
    ("leave_balance", [
        "leave balance", "leaves left", "leave left", "how many leave",
        "kitni chhutti", "chhutti kitni", "chutti kitni", "kitni leave",
        "leave kitni", "balance", "छुट्टी कितनी", "कितनी छुट्टी", "બાકી રજા",
        "કેટલી રજા", "રજા કેટલી", "bachi hai",
    ]),
    ("my_shifts", [
        "shift", "duty", "roster", "schedule", "duty kab", "shift kab",
        "शिफ्ट", "ड्यूटी", "શિફ્ટ", "ડ્યુટી", "kaam kab",
    ]),
    ("payslip", [
        "payslip", "salary slip", "pay slip", "salary kitni", "pagar",
        "salary aayi", "my salary", "पगार", "वेतन", "पे स्लिप", "પગાર",
        "વેતન", "salary",
    ]),
    ("attendance", [
        "attendance", "hajiri", "haziri", "present days", "absent",
        "हाजिरी", "હાજરી", "punch",
    ]),
    ("thanks", [
        "thank", "dhanyavad", "dhanyawad", "shukriya", "धन्यवाद", "शुक्रिया",
        "આભાર", "aabhar",
    ]),
    ("greeting", [
        "hello", "helo", "namaste", "namaskar", "kem cho", "good morning",
        "good evening", "नमस्ते", "नमस्कार", "કેમ છો", "હેલો", "hii",
    ]),
    ("help", [
        "help", "madad", "what can you do", "kya kar sakte", "मदद", "મદદ",
        "sahayata", "how to use",
    ]),
]

# "hi" alone is a greeting only if the whole message is a greeting word
GREETING_EXACT = {"hi", "hey", "hello", "namaste", "नमस्ते", "હાય"}


LEAVE_WORDS = ["leave", "chhutti", "chutti", "छुट्टी", "રજા", "raja"]
BALANCE_WORDS = ["left", "balance", "how many", "kitni", "kitna", "bachi",
                 "bacha", "remaining", "कितनी", "बची", "કેટલી", "બાકી"]


def detect_intent(text):
    n = norm(text)
    if n in GREETING_EXACT:
        return "greeting"
    for intent, keys in INTENT_RULES:
        if intent == "leave_balance":
            # combined rule: any leave word + any balance word (FR-N1, test T1)
            if (any(w in n for w in LEAVE_WORDS)
                    and any(w in n for w in BALANCE_WORDS)):
                return "leave_balance"
        for k in keys:
            if k in n:
                return intent
    return "sop_query"

# ---------------------------------------------------------------- retrieval (FR-K3)

STOP = set("the a an is are how what do i my to of in for me and or please "
           "kya kaise hai hain karu karun mujhe meri mera batao policy".split())


def retrieve(text):
    """Returns (section, score, coverage). Coverage = fraction of query tokens
    that hit keywords/title — guards against one generic word (e.g. 'policy')
    dragging in an unrelated section (FR-N4, test T6)."""
    toks = [t for t in norm(text).split() if t not in STOP and len(t) > 1]
    best, best_score, best_cov = None, 0.0, 0.0
    for sec in SECTIONS:
        hay_kw = " ".join(norm(k) for k in sec["keywords"])
        hay_title = norm(sec["title"])
        hay_body = norm(sec["body_en"] + " " + sec.get("body_hi", ""))
        score, strong = 0.0, 0
        for t in toks:
            if t in hay_kw:
                score += 3.0
                strong += 1
            elif t in hay_title:
                score += 2.0
                strong += 1
            elif t in hay_body:
                score += 0.5
        cov = strong / len(toks) if toks else 0.0
        if score > best_score:
            best, best_score, best_cov = sec, score, cov
    return best, best_score, best_cov

# ---------------------------------------------------------------- templates (FR-N2)

T = {
    "greeting": {
        "en": "Namaste {name} ji! 🙏 I am Sahayak, your work assistant. Ask me about leave, salary, shifts — or how to do any task. You can speak in Hindi, Gujarati or English.",
        "hi": "नमस्ते {name} जी! 🙏 मैं सहायक हूँ। छुट्टी, पगार, शिफ्ट — या कोई भी काम कैसे करना है, मुझसे पूछिए। आप हिंदी, गुजराती या English में बोल सकते हैं।",
        "gu": "નમસ્તે {name} જી! 🙏 હું સહાયક છું. રજા, પગાર, શિફ્ટ — કે કોઈ પણ કામ કેવી રીતે કરવું, મને પૂછો. તમે ગુજરાતી, હિન્દી કે English માં બોલી શકો છો.",
    },
    "help": {
        "en": "I can help you with:\n• Leave balance & applying for leave\n• Your shift schedule\n• Payslip & salary questions\n• Step-by-step help for work tasks (safety, machines, cleaning)\n• Raising a complaint — it goes straight to your supervisor",
        "hi": "मैं इनमें मदद कर सकता हूँ:\n• छुट्टी का बैलेंस और छुट्टी अप्लाई करना\n• आपकी शिफ्ट\n• पे-स्लिप और पगार के सवाल\n• काम कैसे करें — सुरक्षा, मशीन, सफाई\n• शिकायत दर्ज करना — सीधे सुपरवाइज़र तक",
        "gu": "હું આમાં મદદ કરી શકું:\n• રજાનું બેલેન્સ અને રજા અરજી\n• તમારી શિફ્ટ\n• પે-સ્લિપ અને પગારના પ્રશ્નો\n• કામ કેવી રીતે કરવું — સેફ્ટી, મશીન, સફાઈ\n• ફરિયાદ નોંધાવવી — સીધી સુપરવાઇઝર સુધી",
    },
    "thanks": {
        "en": "Happy to help, {name} ji! 🙏 Ask me anytime.",
        "hi": "खुशी हुई, {name} जी! 🙏 कभी भी पूछिए।",
        "gu": "આનંદ થયો, {name} જી! 🙏 ગમે ત્યારે પૂછો.",
    },
    "leave_balance": {
        "en": "Here is your leave balance, {name} ji:\n• Casual (CL): {casual} days\n• Sick (SL): {sick} days\n• Earned (EL): {earned} days\nSay \"apply leave\" if you want to take one.",
        "hi": "{name} जी, आपका छुट्टी बैलेंस:\n• आकस्मिक (CL): {casual} दिन\n• बीमारी (SL): {sick} दिन\n• अर्जित (EL): {earned} दिन\nछुट्टी लेनी हो तो \"छुट्टी चाहिए\" बोलिए।",
        "gu": "{name} જી, તમારું રજા બેલેન્સ:\n• આકસ્મિક (CL): {casual} દિવસ\n• માંદગી (SL): {sick} દિવસ\n• અર્જિત (EL): {earned} દિવસ\nરજા લેવી હોય તો \"રજા જોઈએ\" કહો.",
    },
    "ask_leave_type": {
        "en": "Sure. Which type of leave — sick, casual, or earned?",
        "hi": "ज़रूर। कौन सी छुट्टी — बीमारी (sick), आकस्मिक (casual), या अर्जित (earned)?",
        "gu": "જરૂર. કઈ રજા — માંદગી (sick), આકસ્મિક (casual), કે અર્જિત (earned)?",
    },
    "ask_leave_date": {
        "en": "For which day? You can say \"tomorrow\", \"day after\", or a date like 25/07.",
        "hi": "किस दिन के लिए? आप \"कल\", \"परसों\" या 25/07 जैसी तारीख बोल सकते हैं।",
        "gu": "કયા દિવસ માટે? તમે \"કાલે\", \"પરમ દિવસે\" કે 25/07 જેવી તારીખ કહી શકો.",
    },
    "leave_applied": {
        "en": "Done, {name} ji! ✅ Your {type} leave request for {date} is submitted.\nRequest ID: {rid}\nStatus: Pending supervisor approval — I will tell you as soon as it is decided.",
        "hi": "हो गया, {name} जी! ✅ {date} की {type} छुट्टी की अर्ज़ी जमा हो गई।\nरिक्वेस्ट ID: {rid}\nस्थिति: सुपरवाइज़र की मंज़ूरी बाकी — फैसला होते ही मैं आपको बता दूँगा।",
        "gu": "થઈ ગયું, {name} જી! ✅ {date} ની {type} રજાની અરજી થઈ ગઈ.\nરિક્વેસ્ટ ID: {rid}\nસ્થિતિ: સુપરવાઇઝરની મંજૂરી બાકી — નિર્ણય થતાં જ હું જણાવીશ.",
    },
    "leave_no_balance": {
        "en": "Sorry {name} ji, you have no {type} leave left. You can ask for a different type or talk to your supervisor.",
        "hi": "माफ़ कीजिए {name} जी, आपकी {type} छुट्टी बची नहीं है। दूसरी छुट्टी लें या सुपरवाइज़र से बात करें।",
        "gu": "માફ કરશો {name} જી, તમારી {type} રજા બચી નથી. બીજી રજા લો કે સુપરવાઇઝર સાથે વાત કરો.",
    },
    "my_shifts": {
        "en": "Your shifts for the next 7 days, {name} ji:\n{rows}",
        "hi": "{name} जी, अगले 7 दिन की आपकी शिफ्ट:\n{rows}",
        "gu": "{name} જી, આગામી 7 દિવસની તમારી શિફ્ટ:\n{rows}",
    },
    "payslip": {
        "en": "Your latest payslip ({month}), {name} ji:\n• Gross: ₹{gross:,}\n• Deductions (PF/ESI/PT): ₹{deductions:,}\n• Net credited: ₹{net:,}\nSalary is credited by the 7th of every month. 📄 Full payslip: HR office.",
        "hi": "{name} जी, आपकी ताज़ा पे-स्लिप ({month}):\n• ग्रॉस: ₹{gross:,}\n• कटौती (PF/ESI/PT): ₹{deductions:,}\n• खाते में आया: ₹{net:,}\nपगार हर महीने की 7 तारीख तक आता है। 📄 पूरी स्लिप: HR ऑफिस।",
        "gu": "{name} જી, તમારી તાજી પે-સ્લિપ ({month}):\n• ગ્રોસ: ₹{gross:,}\n• કપાત (PF/ESI/PT): ₹{deductions:,}\n• ખાતામાં આવ્યા: ₹{net:,}\nપગાર દર મહિનાની 7 તારીખ સુધી આવે છે. 📄 પૂરી સ્લિપ: HR ઓફિસ.",
    },
    "attendance": {
        "en": "Your attendance this month, {name} ji:\n• Present: {present} days\n• Absent: {absent} days\n• On leave: {leaves} days",
        "hi": "{name} जी, इस महीने की हाजिरी:\n• उपस्थित: {present} दिन\n• अनुपस्थित: {absent} दिन\n• छुट्टी पर: {leaves} दिन",
        "gu": "{name} જી, આ મહિનાની હાજરી:\n• હાજર: {present} દિવસ\n• ગેરહાજર: {absent} દિવસ\n• રજા પર: {leaves} દિવસ",
    },
    "grievance": {
        "en": "I am sorry you are facing this, {name} ji. 🙏 Your complaint has been sent confidentially to HR — they must respond within 48 hours. No action can ever be taken against you for raising a genuine complaint. Reference ID: {rid}",
        "hi": "{name} जी, यह सुनकर दुख हुआ। 🙏 आपकी शिकायत गोपनीय रूप से HR तक पहुंचा दी गई है — 48 घंटे में जवाब मिलेगा। सच्ची शिकायत करने पर आपके खिलाफ कभी कार्रवाई नहीं होगी। संदर्भ ID: {rid}",
        "gu": "{name} જી, આ સાંભળી દુઃખ થયું. 🙏 તમારી ફરિયાદ ગુપ્ત રીતે HR સુધી પહોંચી ગઈ છે — 48 કલાકમાં જવાબ મળશે. સાચી ફરિયાદ બદલ તમારી સામે ક્યારેય પગલાં નહીં લેવાય. સંદર્ભ ID: {rid}",
    },
    "escalate": {
        "en": "Okay {name} ji, I have sent your message to your supervisor/HR. They will get back to you. Reference ID: {rid}",
        "hi": "ठीक है {name} जी, आपका संदेश सुपरवाइज़र/HR को भेज दिया है। वे आपसे संपर्क करेंगे। संदर्भ ID: {rid}",
        "gu": "ઠીક છે {name} જી, તમારો સંદેશ સુપરવાઇઝર/HR ને મોકલી દીધો છે. તેઓ સંપર્ક કરશે. સંદર્ભ ID: {rid}",
    },
    "unknown": {
        "en": "I don't want to guess and tell you something wrong, {name} ji. 🙏 I have sent your question to your supervisor — you will get a proper answer soon. Reference ID: {rid}",
        "hi": "{name} जी, मैं अंदाज़े से गलत जवाब नहीं देना चाहता। 🙏 आपका सवाल सुपरवाइज़र को भेज दिया है — जल्द सही जवाब मिलेगा। संदर्भ ID: {rid}",
        "gu": "{name} જી, હું અંદાજથી ખોટો જવાબ આપવા માંગતો નથી. 🙏 તમારો પ્રશ્ન સુપરવાઇઝરને મોકલ્યો છે — જલદી સાચો જવાબ મળશે. સંદર્ભ ID: {rid}",
    },
    "sop_intro": {
        "en": "Here is the correct procedure, {name} ji:",
        "hi": "{name} जी, सही तरीका यह है:",
        "gu": "{name} જી, સાચી રીત આ છે:",
    },
    "approved_note": {
        "en": "✅ Good news, {name} ji! Your {type} leave for {date} (ID {rid}) has been APPROVED by your supervisor.",
        "hi": "✅ खुशखबरी, {name} जी! आपकी {date} की {type} छुट्टी (ID {rid}) सुपरवाइज़र ने मंज़ूर कर दी है।",
        "gu": "✅ સારા સમાચાર, {name} જી! તમારી {date} ની {type} રજા (ID {rid}) સુપરવાઇઝરે મંજૂર કરી છે.",
    },
    "rejected_note": {
        "en": "❌ Sorry {name} ji, your {type} leave for {date} (ID {rid}) was not approved. Please talk to your supervisor for the reason.",
        "hi": "❌ माफ़ कीजिए {name} जी, आपकी {date} की {type} छुट्टी (ID {rid}) मंज़ूर नहीं हुई। कारण के लिए सुपरवाइज़र से बात करें।",
        "gu": "❌ માફ કરશો {name} જી, તમારી {date} ની {type} રજા (ID {rid}) મંજૂર થઈ નથી. કારણ માટે સુપરવાઇઝર સાથે વાત કરો.",
    },
}

LEAVE_TYPE_WORDS = {
    "sick": ["sick", "bimar", "bimari", "tabiyat", "बीमार", "तबियत", "माँदा", "માંદગી", "medical"],
    "casual": ["casual", "personal", "आकस्मिक", "આકસ્મિક", "cl"],
    "earned": ["earned", "el", "अर्जित", "અર્જિત", "privilege"],
}

DATE_WORDS = {
    1: ["kal", "tomorrow", "कल", "કાલે", "kaal"],
    2: ["parso", "parson", "day after", "परसों", "પરમ દિવસે", "પરમદિવસે"],
    0: ["aaj", "today", "आज", "આજે"],
}


def _extract_leave_type(text):
    n = norm(text)
    for ltype, words in LEAVE_TYPE_WORDS.items():
        if any(w in n for w in words):
            return ltype
    return None


def _extract_date(text):
    n = norm(text)
    for offset, words in DATE_WORDS.items():
        if any(w in n for w in words):
            return date.today() + timedelta(days=offset)
    m = re.search(r"\b(\d{1,2})[/\-](\d{1,2})\b", n)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        try:
            cand = date(date.today().year, mo, d)
            if cand < date.today():
                cand = date(date.today().year + 1, mo, d)
            return cand
        except ValueError:
            return None
    return None


LEAVE_TYPE_LABEL = {
    "sick": {"en": "sick", "hi": "बीमारी की", "gu": "માંદગીની"},
    "casual": {"en": "casual", "hi": "आकस्मिक", "gu": "આકસ્મિક"},
    "earned": {"en": "earned", "hi": "अर्जित", "gu": "અર્જિત"},
}


def fmt_date(d):
    return d.strftime("%d %b %Y")

# ---------------------------------------------------------------- main entry


def answer(worker_id, text, lang_hint, db):
    """C-3 engine contract. db is main.Db facade (see main.py)."""
    worker = db.get_worker(worker_id)
    name = worker["name"].split()[0]
    lang = detect_lang(text, lang_hint)

    sess = _sessions.get(worker_id)
    if sess and sess.get("intent") == "apply_leave":
        intent = "apply_leave"
    else:
        intent = detect_intent(text)
        sess = None

    reply = {"intent": intent, "lang": lang, "citation": None,
             "card": None, "escalated": False, "resolved": True}

    def t(key, **kw):
        return T[key].get(lang, T[key]["en"]).format(name=name, **kw)

    if intent in ("greeting", "help", "thanks"):
        reply["text"] = t(intent)

    elif intent == "leave_balance":
        bal = db.leave_balance(worker_id)
        reply["text"] = t("leave_balance", **bal)

    elif intent == "apply_leave":
        sess = sess or {"intent": "apply_leave", "type": None, "date": None}
        sess["type"] = sess["type"] or _extract_leave_type(text)
        sess["date"] = sess["date"] or _extract_date(text)
        if not sess["type"]:
            _sessions[worker_id] = sess
            reply["text"] = t("ask_leave_type")
            reply["resolved"] = False
        elif not sess["date"]:
            _sessions[worker_id] = sess
            reply["text"] = t("ask_leave_date")
            reply["resolved"] = False
        else:
            _sessions.pop(worker_id, None)
            bal = db.leave_balance(worker_id)
            if bal[sess["type"]] <= 0:
                reply["text"] = t("leave_no_balance",
                                  type=LEAVE_TYPE_LABEL[sess["type"]][lang])
            else:
                rid = db.create_leave_request(worker_id, sess["type"],
                                              sess["date"].isoformat(), text)
                reply["text"] = t("leave_applied",
                                  type=LEAVE_TYPE_LABEL[sess["type"]][lang],
                                  date=fmt_date(sess["date"]), rid=rid)
                reply["card"] = {"kind": "leave_request", "rid": rid,
                                 "type": sess["type"],
                                 "date": fmt_date(sess["date"]),
                                 "status": "pending"}

    elif intent == "my_shifts":
        rows = db.next_shifts(worker_id, 7)
        lines = "\n".join(
            "• {d} — {rest}".format(
                d=date.fromisoformat(r["date"]).strftime("%a %d %b"),
                rest=("OFF 🌴" if r["shift_code"] == "OFF"
                      else "{c} ({s}–{e})".format(c=r["shift_code"],
                                                  s=r["start"], e=r["end"])))
            for r in rows) or "—"
        reply["text"] = t("my_shifts", rows=lines)

    elif intent == "payslip":
        p = db.latest_payslip(worker_id)
        reply["text"] = t("payslip", month=p["month"], gross=p["gross"],
                          deductions=p["deductions"], net=p["net"])

    elif intent == "attendance":
        a = db.attendance(worker_id)
        reply["text"] = t("attendance", present=a["present"],
                          absent=a["absent"], leaves=a["leaves"])

    elif intent in ("grievance", "escalate"):
        rid = db.create_escalation(worker_id, text, lang,
                                   priority=(intent == "grievance"))
        reply["text"] = t(intent, rid=rid)
        reply["escalated"] = True
        reply["resolved"] = False

    else:  # sop_query
        sec, score, cov = retrieve(text)
        if sec and score >= RETRIEVAL_THRESHOLD and cov >= 0.5:
            body = sec.get("body_hi") if lang == "hi" and sec.get("body_hi") else sec["body_en"]
            steps = re.sub(r"\s*(\d+)\.\s*", r"\n\1. ", body).strip()
            reply["text"] = t("sop_intro") + "\n" + steps
            reply["citation"] = {"doc": sec["doc"], "doc_id": sec["doc_id"],
                                 "section": sec["section_id"],
                                 "title": sec["title"]}
            reply["intent"] = "sop_query"
        else:
            rid = db.create_escalation(worker_id, text, lang, priority=False)
            reply["text"] = t("unknown", rid=rid)
            reply["intent"] = "unknown"
            reply["escalated"] = True
            reply["resolved"] = False

    return reply


def notification_text(kind, worker_name, lang, ltype, ldate, rid):
    """Approval/rejection notification pushed into the worker's chat (FR-D2)."""
    key = "approved_note" if kind == "approved" else "rejected_note"
    return T[key].get(lang, T[key]["en"]).format(
        name=worker_name.split()[0],
        type=LEAVE_TYPE_LABEL[ltype].get(lang, ltype),
        date=fmt_date(date.fromisoformat(ldate)), rid=rid)


def reset_sessions():
    _sessions.clear()
