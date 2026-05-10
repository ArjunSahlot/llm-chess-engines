SYSTEM_PROMPT = """Build the strongest chess engine you can.

The only requirements are that the engine is written in C++, uses the UCI protocol, and compiles successfully using `make` in the current run directory.

Use the provided tools to read and write files and compile code. Tools will not execute if not called with the right syntax, make sure to use the correct syntax.

Iterate by writing code, compiling it, and fixing any errors until you have a working engine or you reach the tool call limit ({max_turns} turns). Make sure your code compiles before you lose access to tools.

Make sure the engine supports enough UCI commands to fully play against other engines in any traditional time control: handle `uci`, `isready`, `ucinewgame`, `position`, `go`, and `quit`.

Games will be facilitated with timer controls, so make sure to base time management on go's parameters and allocate time accordingly throughout the game.

Your goal is to create the highest ELO chess engine you can to beat out the competition.
"""

USER_PROMPT = """Generate the C++ chess engine now. Write the source files and Makefile, run the compile tool, and fix any build errors you encounter."""
