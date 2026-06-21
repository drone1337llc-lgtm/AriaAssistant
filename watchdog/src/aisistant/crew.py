"""Aria autonomous backend crew.

5 agents, 5 tasks, sequential process:
  watch_task → diagnose_task → fix_task → verify_task → learn_task
"""
from __future__ import annotations

import os
from typing import List

from crewai import Agent, Crew, LLM, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task

from aisistant.config import DEFAULT_MODEL, LM_STUDIO_BASE_URL, LM_STUDIO_API_KEY, STRONG_MODEL
from aisistant.schemas import (
    ActionsReport,
    DiagnosesReport,
    LearningSummary,
    VerificationsReport,
    WatchReport,
)
from aisistant.tools import (
    ActionExecutorTool,
    BrainHealthTool,
    KBSearchTool,
    KBWriterTool,
    LogTailTool,
    NetCheckTool,
    PortCheckTool,
    ProcessKillTool,
    ProcessListTool,
    ServiceHealthTool,
)


def _llm(model: str) -> LLM:
    """Build an LLM pointed at LM Studio (OpenAI-compatible) on PC 2."""
    return LLM(
        model=model,
        base_url=LM_STUDIO_BASE_URL,
        api_key=LM_STUDIO_API_KEY,
        temperature=0.2,
    )


@CrewBase
class AisistantCrew:
    """Aria autonomous backend maintenance crew."""

    agents: List[BaseAgent]
    tasks: List[Task]

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    # --- Tools ---------------------------------------------------------------

    @staticmethod
    def _watcher_tools() -> list:
        return [ServiceHealthTool(), LogTailTool()]

    @staticmethod
    def _diagnostician_tools() -> list:
        return [KBSearchTool(), LogTailTool(), PortCheckTool(), ProcessListTool(), BrainHealthTool()]

    @staticmethod
    def _fixer_tools() -> list:
        return [ActionExecutorTool(), ProcessKillTool(), PortCheckTool()]

    @staticmethod
    def _verifier_tools() -> list:
        return [ServiceHealthTool(), LogTailTool()]

    @staticmethod
    def _knowledge_tools() -> list:
        return [KBWriterTool()]

    # --- Agents --------------------------------------------------------------

    @agent
    def watcher(self) -> Agent:
        return Agent(
            config=self.agents_config["watcher"],  # type: ignore[index]
            llm=_llm(DEFAULT_MODEL),
            tools=self._watcher_tools(),
            cache=True,
            inject_date=True,
            verbose=True,
        )

    @agent
    def diagnostician(self) -> Agent:
        return Agent(
            config=self.agents_config["diagnostician"],  # type: ignore[index]
            llm=_llm(STRONG_MODEL),
            tools=self._diagnostician_tools(),
            cache=True,
            inject_date=True,
            verbose=True,
        )

    @agent
    def fixer(self) -> Agent:
        return Agent(
            config=self.agents_config["fixer"],  # type: ignore[index]
            llm=_llm(DEFAULT_MODEL),
            tools=self._fixer_tools(),
            cache=True,
            inject_date=True,
            verbose=True,
        )

    @agent
    def verifier(self) -> Agent:
        return Agent(
            config=self.agents_config["verifier"],  # type: ignore[index]
            llm=_llm(DEFAULT_MODEL),
            tools=self._verifier_tools(),
            cache=True,
            inject_date=True,
            verbose=True,
        )

    @agent
    def knowledge_manager(self) -> Agent:
        return Agent(
            config=self.agents_config["knowledge_manager"],  # type: ignore[index]
            llm=_llm(STRONG_MODEL),
            tools=self._knowledge_tools(),
            cache=True,
            inject_date=True,
            verbose=True,
        )

    # --- Tasks ---------------------------------------------------------------

    @task
    def watch_task(self) -> Task:
        return Task(
            config=self.tasks_config["watch_task"],  # type: ignore[index]
            output_pydantic=WatchReport,
        )

    @task
    def diagnose_task(self) -> Task:
        return Task(
            config=self.tasks_config["diagnose_task"],  # type: ignore[index]
            output_pydantic=DiagnosesReport,
        )

    @task
    def fix_task(self) -> Task:
        return Task(
            config=self.tasks_config["fix_task"],  # type: ignore[index]
            output_pydantic=ActionsReport,
        )

    @task
    def verify_task(self) -> Task:
        return Task(
            config=self.tasks_config["verify_task"],  # type: ignore[index]
            output_pydantic=VerificationsReport,
        )

    @task
    def learn_task(self) -> Task:
        return Task(
            config=self.tasks_config["learn_task"],  # type: ignore[index]
            output_pydantic=LearningSummary,
        )

    # --- Crew ----------------------------------------------------------------

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
            output_log_file=True,
        )