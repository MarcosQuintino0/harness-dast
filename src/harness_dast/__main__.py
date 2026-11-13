"""Permite executar a CLI com `python -m harness_dast`."""

import sys

from harness_dast.cli.app import main

sys.exit(main())
