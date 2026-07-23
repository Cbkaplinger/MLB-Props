"""Windows-compatible nbconvert entry point used by export-notebook.ps1."""

from __future__ import annotations

import asyncio
import sys

from nbconvert.nbconvertapp import NbConvertApp


app = NbConvertApp()
app.initialize()

# nbconvert selects the Windows selector loop during initialization, but
# Playwright requires subprocess support from the proactor loop.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

app.start()
