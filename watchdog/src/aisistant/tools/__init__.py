"""Tools for the Aria autonomous backend crew.

Each tool is a thin CrewAI BaseTool wrapping a focused operation. The agents
(Watcher, Diagnostician, Fixer, Verifier, Knowledge Manager) reference them
by class name in crew.py.
"""
from aisistant.tools.service_health import BrainHealthTool, ServiceHealthTool
from aisistant.tools.log_tail import LogTailTool
from aisistant.tools.process_check import ProcessListTool, ProcessKillTool
from aisistant.tools.port_check import PortCheckTool
from aisistant.tools.network_check import NetCheckTool
from aisistant.tools.action_executor import ActionExecutorTool
from aisistant.tools.kb_search import KBSearchTool
from aisistant.tools.kb_writer import KBWriterTool

__all__ = [
    "ServiceHealthTool",
    "BrainHealthTool",
    "LogTailTool",
    "ProcessListTool",
    "ProcessKillTool",
    "PortCheckTool",
    "NetCheckTool",
    "ActionExecutorTool",
    "KBSearchTool",
    "KBWriterTool",
]