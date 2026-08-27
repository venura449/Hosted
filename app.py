import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import request

ROOT = Path(__file__).parent
DB_PATH = ROOT / "wellbeing.db"
ACTIVITIES_PATH = ROOT / "activities.json"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemma-4-31b-it")
GEMINI_TIMEOUT_SECONDS = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "8"))
CRISIS_PATTERN = re.compile(
    r"(suicid|kill myself|end my life|hurt myself|harm myself|self[- ]harm|hopeless|මැරෙන්න|දිවි නසා|තමන්ට හානි|බලාපොරොත්තු නැහැ|අසරණ)",
    re.IGNORECASE,
)

SYSTEM_INSTRUCTION = (
    "You are a mental health support assistant. Communicate fluently in both English and Sinhala. "
    "Detect the language used by the user and respond in the same language. Always be non-judgmental, "
    "empathetic, and supportive. Use active listening techniques. Validate the user's feelings before "
    "offering advice. Do not diagnose, and keep suggestions practical and gentle."
)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def init_db():
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS emotional_trends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                emotion TEXT NOT NULL,
                intensity INTEGER NOT NULL,
                keywords TEXT NOT NULL
            )"""
        )


def load_activities():
    return json.loads(ACTIVITIES_PATH.read_text(encoding="utf-8"))


def detect_crisis(text):
    return bool(CRISIS_PATTERN.search(text))


def fallback_reply(language, message):
    lowered = message.lower().strip()
    if language == "si" and any(greeting in message for greeting in ("හායි", "ආයුබෝවන්", "හෙලෝ")):
        return "ආයුබෝවන්. ඔබට අද කොහොමද දැනෙන්නේ?"
    if language == "en" and any(greeting in lowered.split() for greeting in ("hello", "hi", "hey")):
        return "Hello. I am here with you. How are you feeling today?"
    if language == "si":
        return "ඔබට මෙය දැනෙන එක ගැන කණගාටුයි. ඔබ තනිවම මෙය දරාගත යුතු නැහැ. මේ මොහොතේ ඔබ විශ්වාස කරන කෙනෙකුට කතා කර, සෙමින් හුස්ම තුනක් ගන්න."
    return "I am sorry this feels heavy right now. You do not have to carry it alone. Consider reaching out to someone you trust, and take three slow breaths with me."


def detect_language(text):
    return "si" if re.search(r"[\u0D80-\u0DFF]", text) else "en"


def analyze_locally(text):
    language = detect_language(text)
    lowered = text.lower()
    negative_words = ["stressed", "anxious", "overwhelmed", "sad", "tired", "lonely", "stress", "බය", "ආතතිය", "දුක", "තෙහෙට්ටු"]
    matched = [word for word in negative_words if word in lowered or word in text]
    intensity = min(10, 3 + len(matched) * 2 + (4 if detect_crisis(text) else 0))
    emotion = "negative" if matched or detect_crisis(text) else "neutral"
    return {"emotion": emotion, "intensity": intensity, "keywords": matched[:5], "language": language}


def choose_activity(message, analysis):
    if not any(word in message.lower() for word in ("lonely", "loneliness", "bored", "boredom")):
        return None
    activities = load_activities()
    target = "anxiety" if analysis["intensity"] >= 6 else "reflection"
    for activity in activities:
        if target in activity["tags"]:
            return activity
    return activities[0]


def call_gemini(messages):
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={api_key}"
    payload = {"system_instruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]}, "contents": messages, "generationConfig": {"temperature": 0.25, "responseMimeType": "text/plain"}}
    data = json.dumps(payload).encode("utf-8")
    try:
        req = request.Request(endpoint, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with request.urlopen(req, timeout=GEMINI_TIMEOUT_SECONDS) as response:
            result = json.loads(response.read().decode("utf-8"))
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return None


def stream_gemini(messages):
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:streamGenerateContent?alt=sse&key={api_key}"
    payload = {"system_instruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]}, "contents": messages, "generationConfig": {"temperature": 0.25, "responseMimeType": "text/plain"}}
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(endpoint, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with request.urlopen(req, timeout=GEMINI_TIMEOUT_SECONDS) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            event = line[5:].strip()
            if event == "[DONE]":
                break
            try:
                result = json.loads(event)
            except json.JSONDecodeError:
                continue
            for candidate in result.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    text = part.get("text")
                    if text:
                        yield text


def save_trend(user_id, analysis):
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            "INSERT INTO emotional_trends (user_id, created_at, emotion, intensity, keywords) VALUES (?, ?, ?, ?, ?)",
            (user_id, utc_now(), analysis["emotion"], analysis["intensity"], json.dumps(analysis["keywords"], ensure_ascii=False)),
        )


def long_term_distress(user_id):
    since = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    with sqlite3.connect(DB_PATH) as connection:
        rows = connection.execute("SELECT intensity FROM emotional_trends WHERE user_id = ? AND created_at >= ? ORDER BY created_at DESC LIMIT 3", (user_id, since)).fetchall()
    return len(rows) == 3 and all(row[0] >= 9 for row in rows)


def response_for(payload):
    user_id = str(payload.get("user_id") or "local-user")
    message = str(payload.get("message") or "").strip()
    history = payload.get("history") or []
    if not message:
        raise ValueError("message is required")
    analysis = analyze_locally(message)
    save_trend(user_id, analysis)
    if detect_crisis(message) or long_term_distress(user_id):
        return {"reply": "It sounds like you are going through a very difficult time. Please contact a mental health professional or emergency service now. In Sri Lanka, call 1926 (National Mental Health Helpline) or 1333 (CCCline). If you may act soon, go to the nearest hospital or ask someone you trust to stay with you.", "crisis": True, "analysis": analysis}
    gemini_messages = [{"role": item.get("role", "user"), "parts": [{"text": str(item.get("text", ""))}]} for item in history[-10:]]
    gemini_messages.append({"role": "user", "parts": [{"text": message}]})
    reply = call_gemini(gemini_messages) or fallback_reply(analysis["language"], message)
    result = {"reply": reply, "crisis": False, "analysis": analysis}
    activity = choose_activity(message, analysis)
    if activity:
        result["activity"] = activity
    return result


def stream_response_for(payload):
    user_id = str(payload.get("user_id") or "local-user")
    message = str(payload.get("message") or "").strip()
    history = payload.get("history") or []
    if not message:
        raise ValueError("message is required")
    analysis = analyze_locally(message)
    save_trend(user_id, analysis)

    if detect_crisis(message) or long_term_distress(user_id):
        reply = "It sounds like you are going through a very difficult time. Please contact a mental health professional or emergency service now. In Sri Lanka, call 1926 (National Mental Health Helpline) or 1333 (CCCline). If you may act soon, go to the nearest hospital or ask someone you trust to stay with you."
        return iter(({"type": "token", "text": reply}, {"type": "done", "crisis": True, "analysis": analysis}))

    gemini_messages = [{"role": item.get("role", "user"), "parts": [{"text": str(item.get("text", ""))}]} for item in history[-10:]]
    gemini_messages.append({"role": "user", "parts": [{"text": message}]})

    def generate():
        streamed = False
        try:
            for text in stream_gemini(gemini_messages) or ():
                streamed = True
                yield {"type": "token", "text": text}
        except Exception:
            pass
        if not streamed:
            yield {"type": "token", "text": fallback_reply(analysis["language"], message)}
        result = {"type": "done", "crisis": False, "analysis": analysis}
        activity = choose_activity(message, analysis)
        if activity:
            result["activity"] = activity
        yield result

    return generate()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def send_json(self, status, body):
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        if self.path == "/api/health":
            self.send_json(200, {"ok": True, "gemini_configured": bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))})
            return
        self.send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path not in ("/api/chat", "/api/chat/stream"):
            self.send_json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length))
            if self.path == "/api/chat/stream":
                events = stream_response_for(payload)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                for event in events:
                    encoded = f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")
                    self.wfile.write(f"{len(encoded):X}\r\n".encode("ascii"))
                    self.wfile.write(encoded)
                    self.wfile.write(b"\r\n")
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")
                return
            result = response_for(payload)
            self.send_json(200, result)
        except (ValueError, json.JSONDecodeError) as error:
            self.send_json(400, {"error": str(error)})

    def log_message(self, *_args):
        return


if __name__ == "__main__":
    init_db()
    host = os.getenv("HOST", "0.0.0.0")
    server = ThreadingHTTPServer((host, int(os.getenv("PORT", "8000"))), Handler)
    print(f"Mindful support assistant running at http://{host}:{server.server_port}")
    server.serve_forever()
