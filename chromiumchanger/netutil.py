"""HTTPS requests with a safe certificate fallback.

Python on Windows trusts the Windows certificate store. A fresh VM (or a PC that never visited the site) may be missing
a root certificate, which gives "CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate". In that case we
retry ONCE with the CA bundle shipped in assets/cacert.pem (Mozilla roots, from certifi, MPL-2.0).
Verification is never switched off.
"""
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

HINT = ("The HTTPS certificate could not be verified even with the bundled certificates. Check that the date and time "
        "of this computer are correct, that no security software or proxy is intercepting HTTPS, "
        "and that Windows is up to date.")


def _bundle():
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    p = base / "assets" / "cacert.pem"
    return p if p.exists() else None


def _is_cert_error(e):
    r = getattr(e, "reason", e)
    return isinstance(r, ssl.SSLCertVerificationError) or isinstance(e, ssl.SSLCertVerificationError)


def urlopen(req, timeout=60):
    """Like urllib.request.urlopen, with the fallback described above (for https only)."""
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except (urllib.error.URLError, ssl.SSLError) as e:
        url = req if isinstance(req, str) else req.full_url
        bundle = _bundle()
        if not (url.lower().startswith("https://") and _is_cert_error(e) and bundle):
            raise
        ctx = ssl.create_default_context(cafile=str(bundle))
        try:
            return urllib.request.urlopen(req, timeout=timeout, context=ctx)
        except (urllib.error.URLError, ssl.SSLError) as e2:
            if _is_cert_error(e2):
                raise urllib.error.URLError(f"{e2} -- {HINT}") from e2
            raise
