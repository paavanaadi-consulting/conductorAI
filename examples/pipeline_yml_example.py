import yaml

from conductor import ConductorAI
from conductor.agents import PipelineYamlGeneratorAgent
from conductor.core.config import ConductorConfig
from conductor.core.config import load_config
from conductor.core.enums import AgentType, WorkflowPhase
from conductor.core.models import TaskDefinition, WorkflowDefinition
from conductor.integrations.llm.anthropic_provider import AnthropicProvider
from conductor.integrations.llm.mock import MockLLMProvider
from conductor.orchestration.workflow_engine import WorkflowEngine
import asyncio

async def main():
    requirement_doc_path = "D:\\Learning\\ConductorAI\\Documents\\requirement.yaml"
    infra_doc_path = "D:\\Learning\\ConductorAI\\Documents\\infra.yaml"
    with open(requirement_doc_path, "r") as requirement_file_ptr, open(infra_doc_path, "r") as infra_file_ptr:
        task = TaskDefinition(name="pipeline-generation-task", description="Pipeline generation task",
                              input_data={
                                  "requirements_yaml": requirement_file_ptr,
                                  "infra_yaml": infra_file_ptr
                              },
                              assigned_to=AgentType.PIPELINE_GENERATOR)

        workflow_definition = WorkflowDefinition(tasks=[task], name="pipeline-generation-task",
                                             phases=[WorkflowPhase.BASE])

        conductor_config = load_config("D:\\Project\\MachineLearning\\conductorAI\\conductor.yaml")
        async with ConductorAI(conductor_config) as conductor:

            #llm_provider = MockLLMProvider()

            llm_provider = AnthropicProvider(conductor_config.llm)
            pipeline_agent = PipelineYamlGeneratorAgent("pipeline-001", llm_provider=llm_provider,
                                                        config=conductor_config)
            await conductor.register_agent(pipeline_agent)
            await conductor.run_workflow(workflow_definition)


if __name__ == "__main__":
    asyncio.run(main())










