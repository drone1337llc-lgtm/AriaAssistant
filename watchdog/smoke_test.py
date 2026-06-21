"""Quick smoke test — verifies Flow + Crew + tools wire up."""
from aisistant.flow import AriaFlow
from aisistant.crew import AisistantCrew
from aisistant.tools import (
    ServiceHealthTool, LogTailTool, ProcessListTool, ProcessKillTool,
    PortCheckTool, NetCheckTool, ActionExecutorTool, KBSearchTool, KBWriterTool,
)
from aisistant.config import SAFE_MODE, TICK_SECONDS, DEFAULT_MODEL, STRONG_MODEL, LM_STUDIO_BASE_URL


def main():
    print("=== Flow ===")
    flow = AriaFlow()
    print(f"  state type: {type(flow.state).__name__}")
    print(f"  tick_number: {flow.state.tick_number}")
    print(f"  started_at: {flow.state.started_at_iso}")

    print("\n=== Crew ===")
    crew = AisistantCrew().crew()
    print(f"  process: {crew.process}")
    print(f"  agents: {len(crew.agents)}, tasks: {len(crew.tasks)}")

    print("\n=== Tools ===")
    for T in (ServiceHealthTool, LogTailTool, ProcessListTool, ProcessKillTool,
              PortCheckTool, NetCheckTool, ActionExecutorTool, KBSearchTool, KBWriterTool):
        inst = T()
        print(f"  - {T.__name__} (name='{inst.name}')")

    print("\n=== Config ===")
    print(f"  safe_mode: {SAFE_MODE}")
    print(f"  tick_seconds: {TICK_SECONDS}")
    print(f"  default_model: {DEFAULT_MODEL}")
    print(f"  strong_model: {STRONG_MODEL}")
    print(f"  lm_studio_url: {LM_STUDIO_BASE_URL}")
    print("\n=== all OK ===")


if __name__ == "__main__":
    main()