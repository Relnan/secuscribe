"""
secuscribe/encryption.py
~~~~~~~~~~~~~~~~~~~~~~~~
GnuPG encryption wrapper for transcription output files.

Encrypts text or JSON output with the recipient's public key so that
transcript files are protected at rest.  Requires the ``gpg`` binary to be
installed and the recipient's public key to be imported into the keyring
(both trivially satisfied on any standard Debian installation).

Usage::

    from pathlib import Path
    from secuscribe.encryption import GPGEncryptor

    enc = GPGEncryptor(recipient="security@example.com")
    enc.encrypt_file(Path("transcript.json"))
    # Produces transcript.json.gpg and (optionally) removes the plaintext.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Suffix appended to output files produced by GPG
_GPG_SUFFIX = ".gpg"


def _require_gpg() -> None:
    """Raise :exc:`RuntimeError` if the ``gpg`` binary is not available."""
    if shutil.which("gpg") is None:
        raise RuntimeError(
            "The 'gpg' binary was not found. "
            "Install GnuPG: apt-get install gnupg"
        )


class GPGEncryptor:
    """
    Wrapper around *python-gnupg* for encrypting transcript output files.

    Parameters
    ----------
    recipient:
        GPG key ID, fingerprint, or e-mail address of the recipient.
        The corresponding public key must already be imported into the
        GnuPG keyring.
    gpg_home:
        Path to the GnuPG home directory.  Defaults to ``~/.gnupg``.
    always_trust:
        Whether to pass ``--trust-model always`` to GPG.  Useful in
        automated, air-gapped environments where the web-of-trust is
        not maintained.
    """

    def __init__(
        self,
        recipient: str,
        gpg_home: Optional[Path] = None,
        *,
        always_trust: bool = True,
    ) -> None:
        _require_gpg()

        try:
            import gnupg  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "python-gnupg is required for encryption. "
                "Install it with: pip install python-gnupg"
            ) from exc

        self._recipient = recipient
        self._always_trust = always_trust
        gpg_kwargs: dict = {}
        if gpg_home is not None:
            gpg_kwargs["gnupghome"] = str(gpg_home)
        self._gpg = gnupg.GPG(**gpg_kwargs)
        self._gpg.encoding = "utf-8"
        logger.debug("GPGEncryptor initialised (recipient=%s).", recipient)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def encrypt_file(
        self,
        path: Path | str,
        *,
        remove_plaintext: bool = True,
        output_path: Optional[Path] = None,
    ) -> Path:
        """
        Encrypt *path* for the configured recipient.

        Parameters
        ----------
        path:
            Plaintext file to encrypt.
        remove_plaintext:
            If ``True`` (default), the plaintext file is deleted after
            successful encryption.
        output_path:
            Explicit path for the ``.gpg`` output file.  Defaults to
            ``<path>.gpg``.

        Returns
        -------
        Path
            Path of the encrypted output file.

        Raises
        ------
        FileNotFoundError
            If *path* does not exist.
        RuntimeError
            If GPG reports an error.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        out = output_path or path.with_suffix(path.suffix + _GPG_SUFFIX)

        logger.info("Encrypting %s → %s…", path.name, out.name)
        with open(path, "rb") as fh:
            result = self._gpg.encrypt_file(
                fh,
                recipients=[self._recipient],
                output=str(out),
                always_trust=self._always_trust,
            )

        if not result.ok:
            raise RuntimeError(
                f"GPG encryption failed for {path}: {result.stderr}"
            )

        logger.info("Encrypted: %s", out)

        if remove_plaintext:
            path.unlink()
            logger.info("Plaintext removed: %s", path)

        return out

    def encrypt_string(self, text: str) -> str:
        """
        Encrypt *text* in ASCII-armoured format and return the ciphertext.

        Raises
        ------
        RuntimeError
            If GPG reports an error.
        """
        result = self._gpg.encrypt(
            text,
            recipients=[self._recipient],
            always_trust=self._always_trust,
            armor=True,
        )
        if not result.ok:
            raise RuntimeError(f"GPG string encryption failed: {result.stderr}")
        return str(result)

    def list_keys(self) -> list[dict]:
        """Return the list of public keys currently in the keyring."""
        return self._gpg.list_keys()

    def import_key(self, key_data: str) -> None:
        """
        Import an ASCII-armoured public key into the local keyring.

        Parameters
        ----------
        key_data:
            ASCII-armoured GPG public key block.
        """
        result = self._gpg.import_keys(key_data)
        logger.info(
            "Key import result: %d imported, %d unchanged.",
            result.imported,
            result.unchanged,
        )
