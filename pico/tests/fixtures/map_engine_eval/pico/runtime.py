"""Paths under pico make PICO a case-preserving path-ident fixture."""

from pico.tools import build_tool_name


class PicoRuntime:
    def run(self) -> str:
        return build_tool_name()
