"""
Rust Engine Bridge for WealthMap FastAPI & Streamlit.

Interfaces Python WealthMap calls with the high-performance Rust
`wealthmap-engine` core via PyO3 native extension bindings.
"""

from __future__ import annotations
import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_RUST_ENGINE_AVAILABLE = False
try:
    import os
    import sys
    if sys.platform == "win32":
        mingw_bin = r"C:\Users\Dell\AppData\Local\Microsoft\WinGet\Packages\MartinStorsjo.LLVM-MinGW.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe\llvm-mingw-20260616-ucrt-x86_64\bin"
        if os.path.exists(mingw_bin):
            try:
                os.add_dll_directory(mingw_bin)
            except AttributeError:
                os.environ["PATH"] = mingw_bin + os.pathsep + os.environ.get("PATH", "")
    import wealthmap_engine
    _RUST_ENGINE_AVAILABLE = True
except Exception as exc:
    logger.warning("Native PyO3 'wealthmap_engine' module not loaded (%s). Falling back to pure Python execution.", exc)


class RustEngineBridge:
    """Interface to wealthmap-engine Rust core."""

    @staticmethod
    def is_available() -> bool:
        return _RUST_ENGINE_AVAILABLE

    @classmethod
    def compute_tax_lots(cls, raw_transactions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Executes Scan -> Filter -> Sort -> FIFOMatch -> GroupAggregate pipeline
        in Rust and returns matched lots and aggregates.
        """
        if not _RUST_ENGINE_AVAILABLE:
            raise RuntimeError("wealthmap_engine Rust extension is not available.")

        txs_json = json.dumps(raw_transactions)
        result_json_str = wealthmap_engine.compute_fifo_tax_json(txs_json)
        return json.loads(result_json_str)
