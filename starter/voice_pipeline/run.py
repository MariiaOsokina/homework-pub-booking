"""Ex8 — voice pipeline runner."""

from __future__ import annotations

import asyncio
import os
import sys

from sovereign_agent._internal.paths import example_sessions_dir
from sovereign_agent.session.directory import create_session

from starter.voice_pipeline.manager_persona import ManagerPersona
from starter.voice_pipeline.voice_loop import run_text_mode, run_voice_mode


async def main_async(voice: bool) -> int:
    with example_sessions_dir("ex8-voice-pipeline", persist=True) as sessions_root:
        session = create_session(
            scenario="ex8-voice-pipeline",
            task="Converse with Alasdair MacLeod (pub manager) to arrange a booking.",
            sessions_dir=sessions_root,
        )
        print(f"Session {session.session_id}")
        print(f"  dir: {session.directory}")

        if not os.environ.get("NEBIUS_KEY"):
            print("✗ NEBIUS_KEY not set. Run 'make verify' first.", file=sys.stderr)
            return 1

        persona = ManagerPersona.from_env()

        if voice:
            await run_voice_mode(session, persona)
        else:
            await run_text_mode(session, persona)

        return 0


def main() -> None:
    voice = "--voice" in sys.argv
    # --text is the default and can also be passed explicitly
    sys.exit(asyncio.run(main_async(voice=voice)))


if __name__ == "__main__":
    main()
