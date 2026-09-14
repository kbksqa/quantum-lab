# Save IBM Quantum Platform credentials on THIS machine, then check that they work.
#
# The API key is typed with hidden input and is never printed, logged or written into this repository.
# Qiskit stores it in your user profile (~/.qiskit/qiskit-ibm.json), outside the repo.
#
# Usage (from the repository root):
#     .venv\Scripts\python.exe tools\save_ibm_credentials.py

from __future__ import annotations

import getpass
import sys


def main() -> None:
    from qiskit_ibm_runtime import QiskitRuntimeService

    print("Paste your IBM Quantum API key and press Enter.")
    print("Nothing will appear on screen while you paste - that is normal.")
    token = getpass.getpass("API key: ").strip()
    if not token:
        sys.exit("No key entered - nothing was saved.")

    crn = input("Instance CRN (optional - just press Enter to skip): ").strip() or None

    QiskitRuntimeService.save_account(
        channel="ibm_quantum_platform",
        token=token,
        instance=crn,
        set_as_default=True,
        overwrite=True,
    )
    print("Saved. Checking the connection...")

    try:
        service = QiskitRuntimeService()
        backends = service.backends(operational=True, simulator=False)
        names = sorted(b.name for b in backends)
        print("Connected. Real quantum computers you can use: " + ", ".join(names))
        print("Least busy right now: " + service.least_busy(operational=True, simulator=False).name)
    except Exception as exc:  # show the reason, never the key
        sys.exit("Saved, but the connection check failed: " + type(exc).__name__ + ": " + str(exc))


if __name__ == "__main__":
    main()
