import pytest
from cryptography.fernet import InvalidToken

from app.security import decrypt_rtsp_url, encrypt_rtsp_url


def test_encrypt_decrypt_roundtrip():
    url = "rtsp://admin:s3cret@10.0.0.5:554/h264"
    token = encrypt_rtsp_url(url)
    assert url not in token
    assert decrypt_rtsp_url(token) == url


def test_decrypt_rejects_tampered_token():
    token = encrypt_rtsp_url("rtsp://cam/1")
    with pytest.raises(InvalidToken):
        decrypt_rtsp_url(token[:-4] + "AAAA")
