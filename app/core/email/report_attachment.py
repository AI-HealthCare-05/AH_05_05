"""Offline password-encrypted HTML. Never write report plaintext or keys to disk."""

import base64
import hashlib
import json
import secrets
from datetime import date
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATES = Environment(
    loader=FileSystemLoader(Path(__file__).resolve().parents[2] / "static" / "templates"),
    autoescape=select_autoescape(["html"]),
)
_ITERATIONS = 600_000


def encrypt_report_html(markup: str, birth_date: date) -> bytes:
    if not isinstance(birth_date, date):
        raise ValueError("보고서 첨부파일을 암호화하려면 생년월일이 필요합니다.")
    salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
    key = hashlib.pbkdf2_hmac("sha256", birth_date.strftime("%y%m%d").encode("ascii"), salt, _ITERATIONS, 32)
    envelope = {
        "salt": base64.b64encode(salt).decode("ascii"),
        "iv": base64.b64encode(iv).decode("ascii"),
        "iterations": _ITERATIONS,
        "ciphertext": base64.b64encode(AESGCM(key).encrypt(iv, markup.encode("utf-8"), None)).decode("ascii"),
    }
    # Values are exclusively generated base64 and an integer, never user markup.
    return _TEMPLATES.get_template("reports/encrypted.html").render(envelope=json.dumps(envelope)).encode("utf-8")
