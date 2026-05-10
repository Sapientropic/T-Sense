"""Small Windows Credential Manager wrapper for local-only Signal Desk secrets."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass
from datetime import UTC, datetime


CRED_TYPE_GENERIC = 1
# Generic credentials are scoped to the current Windows user by Credential
# Manager. This persist mode keeps the secret across that user's logon sessions
# on the same machine, which is the intended Windows alpha boundary.
CRED_PERSIST_LOCAL_MACHINE = 2
ERROR_NOT_FOUND = 1168


class CredentialStoreError(RuntimeError):
    """Raised when the platform credential store cannot complete an operation."""


@dataclass(frozen=True)
class StoredSecret:
    secret: str
    updated_at: str | None = None


class _FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", wintypes.DWORD),
        ("dwHighDateTime", wintypes.DWORD),
    ]


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", _FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def is_supported() -> bool:
    return os.name == "nt"


def _advapi32():
    if not is_supported():
        raise CredentialStoreError("Windows Credential Manager is not available on this platform.")
    library = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    library.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
    library.CredWriteW.restype = wintypes.BOOL
    library.CredReadW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(_CREDENTIALW)),
    ]
    library.CredReadW.restype = wintypes.BOOL
    library.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    library.CredDeleteW.restype = wintypes.BOOL
    library.CredFree.argtypes = [ctypes.c_void_p]
    library.CredFree.restype = None
    return library


def _last_error_message(prefix: str) -> CredentialStoreError:
    code = ctypes.get_last_error()
    return CredentialStoreError(f"{prefix} failed with Windows error {code}.")


def _filetime_to_iso(value: _FILETIME) -> str | None:
    raw = (int(value.dwHighDateTime) << 32) + int(value.dwLowDateTime)
    if raw <= 0:
        return None
    # Windows FILETIME counts 100ns intervals since 1601-01-01 UTC.
    unix_seconds = (raw - 116444736000000000) / 10_000_000
    return datetime.fromtimestamp(unix_seconds, tz=UTC).isoformat().replace("+00:00", "Z")


def read_secret(target_name: str) -> StoredSecret | None:
    library = _advapi32()
    credential = ctypes.POINTER(_CREDENTIALW)()
    ok = library.CredReadW(target_name, CRED_TYPE_GENERIC, 0, ctypes.byref(credential))
    if not ok:
        if ctypes.get_last_error() == ERROR_NOT_FOUND:
            return None
        raise _last_error_message("CredReadW")
    try:
        item = credential.contents
        if item.CredentialBlobSize <= 0:
            secret = ""
        else:
            blob = ctypes.string_at(item.CredentialBlob, item.CredentialBlobSize)
            secret = blob.decode("utf-16-le")
        return StoredSecret(secret=secret, updated_at=_filetime_to_iso(item.LastWritten))
    finally:
        library.CredFree(credential)


def write_secret(target_name: str, secret: str, *, username: str = "Signal Desk") -> None:
    clean = str(secret or "").strip()
    if not clean:
        raise ValueError("Secret cannot be empty.")
    blob = clean.encode("utf-16-le")
    if len(blob) > 2048:
        raise ValueError("Secret is too long for local secure storage.")
    library = _advapi32()
    blob_buffer = ctypes.create_string_buffer(blob)
    credential = _CREDENTIALW()
    credential.Type = CRED_TYPE_GENERIC
    credential.TargetName = target_name
    credential.CredentialBlobSize = len(blob)
    credential.CredentialBlob = ctypes.cast(blob_buffer, ctypes.POINTER(ctypes.c_ubyte))
    credential.Persist = CRED_PERSIST_LOCAL_MACHINE
    credential.UserName = username
    if not library.CredWriteW(ctypes.byref(credential), 0):
        raise _last_error_message("CredWriteW")


def delete_secret(target_name: str) -> None:
    library = _advapi32()
    ok = library.CredDeleteW(target_name, CRED_TYPE_GENERIC, 0)
    if ok or ctypes.get_last_error() == ERROR_NOT_FOUND:
        return
    raise _last_error_message("CredDeleteW")
