import app



def setup_database(tmp_path):
    app.DB_PATH = tmp_path / "test.db"
    app.init_db()


def test_stress_message_does_not_suggest_activity(tmp_path):
    setup_database(tmp_path)
    result = app.response_for({"user_id": "test", "message": "I feel stressed and overwhelmed"})
    assert result["crisis"] is False
    assert result["analysis"]["language"] == "en"
    assert "activity" not in result


def test_loneliness_message_suggests_activity(tmp_path):
    setup_database(tmp_path)
    result = app.response_for({"user_id": "test", "message": "I feel lonely today"})
    assert result["activity"]["name"] == "One-page journaling"


def test_boredom_message_suggests_activity(tmp_path):
    setup_database(tmp_path)
    result = app.response_for({"user_id": "test", "message": "I am bored and need something to do"})
    assert "activity" in result


def test_streaming_fallback_returns_tokens_and_done_event(tmp_path, monkeypatch):
    setup_database(tmp_path)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    events = list(app.stream_response_for({"user_id": "test", "message": "I feel lonely"}))
    assert events[0]["type"] == "token"
    assert events[-1]["type"] == "done"
    assert events[-1]["activity"]["name"] == "One-page journaling"


def test_sinhala_crisis_overrides_model(tmp_path):
    setup_database(tmp_path)
    result = app.response_for({"user_id": "test", "message": "මට මැරෙන්න හිතෙනවා"})
    assert result["crisis"] is True
    assert "1926" in result["reply"]


def test_hello_has_a_greeting_fallback(tmp_path):
    setup_database(tmp_path)
    result = app.response_for({"user_id": "test", "message": "hello"})
    assert result["crisis"] is False
    assert result["reply"] == "Hello. I am here with you. How are you feeling today?"


def test_crisis_label_matches_crisis_model_reply(tmp_path, monkeypatch):
    setup_database(tmp_path)
    monkeypatch.setattr(app, "call_gemini", lambda messages: "Please call a suicide crisis helpline now.")
    result = app.response_for({"user_id": "test", "message": "I need help understanding this"})
    assert result["crisis"] is True


def test_streaming_crisis_label_matches_streamed_reply(tmp_path, monkeypatch):
    setup_database(tmp_path)
    monkeypatch.setattr(app, "stream_gemini", lambda messages: iter(("Please contact a suicide crisis helpline.",)))
    events = list(app.stream_response_for({"user_id": "test", "message": "I need help understanding this"}))
    assert events[-1]["crisis"] is True
