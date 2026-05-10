SYSTEM_PROMPT = """You are building a chess engine for a standardized benchmark.

Create a compact C++ UCI chess engine in the current run directory. The project must include a Makefile at the run directory root, and `make` must build the engine binary without interactive input.

Use only the provided tools for file I/O and compilation. Keep all files inside the current run directory. Do not read or write outside it. Iterate with the compile tool until the project builds or you have reached the turn limit.

Favor reliable, simple chess logic over elaborate unfinished features. The engine should speak enough UCI to run in automated matches later: handle `uci`, `isready`, `ucinewgame`, `position`, `go`, and `quit`.
"""


USER_PROMPT = """Generate the C++ chess engine now. Write the source files and Makefile, run the compile tool, and fix any build errors you encounter."""
