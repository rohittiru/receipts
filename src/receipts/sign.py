"""Ed25519 signing and verification for receipts.

A key pair lives at:
    ~/.receipts/keys/signing.key      (raw 32-byte seed, private)
    ~/.receipts/keys/signing.pub      (raw 32-byte verify key, public, hex-encoded)

Receipts include a `signature` block with the Ed25519 signature over a
canonicalized JSON serialization of the payload (everything except the
signature block itself). Canonicalization uses sorted keys + minimal separators
so two implementations will produce byte-identical inputs.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

from nacl import encoding, exceptions, signing


def default_key_dir() -> Path:
    return Path.home() / ".receipts" / "keys"


def ensure_keypair(key_dir: Path | None = None) -> tuple[Path, Path]:
    """Generate a signing key pair on first run; return (priv_path, pub_path)."""
    key_dir = key_dir or default_key_dir()
    key_dir.mkdir(parents=True, exist_ok=True)
    priv_path = key_dir / "signing.key"
    pub_path = key_dir / "signing.pub"

    if priv_path.exists() and pub_path.exists():
        return priv_path, pub_path

    sk = signing.SigningKey.generate()
    vk = sk.verify_key

    priv_path.write_bytes(sk.encode())
    # Restrict to owner read/write only — best effort, POSIX-only
    try:
        priv_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass

    pub_path.write_text(vk.encode(encoder=encoding.HexEncoder).decode("ascii"))
    return priv_path, pub_path


def load_signing_key(priv_path: Path | None = None) -> signing.SigningKey:
    priv_path = priv_path or (default_key_dir() / "signing.key")
    if not priv_path.exists():
        raise FileNotFoundError(
            f"no signing key at {priv_path}; run `receipts keygen` or `receipts run` once to generate"
        )
    return signing.SigningKey(priv_path.read_bytes())


def public_key_hex(sk: signing.SigningKey) -> str:
    return sk.verify_key.encode(encoder=encoding.HexEncoder).decode("ascii")


def canonicalize(payload: dict[str, Any]) -> bytes:
    """Canonicalize a JSON-serializable payload for signing.

    Sorted keys, no extra whitespace, UTF-8. This is *not* full RFC 8785 JCS —
    it's the "good enough" subset that two CPython implementations will agree
    on. For interop with non-Python verifiers, we'll move to JCS in v0.2.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sign_payload(payload: dict[str, Any], sk: signing.SigningKey) -> dict[str, str]:
    """Return a signature block: {algorithm, public_key, signature}."""
    message = canonicalize(payload)
    sig = sk.sign(message).signature
    return {
        "algorithm": "ed25519",
        "canonicalization": "json-sorted-keys-v1",
        "public_key": public_key_hex(sk),
        "signature": sig.hex(),
    }


class VerificationError(ValueError):
    """Raised when a receipt's signature does not verify."""


def verify_receipt(receipt: dict[str, Any]) -> str:
    """Verify a receipt's signature; return the public key hex on success.

    Raises VerificationError if the signature is missing or invalid.
    """
    sig_block = receipt.get("signature")
    if not isinstance(sig_block, dict):
        raise VerificationError("receipt has no signature block")

    algorithm = sig_block.get("algorithm")
    if algorithm != "ed25519":
        raise VerificationError(f"unsupported signature algorithm: {algorithm!r}")

    canonicalization = sig_block.get("canonicalization")
    if canonicalization != "json-sorted-keys-v1":
        raise VerificationError(
            f"unsupported canonicalization: {canonicalization!r}"
        )

    pub_hex = sig_block.get("public_key")
    sig_hex = sig_block.get("signature")
    if not pub_hex or not sig_hex:
        raise VerificationError("signature block missing public_key or signature")

    try:
        vk = signing.VerifyKey(pub_hex, encoder=encoding.HexEncoder)
        sig_bytes = bytes.fromhex(sig_hex)
    except (ValueError, exceptions.TypeError) as e:
        raise VerificationError(f"malformed signature: {e}") from e

    payload = {k: v for k, v in receipt.items() if k != "signature"}
    message = canonicalize(payload)

    try:
        vk.verify(message, sig_bytes)
    except exceptions.BadSignatureError as e:
        raise VerificationError(f"signature does not verify: {e}") from e

    return pub_hex
