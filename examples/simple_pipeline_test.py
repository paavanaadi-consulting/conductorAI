"""
Simple Pipeline Generator Test
================================

Quick test of the PipelineYamlGeneratorAgent without debugging overhead.
This shows the basic flow in a clean, simple way.

Usage:
    python examples/simple_pipeline_test.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from conductor.agents.pipeline import PipelineYamlGeneratorAgent
from conductor.core.config import ConductorConfig
from conductor.core.enums import AgentType
from conductor.core.models import TaskDefinition
from conductor.integrations.llm.mock import MockLLMProvider


# Sample minimal requirements
REQUIREMENTS = """
project_name: "sales-analytics"
team: "data-team"

pipeline_type: "batch"
sources:
  - name: "Salesforce"
    type: "api"
destination:
  target: "Snowflake"
quality_requirements:
  accuracy: ">= 99%"
schedule:
  batch_frequency: "daily"
"""

INFRASTRUCTURE = """
cloud_provider: "aws"
data_warehouse:
  platform: "snowflake"
orchestration:
  tool: "airflow"
"""

# Mock LLM response
MOCK_RESPONSE = """
project:
  name: "sales-analytics-pipeline"
  version: "1.0.0"

business_requirements:
  objective: "Sales analytics pipeline"

data_sources:
  - name: "salesforce_api"
    type: "rest_api"
    schedule: "daily"

transformations:
  architecture: "simple"
  tools: ["dbt"]

orchestration:
  tool: "airflow"
  dag_schedule: "daily"

storage:
  warehouse: "snowflake"
  database: "analytics"

monitoring:
  tools: ["datadog"]
  alerts: []

success_criteria:
  - "Data quality >= 99%"
"""


async def main():
    """Run a simple pipeline generation test."""
    
    print("\n" + "="*70)
    print("  Simple Pipeline YAML Generator Test")
    print("="*70)
    
    # 1. Setup
    print("\n1️⃣  Setting up...")
    config = ConductorConfig()
    llm_provider = MockLLMProvider(responses=[MOCK_RESPONSE])
    agent = PipelineYamlGeneratorAgent(
        agent_id="pipeline-gen-test",
        config=config,
        llm_provider=llm_provider,
    )
    print("   ✓ Agent created")
    
    # 2. Start agent
    print("\n2️⃣  Starting agent...")
    await agent.start()
    print(f"   ✓ Status: {agent.status.value}")
    
    # 3. Create task
    print("\n3️⃣  Creating task...")
    task = TaskDefinition(
        name="Generate Sales Analytics Pipeline",
        assigned_to=AgentType.PIPELINE_GENERATOR,
        input_data={
            "requirements_yaml": REQUIREMENTS,
            "infra_yaml": INFRASTRUCTURE,
            "pipeline_type": "auto",  # Auto-detect
        }
    )
    print(f"   ✓ Task: {task.name}")
    
    # 4. Execute
    print("\n4️⃣  Executing task...")
    result = await agent.execute_task(task)
    print(f"   ✓ Status: {result.status.value}")
    print(f"   ✓ Duration: {result.duration_seconds:.3f}s")
    
    # 5. Results
    print("\n5️⃣  Results:")
    print(f"   Pipeline Type: {result.output_data.get('pipeline_type')}")
    print(f"   Confidence: {result.output_data.get('pipeline_type_confidence', 0):.0%}")
    print(f"   Validation: {'✓ Valid' if result.output_data.get('validation_result', {}).get('valid') else '✗ Invalid'}")
    print(f"   Sections: {len(result.output_data.get('sections_generated', []))}")
    print(f"   Generation Stages: {result.output_data.get('generation_stages', 1)}")
    
    # 6. Show generated YAML
    print("\n6️⃣  Generated Pipeline YAML:")
    print("-"*70)
    pipeline_yaml = result.output_data.get('pipeline_yaml', '')
    lines = pipeline_yaml.split('\n')
    
    # Show first 30 lines
    for i, line in enumerate(lines[:30], 1):
        print(f"{i:3d} | {line}")
    
    if len(lines) > 30:
        print(f"... | ({len(lines) - 30} more lines)")
    
    print("-"*70)
    
    # 7. Save output
    output_file = Path("generated_pipeline_simple.yaml")
    output_file.write_text(pipeline_yaml)
    print(f"\n💾 Full output saved to: {output_file}")
    
    # 8. Token usage
    usage = result.output_data.get('llm_usage', {})
    if usage:
        print(f"\n📊 Token Usage:")
        print(f"   Prompt: {usage.get('prompt_tokens', 0)}")
        print(f"   Completion: {usage.get('completion_tokens', 0)}")
        print(f"   Total: {usage.get('total_tokens', 0)}")
    
    # Summary
    print("\n" + "="*70)
    print("  ✅ Test Complete!")
    print("="*70)
    print(f"\n✓ Generated {len(lines)} lines of YAML")
    print(f"✓ Detected as: {result.output_data.get('pipeline_type')}")
    print(f"✓ Validated: {result.output_data.get('validation_result', {}).get('valid', False)}")
    print(f"\nNext steps:")
    print("  • Run: python examples/debug_pipeline_generator.py")
    print("  • See: examples/README_DEBUG.md")
    print()


if __name__ == "__main__":
    asyncio.run(main())
