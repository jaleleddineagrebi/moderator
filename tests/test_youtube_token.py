import json

import pytest
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials

from moderator.tools import youtube_upload

TOKEN = {"token": "old", "refresh_token": "r", "client_id": "c.apps.googleusercontent.com", "client_secret": "s",
         "token_uri": "https://oauth2.googleapis.com/token", "scopes": youtube_upload.UPLOAD_SCOPES}


def _expired(monkeypatch):
    def refresh(self, request):
        raise RefreshError("invalid_grant: Token has been expired or revoked.", {"error": "invalid_grant"})

    monkeypatch.setattr(Credentials, "refresh", refresh)
    monkeypatch.setattr(Credentials, "valid", property(lambda self: False))


def test_expired_login_gives_an_actionable_message(monkeypatch):
    _expired(monkeypatch)
    monkeypatch.setenv("YOUTUBE_TOKEN", json.dumps(TOKEN))
    with pytest.raises(RuntimeError) as err:
        youtube_upload.credentials("en")
    text = str(err.value)
    assert "expired or revoked" in text and "youtube-auth" in text and "YOUTUBE_TOKEN" in text and "Publish app" in text
    assert "7 days" in text and "invalid_grant" in text


def test_expired_login_from_file_gives_the_same_message(monkeypatch, tmp_path):
    _expired(monkeypatch)
    path = tmp_path / "youtube_manage.json"
    path.write_text(json.dumps(TOKEN), encoding="utf-8")
    with pytest.raises(RuntimeError, match="youtube_manage.json.*expired or revoked"):
        youtube_upload.credentials_from_file(path)
