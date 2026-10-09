import asyncio
import os
import sys
import time

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, query

SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}, "echo": {"type": "string"}},
    "required": ["ok", "echo"],
}


async def main(config_dir: str | None) -> None:
    env = {"CLAUDE_CONFIG_DIR": config_dir} if config_dir else {}
    options = ClaudeAgentOptions(
        tools=[],
        setting_sources=[],
        max_turns=2,
        output_format={"type": "json_schema", "schema": SCHEMA},
        env=env,
        stderr=lambda line: print(f"[stderr] {line}", file=sys.stderr),
    )
    started = time.monotonic()
    async for msg in query(prompt='Return ok=true and echo="pong".', options=options):
        if isinstance(msg, AssistantMessage) and msg.error:
            print(f"assistant.error={msg.error}")
        if isinstance(msg, ResultMessage):
            print(
                f"subtype={msg.subtype} is_error={msg.is_error} "
                f"api_status={msg.api_error_status} errors={msg.errors}"
            )
            print(f"structured={msg.structured_output} result={msg.result!r}")
            print(f"cost={msg.total_cost_usd} elapsed={time.monotonic() - started:.1f}s")


if __name__ == "__main__":
    assert "ANTHROPIC_API_KEY" not in os.environ, "unset ANTHROPIC_API_KEY"
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None))
