"""Permite ejecutar `python -m taller_cultura ...` como atajo de la CLI."""

import sys

from taller_cultura.main import main

if __name__ == "__main__":
    sys.exit(main())
