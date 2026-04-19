"""
ConductorAI UI — ConductorAI Facade Wrapper
"""

from __future__ import annotations

import structlog
from typing import Any, Optional

from conductor import ConductorAI
from conductor.core.config import ConductorConfig, LLMConfig
from conductor.core.enums import AgentType
from conductor.core.models import TaskDefinition
from conductor.integrations.llm.factory import create_llm_provider
from conductor.integrations.llm.base import BaseLLMProvider

from ui.api.config import APISettings

logger = structlog.get_logger()


class ConductorService:
    """Singleton wrapper around the ConductorAI facade."""

    def __init__(self, settings: APISettings) -> None:
        self._settings = settings
        self._conductor: Optional[ConductorAI] = None
        self._llm_provider: Optional[BaseLLMProvider] = None

    async def initialize(self) -> None:
        config = ConductorConfig(
            llm=LLMConfig(
                provider=self._settings.conductor_llm_provider,
                model=self._settings.conductor_llm_model,
                api_key=self._settings.conductor_llm_api_key,
            ),
        )
        self._llm_provider = create_llm_provider(config.llm)
        self._conductor = ConductorAI(config)
        await self._conductor.initialize()
        await self._register_agents()
        logger.info("conductor_service.initialized")

    async def _register_agents(self) -> None:
        from conductor.agents.development.coding_agent import CodingAgent
        from conductor.agents.development.review_agent import ReviewAgent
        from conductor.agents.development.test_agent import TestAgent
        from conductor.agents.development.test_data_agent import TestDataAgent
        from conductor.agents.devops.devops_agent import DevOpsAgent
        from conductor.agents.devops.deploying_agent import DeployingAgent
        from conductor.agents.monitoring.monitor_agent import MonitorAgent
        from conductor.agents.pipeline.pipeline_yaml_generator import (
            PipelineYamlGeneratorAgent,
        )
        from conductor.agents.development.readme_generator_agent import (
            ReadmeGeneratorAgent
        )

        agents = [
            CodingAgent("coding-01", self._conductor.config, llm_provider=self._llm_provider),
            ReviewAgent("review-01", self._conductor.config, llm_provider=self._llm_provider),
            TestAgent("test-01", self._conductor.config, llm_provider=self._llm_provider),
            TestDataAgent("test-data-01", self._conductor.config, llm_provider=self._llm_provider),
            DevOpsAgent("devops-01", self._conductor.config, llm_provider=self._llm_provider),
            DeployingAgent("deploying-01", self._conductor.config, llm_provider=self._llm_provider),
            MonitorAgent("monitor-01", self._conductor.config, llm_provider=self._llm_provider),
            PipelineYamlGeneratorAgent(
                "pipeline-gen-01", self._conductor.config, llm_provider=self._llm_provider
            ),
            ReadmeGeneratorAgent(
                "readme-gen-01", self._conductor.config, llm_provider=self._llm_provider
            )

        ]
        for agent in agents:
            await self._conductor.register_agent(agent)

    @property
    def conductor(self) -> ConductorAI:
        assert self._conductor is not None
        return self._conductor

    async def generate_pipeline(
        self,
        requirements_yaml: str,
        infra_yaml: str,
        pipeline_type: str = "auto",
    ) -> dict[str, Any]:
        return await self._conductor.generate_pipeline_yaml(
            requirements_yaml, infra_yaml, pipeline_type=pipeline_type
        )

    async def generate_readme(
        self,
        requirements_yaml: str,
        infra_yaml: str,
    ) -> dict[str, Any]:
        return await self._conductor.generate_readme_txt(
            requirements_yaml, infra_yaml)

    async def run_workflow(self, definition) -> Any:
        return await self._conductor.run_workflow(definition)

    async def review_code(
        self,
        code: str,
        language: str = "python",
        context: str = "",
    ) -> dict[str, Any]:
        task = TaskDefinition(
            name="PR Code Review",
            assigned_to=AgentType.REVIEW,
            input_data={
                "code": code,
                "language": language,
                "context": context,
                "review_criteria": [
                    "correctness",
                    "security",
                    "performance",
                    "maintainability",
                    "readability",
                ],
            },
        )
        result = await self._conductor.dispatch_task(task)
        return result.output_data if hasattr(result, "output_data") else {}

    async def shutdown(self) -> None:
        if self._conductor:
            await self._conductor.shutdown()
            logger.info("conductor_service.shutdown")
