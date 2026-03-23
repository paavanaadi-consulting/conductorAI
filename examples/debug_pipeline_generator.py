"""
Debug Pipeline YAML Generator - Step-by-Step Execution Trace
==============================================================

This script provides comprehensive debugging for the PipelineYamlGeneratorAgent.
It traces EVERY step of the process with detailed logging and inspection points.

Usage:
    python examples/debug_pipeline_generator.py
    
    Or with interactive mode (pauses at each step):
    python examples/debug_pipeline_generator.py --interactive
    
    Or with verbose output:
    python examples/debug_pipeline_generator.py --verbose
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import yaml

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from conductor.agents.pipeline import PipelineYamlGeneratorAgent
from conductor.agents.pipeline.schema_extractor import (
    REQUIRED_SECTIONS,
    TEMPLATE_FILES,
    extract_schema_skeleton,
    load_template_schema,
)
from conductor.agents.pipeline.validators import (
    strip_markdown_fences,
    validate_pipeline_yaml,
)
from conductor.core.config import ConductorConfig
from conductor.core.enums import AgentType
from conductor.core.models import TaskDefinition
from conductor.integrations.llm.mock import MockLLMProvider


# =============================================================================
# Debug Configuration
# =============================================================================
class DebugConfig:
    """Configuration for debugging verbosity and behavior."""
    
    def __init__(self):
        self.interactive = False  # Pause at each step?
        self.verbose = False      # Show detailed data?
        self.save_outputs = True  # Save intermediate files?
        self.show_prompts = True  # Display LLM prompts?
        

DEBUG = DebugConfig()


# =============================================================================
# Debug Utilities
# =============================================================================
def print_header(title: str, level: int = 1) -> None:
    """Print a formatted section header."""
    if level == 1:
        print("\n" + "=" * 80)
        print(f"  {title}")
        print("=" * 80)
    elif level == 2:
        print("\n" + "-" * 80)
        print(f"  {title}")
        print("-" * 80)
    else:
        print(f"\n>>> {title}")


def print_data(label: str, data: Any, max_lines: int = 20) -> None:
    """Print data with optional truncation."""
    print(f"\n{label}:")
    
    if isinstance(data, (dict, list)):
        formatted = json.dumps(data, indent=2)
    elif isinstance(data, str):
        formatted = data
    else:
        formatted = str(data)
    
    lines = formatted.split('\n')
    
    if DEBUG.verbose or len(lines) <= max_lines:
        print(formatted)
    else:
        print('\n'.join(lines[:max_lines]))
        print(f"\n... ({len(lines) - max_lines} more lines, use --verbose to see all)")


def pause_for_inspection(message: str = "Press Enter to continue...") -> None:
    """Pause execution for user inspection (if interactive mode)."""
    if DEBUG.interactive:
        input(f"\n🔍 {message}")


def save_debug_file(filename: str, content: str) -> None:
    """Save intermediate output to debug/ folder."""
    if DEBUG.save_outputs:
        debug_dir = Path("debug_output")
        debug_dir.mkdir(exist_ok=True)
        filepath = debug_dir / filename
        filepath.write_text(content)
        print(f"  💾 Saved to: {filepath}")


# =============================================================================
# Sample Test Data
# =============================================================================
SAMPLE_REQUIREMENTS = """
project_name: "customer-360-analytics"
team: "data-engineering"
contact_email: "data-team@example.com"
priority: "high"
target_date: "2026-06-30"

description: |
  Build a unified customer analytics pipeline that consolidates data
  from multiple sources into a single data warehouse.

pipeline_type: "batch"
architecture: "medallion"

sources:
  - name: "Salesforce CRM"
    type: "api"
    technology: "REST API"
    update_frequency: "daily"
    estimated_volume: "500K records/day"
    
  - name: "PostgreSQL Transactions DB"
    type: "database"
    technology: "PostgreSQL"
    update_frequency: "hourly"
    estimated_volume: "2M records/day"

destination:
  target: "Snowflake"
  format: "parquet"
  partitioning: "by date and region"

quality_requirements:
  freshness: "Data available within 1 hour"
  accuracy: ">= 99%"
  completeness: "No null values in required fields"
  deduplication: true

schedule:
  batch_frequency: "daily at 2AM UTC"
  sla: "Data available by 7 AM UTC"

consumers:
  - team: "Marketing"
    use_case: "Customer segmentation"
    data_needed: ["demographics", "purchase_history"]
  
  - team: "Analytics"
    use_case: "Revenue forecasting"
    data_needed: ["transactions", "customer_lifetime_value"]

preferences:
  orchestrator: "airflow"
  processing_engine: "dbt"
  cloud_provider: "aws"

compliance:
  regulations: ["GDPR", "SOC2"]
  pii_handling: "mask"
  retention_period: "7 years"
  lineage_required: true

success_criteria:
  - "All batch jobs complete within SLA window"
  - ">= 99% data quality score"
  - "Zero data loss incidents"
"""

SAMPLE_INFRASTRUCTURE = """
cloud_provider: "aws"
region: "us-east-1"
environment: "production"

compute:
  available_services:
    - "ec2"
    - "eks"
    - "lambda"
  default_instance_type: "t3.large"
  max_cluster_size: 10

storage:
  available_services:
    - "s3"
    - "rds"
    - "dynamodb"
  s3_buckets:
    raw: "s3://acme-raw-data"
    processed: "s3://acme-processed-data"
    archive: "s3://acme-archive"

data_warehouse:
  platform: "snowflake"
  clusters:
    - name: "compute_wh"
      size: "large"
    - name: "analytics_wh"
      size: "medium"
  databases:
    - "production"
    - "development"
    - "analytics"

orchestration:
  tool: "airflow"
  version: "2.8.0"
  executor: "kubernetes"
  
data_quality:
  tools:
    - "great_expectations"
    - "deequ"

monitoring:
  tools:
    - "datadog"
    - "grafana"
  alerts_channel: "slack"

networking:
  vpc_id: "vpc-12345"
  subnets:
    - "subnet-abc123"
    - "subnet-def456"
  security_groups:
    - "sg-data-pipeline"

compliance:
  encryption_required: true
  audit_logging: true
  approved_regions: ["us-east-1", "us-west-2"]
"""

MOCK_LLM_RESPONSE = """
project:
  name: "customer-360-analytics-pipeline"
  version: "1.0.0"
  description: "Unified customer analytics data pipeline"
  team: "data-engineering"
  contact: "data-team@example.com"
  priority: "high"
  target_date: "2026-06-30"

business_requirements:
  objective: "Consolidate customer data from multiple sources"
  stakeholders:
    - team: "Marketing"
      needs: "Customer segmentation data"
    - team: "Analytics"  
      needs: "Revenue forecasting data"
  success_criteria:
    - "Data freshness < 1 hour"
    - "Data quality >= 99%"
    - "Zero data loss"

data_sources:
  - name: "salesforce_crm"
    type: "rest_api"
    connection:
      url: "https://api.salesforce.com/v1"
      auth_method: "oauth2"
    schedule: "daily at 2AM UTC"
    estimated_volume: "500K records/day"
    
  - name: "postgres_transactions"
    type: "database"
    connection:
      host: "prod-db.internal"
      port: 5432
      database: "transactions"
    schedule: "hourly"
    estimated_volume: "2M records/day"

transformations:
  architecture: "medallion"
  layers:
    bronze:
      description: "Raw ingestion layer"
      location: "s3://acme-raw-data/bronze/"
      format: "parquet"
    silver:
      description: "Cleaned and validated"
      location: "s3://acme-processed-data/silver/"
      format: "parquet"
    gold:
      description: "Business-ready aggregates"
      location: "s3://acme-processed-data/gold/"
      format: "parquet"
  tools:
    - "dbt"
  quality_checks:
    - "no nulls in required fields"
    - "deduplication"
    - "schema validation"

orchestration:
  tool: "airflow"
  version: "2.8.0"
  executor: "kubernetes"
  dag_schedule: "0 2 * * *"
  sla: "5 hours"
  retry_policy:
    retries: 3
    delay: "5 min"

storage:
  warehouse: "snowflake"
  cluster: "compute_wh"
  database: "production"
  schema: "customer_360"
  retention: "7 years"

monitoring:
  tools:
    - "datadog"
    - "grafana"
  alerts:
    - type: "sla_breach"
      threshold: "1 hour"
      channel: "slack"
    - type: "quality_failure"
      threshold: "99%"
      channel: "slack"
  dashboards:
    - "Pipeline Health"
    - "Data Quality Metrics"

success_criteria:
  - metric: "batch_completion_time"
    target: "< 5 hours"
  - metric: "data_quality_score"
    target: ">= 99%"
  - metric: "data_loss_incidents"
    target: "0"
"""


# =============================================================================
# Step-by-Step Debugging Functions
# =============================================================================

async def debug_step_1_initialization():
    """Step 1: Initialize configuration and components."""
    print_header("STEP 1: INITIALIZATION", level=1)
    
    print("\n1.1 Creating ConductorConfig...")
    config = ConductorConfig()
    print(f"  ✓ Environment: {config.environment}")
    print(f"  ✓ Log Level: {config.log_level}")
    print(f"  ✓ LLM Provider: {config.llm.provider}")
    print(f"  ✓ LLM Model: {config.llm.model}")
    print(f"  ✓ Max Tokens: {config.llm.max_tokens}")
    pause_for_inspection("Configuration created. Inspect config object.")
    
    print("\n1.2 Creating MockLLMProvider...")
    llm_provider = MockLLMProvider(responses=[MOCK_LLM_RESPONSE])
    print(f"  ✓ Provider: {llm_provider.provider_name}")
    print(f"  ✓ Model: {llm_provider.model}")
    print(f"  ✓ Queued responses: {len(llm_provider._responses)}")
    pause_for_inspection("LLM Provider created.")
    
    print("\n1.3 Creating PipelineYamlGeneratorAgent...")
    agent = PipelineYamlGeneratorAgent(
        agent_id="pipeline-gen-debug-001",
        config=config,
        llm_provider=llm_provider,
        name="Pipeline Generator (Debug Mode)"
    )
    print(f"  ✓ Agent ID: {agent.agent_id}")
    print(f"  ✓ Agent Type: {agent.agent_type}")
    print(f"  ✓ Status: {agent.status}")
    print(f"  ✓ Templates Dir: {agent.templates_dir}")
    pause_for_inspection("Agent created.")
    
    return config, llm_provider, agent


async def debug_step_2_agent_startup(agent):
    """Step 2: Start the agent."""
    print_header("STEP 2: AGENT STARTUP", level=1)
    
    print("\n2.1 Calling agent.start()...")
    await agent.start()
    print(f"  ✓ Agent Status: {agent.status}")
    print(f"  ✓ Agent Identity: {agent.identity}")
    pause_for_inspection("Agent started and ready.")
    
    return agent


async def debug_step_3_input_validation(requirements_yaml, infra_yaml):
    """Step 3: Validate and parse input YAMLs."""
    print_header("STEP 3: INPUT VALIDATION & PARSING", level=1)
    
    print("\n3.1 Input Requirements YAML...")
    print_data("Requirements", requirements_yaml, max_lines=15)
    save_debug_file("01_input_requirements.yaml", requirements_yaml)
    pause_for_inspection("Review requirements YAML.")
    
    print("\n3.2 Parsing Requirements YAML...")
    try:
        requirements = yaml.safe_load(requirements_yaml)
        print(f"  ✓ Parsed successfully")
        print(f"  ✓ Type: {type(requirements).__name__}")
        print(f"  ✓ Top-level keys: {list(requirements.keys())}")
        print_data("Parsed Requirements", requirements, max_lines=10)
    except Exception as e:
        print(f"  ✗ Parse failed: {e}")
        return None, None
    pause_for_inspection("Requirements parsed.")
    
    print("\n3.3 Input Infrastructure YAML...")
    print_data("Infrastructure", infra_yaml, max_lines=15)
    save_debug_file("02_input_infrastructure.yaml", infra_yaml)
    pause_for_inspection("Review infrastructure YAML.")
    
    print("\n3.4 Parsing Infrastructure YAML...")
    try:
        infrastructure = yaml.safe_load(infra_yaml)
        print(f"  ✓ Parsed successfully")
        print(f"  ✓ Type: {type(infrastructure).__name__}")
        print(f"  ✓ Top-level keys: {list(infrastructure.keys())}")
        print_data("Parsed Infrastructure", infrastructure, max_lines=10)
    except Exception as e:
        print(f"  ✗ Parse failed: {e}")
        return None, None
    pause_for_inspection("Infrastructure parsed.")
    
    return requirements, infrastructure


async def debug_step_4_type_detection(requirements):
    """Step 4: Auto-detect pipeline type."""
    print_header("STEP 4: PIPELINE TYPE AUTO-DETECTION", level=1)
    
    print("\n4.1 Available Pipeline Types:")
    from conductor.agents.pipeline.pipeline_yaml_generator import PIPELINE_TYPE_INDICATORS
    for ptype, indicators in PIPELINE_TYPE_INDICATORS.items():
        print(f"  - {ptype}: {len(indicators)} indicators")
        if DEBUG.verbose:
            print(f"    Indicators: {', '.join(indicators)}")
    pause_for_inspection("Review pipeline types.")
    
    print("\n4.2 Scoring Each Pipeline Type...")
    from conductor.agents.pipeline.pipeline_yaml_generator import (
        PIPELINE_TYPE_INDICATORS,
        PIPELINE_TYPE_VALUES
    )
    
    scores = {}
    for ptype, indicators in PIPELINE_TYPE_INDICATORS.items():
        score = 0.0
        matches = []
        
        for key in indicators:
            if key in requirements:
                score += 1.0
                matches.append(key)
                
                # Bonus for value matches
                value_map = PIPELINE_TYPE_VALUES.get(ptype, {})
                if key in value_map:
                    val = requirements[key]
                    if isinstance(val, str) and val in value_map[key]:
                        score += 0.5
                        matches.append(f"{key}={val} (bonus)")
        
        scores[ptype] = score
        print(f"\n  {ptype}:")
        print(f"    Score: {score}")
        print(f"    Matches: {matches if matches else 'None'}")
    
    pause_for_inspection("Review scoring results.")
    
    print("\n4.3 Determining Winner...")
    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]
    total_indicators = len(PIPELINE_TYPE_INDICATORS.get(best_type, []))
    confidence = min(best_score / max(total_indicators, 1), 1.0)
    
    print(f"  ✓ Winner: {best_type}")
    print(f"  ✓ Score: {best_score} / {total_indicators}")
    print(f"  ✓ Confidence: {confidence:.2%}")
    
    pause_for_inspection("Pipeline type detected.")
    
    return best_type, confidence


async def debug_step_5_schema_loading(pipeline_type, templates_dir):
    """Step 5: Load template schema skeleton."""
    print_header("STEP 5: SCHEMA SKELETON LOADING", level=1)
    
    print("\n5.1 Template File Mapping...")
    print(f"  Pipeline Type: {pipeline_type}")
    template_file = TEMPLATE_FILES.get(pipeline_type, "project-requirements-template.yaml")
    print(f"  Template File: {template_file}")
    template_path = templates_dir / template_file
    print(f"  Full Path: {template_path}")
    print(f"  File Exists: {template_path.exists()}")
    pause_for_inspection("Template file identified.")
    
    if not template_path.exists():
        print(f"\n  ⚠️  Template file not found! Using empty schema.")
        return ""
    
    print("\n5.2 Loading Full Template...")
    with open(template_path) as f:
        full_template = f.read()
    print(f"  ✓ Template loaded: {len(full_template)} characters")
    print(f"  ✓ Lines: {len(full_template.split(chr(10)))}")
    save_debug_file("03_full_template.yaml", full_template)
    pause_for_inspection("Full template loaded.")
    
    print("\n5.3 Parsing Template YAML...")
    template_data = yaml.safe_load(full_template)
    print(f"  ✓ Parsed successfully")
    print(f"  ✓ Top-level sections: {list(template_data.keys())}")
    pause_for_inspection("Template parsed.")
    
    print("\n5.4 Extracting Schema Skeleton...")
    schema_skeleton_data = extract_schema_skeleton(template_data, max_depth=3)
    schema_skeleton = yaml.dump(schema_skeleton_data, default_flow_style=False, sort_keys=False)
    print(f"  ✓ Schema extracted: {len(schema_skeleton)} characters")
    print(f"  ✓ Compression ratio: {len(full_template)} → {len(schema_skeleton)} ({len(schema_skeleton)/len(full_template):.1%})")
    print_data("Schema Skeleton", schema_skeleton, max_lines=30)
    save_debug_file("04_schema_skeleton.yaml", schema_skeleton)
    pause_for_inspection("Schema skeleton extracted.")
    
    return schema_skeleton


async def debug_step_6_prompt_building(requirements_yaml, infra_yaml, schema_skeleton, pipeline_type):
    """Step 6: Build LLM prompts."""
    print_header("STEP 6: LLM PROMPT CONSTRUCTION", level=1)
    
    print("\n6.1 Building System Prompt...")
    from conductor.agents.pipeline.pipeline_yaml_generator import (
        BASE_SYSTEM_PROMPT,
        TYPE_SPECIFIC_ADDENDA
    )
    
    system_prompt = PipelineYamlGeneratorAgent._build_system_prompt(pipeline_type)
    print(f"  ✓ Length: {len(system_prompt)} characters")
    print(f"  ✓ Contains base prompt: {BASE_SYSTEM_PROMPT[:50] in system_prompt}")
    print(f"  ✓ Pipeline type: {pipeline_type}")
    
    if DEBUG.show_prompts:
        print_data("System Prompt", system_prompt, max_lines=25)
    save_debug_file("05_system_prompt.txt", system_prompt)
    pause_for_inspection("System prompt built.")
    
    print("\n6.2 Building User Prompt...")
    user_prompt = PipelineYamlGeneratorAgent._build_user_prompt(
        requirements_yaml, infra_yaml, schema_skeleton, pipeline_type
    )
    print(f"  ✓ Length: {len(user_prompt)} characters")
    print(f"  ✓ Contains requirements: {'BUSINESS REQUIREMENTS' in user_prompt}")
    print(f"  ✓ Contains infrastructure: {'AVAILABLE INFRASTRUCTURE' in user_prompt}")
    print(f"  ✓ Contains schema: {'EXPECTED OUTPUT SCHEMA' in user_prompt}")
    print(f"  ✓ Contains required sections: {'REQUIRED SECTIONS' in user_prompt}")
    
    if DEBUG.show_prompts:
        print_data("User Prompt", user_prompt, max_lines=40)
    save_debug_file("06_user_prompt.txt", user_prompt)
    pause_for_inspection("User prompt built.")
    
    print("\n6.3 Required Sections for this Pipeline Type...")
    required = REQUIRED_SECTIONS.get(pipeline_type, [])
    print(f"  Required sections ({len(required)}): {', '.join(required)}")
    pause_for_inspection("Prompts ready for LLM.")
    
    return system_prompt, user_prompt


async def debug_step_7_llm_generation(agent, system_prompt, user_prompt):
    """Step 7: LLM generation."""
    print_header("STEP 7: LLM GENERATION", level=1)
    
    print("\n7.1 LLM Configuration...")
    print(f"  Provider: {agent.llm_provider.provider_name}")
    print(f"  Model: {agent.llm_provider.model}")
    print(f"  Temperature: 0.1 (deterministic)")
    print(f"  Max Tokens: {agent._config.llm.max_tokens}")
    pause_for_inspection("About to call LLM...")
    
    print("\n7.2 Calling LLM Provider...")
    llm_response = await agent.llm_provider.generate_with_system(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.1,
        max_tokens=agent._config.llm.max_tokens,
    )
    print(f"  ✓ Response received")
    print(f"  ✓ Model: {llm_response.model}")
    print(f"  ✓ Content length: {len(llm_response.content)} characters")
    
    if llm_response.usage:
        print(f"  ✓ Prompt tokens: {llm_response.usage.prompt_tokens}")
        print(f"  ✓ Completion tokens: {llm_response.usage.completion_tokens}")
        print(f"  ✓ Total tokens: {llm_response.usage.total_tokens}")
    
    pause_for_inspection("LLM response received.")
    
    print("\n7.3 Raw LLM Response...")
    print_data("Raw Response", llm_response.content, max_lines=40)
    save_debug_file("07_llm_raw_response.txt", llm_response.content)
    pause_for_inspection("Review raw LLM output.")
    
    print("\n7.4 Stripping Markdown Fences...")
    generated_yaml = strip_markdown_fences(llm_response.content)
    has_fences = generated_yaml != llm_response.content
    print(f"  Markdown fences found: {has_fences}")
    print(f"  ✓ Cleaned YAML length: {len(generated_yaml)} characters")
    print_data("Generated YAML", generated_yaml, max_lines=40)
    save_debug_file("08_generated_yaml.yaml", generated_yaml)
    pause_for_inspection("YAML cleaned and ready.")
    
    return generated_yaml, llm_response


async def debug_step_8_validation(generated_yaml, pipeline_type):
    """Step 8: Validate generated YAML."""
    print_header("STEP 8: YAML VALIDATION", level=1)
    
    print("\n8.1 Validation Layer 1: YAML Parsability...")
    try:
        parsed = yaml.safe_load(generated_yaml)
        print(f"  ✓ YAML is parseable")
        print(f"  ✓ Type: {type(parsed).__name__}")
        is_dict = isinstance(parsed, dict)
        print(f"  ✓ Is dict: {is_dict}")
    except Exception as e:
        print(f"  ✗ Parse failed: {e}")
        parsed = None
    pause_for_inspection("Parsability check complete.")
    
    print("\n8.2 Validation Layer 2: Required Sections...")
    required_sections = REQUIRED_SECTIONS.get(pipeline_type, [])
    print(f"  Required for {pipeline_type}: {required_sections}")
    
    if parsed and isinstance(parsed, dict):
        found = list(parsed.keys())
        missing = [s for s in required_sections if s not in found]
        print(f"  ✓ Sections found ({len(found)}): {found}")
        print(f"  ✗ Sections missing ({len(missing)}): {missing if missing else 'None'}")
    else:
        found = []
        missing = required_sections
        print(f"  ✗ Cannot check sections (not a valid dict)")
    pause_for_inspection("Section check complete.")
    
    print("\n8.3 Validation Layer 3: Field Types...")
    warnings = []
    if parsed and isinstance(parsed, dict):
        # Check project.name
        if "project" in parsed and isinstance(parsed["project"], dict):
            if "name" in parsed["project"]:
                if not isinstance(parsed["project"]["name"], str) or not parsed["project"]["name"]:
                    warnings.append("project.name should be non-empty string")
            if "version" in parsed["project"]:
                if not isinstance(parsed["project"]["version"], str):
                    warnings.append("project.version should be string")
        
        # Check monitoring
        if "monitoring" in parsed and not isinstance(parsed["monitoring"], dict):
            warnings.append("monitoring should be dict")
        
        # Check success_criteria
        if "success_criteria" in parsed and not isinstance(parsed["success_criteria"], (dict, list)):
            warnings.append("success_criteria should be dict or list")
    
    if warnings:
        print(f"  ⚠️  Warnings ({len(warnings)}):")
        for w in warnings:
            print(f"    - {w}")
    else:
        print(f"  ✓ No type warnings")
    pause_for_inspection("Field type check complete.")
    
    print("\n8.4 Full Validation Result...")
    validation = validate_pipeline_yaml(generated_yaml, pipeline_type)
    print(f"  Valid: {validation['valid']}")
    print(f"  Errors: {validation['errors'] if validation['errors'] else 'None'}")
    print(f"  Warnings: {validation['warnings'] if validation['warnings'] else 'None'}")
    print(f"  Sections found: {validation['sections_found']}")
    print(f"  Sections missing: {validation['sections_missing'] if validation['sections_missing'] else 'None'}")
    
    print_data("Full Validation Report", validation, max_lines=20)
    save_debug_file("09_validation_report.json", json.dumps(validation, indent=2, default=str))
    pause_for_inspection("Validation complete.")
    
    return validation


async def debug_step_9_repair_if_needed(agent, generated_yaml, validation, requirements_yaml, pipeline_type):
    """Step 9: Repair YAML if needed."""
    print_header("STEP 9: REPAIR (IF NEEDED)", level=1)
    
    needs_repair = not validation["valid"] and validation["parsed_data"] is not None
    
    if not needs_repair:
        print("\n✓ No repair needed - YAML is valid!")
        return generated_yaml, 1, {}
    
    print(f"\n⚠️  Repair needed!")
    print(f"  Reason: Missing sections: {validation['sections_missing']}")
    pause_for_inspection("Preparing repair...")
    
    print("\n9.1 Building Repair Prompt...")
    from conductor.agents.pipeline.pipeline_yaml_generator import REPAIR_SYSTEM_PROMPT
    
    repair_user_prompt = (
        f"The following pipeline YAML is missing these required sections: "
        f"{validation['sections_missing']}\n\n"
        f"Here is the current YAML:\n{generated_yaml}\n\n"
        f"Here are the original requirements for context:\n{requirements_yaml}\n\n"
        f"Add the missing sections with realistic values."
    )
    
    print(f"  ✓ Repair prompt length: {len(repair_user_prompt)} characters")
    if DEBUG.show_prompts:
        print_data("Repair User Prompt", repair_user_prompt, max_lines=30)
    save_debug_file("10_repair_prompt.txt", repair_user_prompt)
    pause_for_inspection("Repair prompt built.")
    
    print("\n9.2 Calling LLM for Repair...")
    repair_response = await agent.llm_provider.generate_with_system(
        system_prompt=REPAIR_SYSTEM_PROMPT,
        user_prompt=repair_user_prompt,
        temperature=0.1,
        max_tokens=agent._config.llm.max_tokens,
    )
    print(f"  ✓ Repair response received")
    print(f"  ✓ Length: {len(repair_response.content)} characters")
    
    if repair_response.usage:
        print(f"  ✓ Prompt tokens: {repair_response.usage.prompt_tokens}")
        print(f"  ✓ Completion tokens: {repair_response.usage.completion_tokens}")
    
    pause_for_inspection("Repair response received.")
    
    print("\n9.3 Processing Repaired YAML...")
    repaired_yaml = strip_markdown_fences(repair_response.content)
    print_data("Repaired YAML", repaired_yaml, max_lines=40)
    save_debug_file("11_repaired_yaml.yaml", repaired_yaml)
    pause_for_inspection("Repaired YAML extracted.")
    
    print("\n9.4 Re-validating Repaired YAML...")
    revalidation = validate_pipeline_yaml(repaired_yaml, pipeline_type)
    print(f"  Valid: {revalidation['valid']}")
    print(f"  Errors: {revalidation['errors'] if revalidation['errors'] else 'None'}")
    print(f"  Sections missing: {revalidation['sections_missing'] if revalidation['sections_missing'] else 'None'}")
    
    if revalidation['valid']:
        print("\n  ✓ Repair successful!")
        final_yaml = repaired_yaml
    else:
        print("\n  ✗ Repair failed, using original YAML")
        final_yaml = generated_yaml
    
    pause_for_inspection("Repair process complete.")
    
    return final_yaml, 2, repair_response.usage.model_dump() if repair_response.usage else {}


async def debug_step_10_final_result(final_yaml, pipeline_type, confidence, validation, stages, llm_usage):
    """Step 10: Assemble final result."""
    print_header("STEP 10: FINAL RESULT ASSEMBLY", level=1)
    
    print("\n10.1 Final Pipeline YAML...")
    print(f"  ✓ Length: {len(final_yaml)} characters")
    print(f"  ✓ Lines: {len(final_yaml.split(chr(10)))}")
    print_data("Final YAML", final_yaml, max_lines=50)
    save_debug_file("12_final_pipeline.yaml", final_yaml)
    pause_for_inspection("Final YAML ready.")
    
    print("\n10.2 Metadata Summary...")
    print(f"  Pipeline Type: {pipeline_type}")
    print(f"  Detection Confidence: {confidence:.2%}")
    print(f"  Generation Stages: {stages}")
    print(f"  Validation Status: {'✓ Valid' if validation['valid'] else '✗ Invalid'}")
    print(f"  Sections Generated: {len(validation['sections_found'])}")
    print(f"  Total Tokens Used: {llm_usage.get('total_tokens', 'N/A')}")
    
    print("\n10.3 TaskResult Structure...")
    result_output = {
        "pipeline_yaml": final_yaml,
        "pipeline_type": pipeline_type,
        "pipeline_type_confidence": confidence,
        "sections_generated": validation.get("sections_found", []),
        "validation_result": {k: v for k, v in validation.items() if k != "parsed_data"},
        "decisions_summary": f"Generated {pipeline_type} pipeline specification",
        "llm_usage": llm_usage,
        "generation_stages": stages,
    }
    
    print_data("Result Output", result_output, max_lines=30)
    save_debug_file("13_task_result.json", json.dumps(result_output, indent=2, default=str))
    pause_for_inspection("Final result assembled.")
    
    return result_output


# =============================================================================
# Main Debugging Flow
# =============================================================================

async def main():
    """Run the complete debugging session."""
    print_header("🔍 PIPELINE YAML GENERATOR - STEP-BY-STEP DEBUG", level=1)
    print("\nThis script traces EVERY step of the pipeline YAML generation process.")
    
    # Parse command line args
    if "--interactive" in sys.argv:
        DEBUG.interactive = True
        print("✓ Interactive mode: Will pause at each step")
    
    if "--verbose" in sys.argv:
        DEBUG.verbose = True
        print("✓ Verbose mode: Showing all data")
    
    if "--no-save" in sys.argv:
        DEBUG.save_outputs = False
        print("✓ Not saving intermediate files")
    else:
        print("✓ Saving intermediate files to debug_output/")
    
    if not DEBUG.interactive:
        print("\nTip: Use --interactive to pause at each step for inspection")
    
    pause_for_inspection("Ready to begin? Press Enter to start...")
    
    try:
        # Step 1: Initialize
        config, llm_provider, agent = await debug_step_1_initialization()
        
        # Step 2: Start agent
        agent = await debug_step_2_agent_startup(agent)
        
        # Step 3: Input validation
        requirements, infrastructure = await debug_step_3_input_validation(
            SAMPLE_REQUIREMENTS, SAMPLE_INFRASTRUCTURE
        )
        
        if requirements is None or infrastructure is None:
            print("\n❌ Input validation failed. Stopping.")
            return
        
        # Step 4: Type detection
        pipeline_type, confidence = await debug_step_4_type_detection(requirements)
        
        # Step 5: Schema loading
        schema_skeleton = await debug_step_5_schema_loading(pipeline_type, agent.templates_dir)
        
        # Step 6: Prompt building
        system_prompt, user_prompt = await debug_step_6_prompt_building(
            SAMPLE_REQUIREMENTS, SAMPLE_INFRASTRUCTURE, schema_skeleton, pipeline_type
        )
        
        # Step 7: LLM generation
        generated_yaml, llm_response = await debug_step_7_llm_generation(
            agent, system_prompt, user_prompt
        )
        
        # Step 8: Validation
        validation = await debug_step_8_validation(generated_yaml, pipeline_type)
        
        # Step 9: Repair if needed
        final_yaml, stages, repair_usage = await debug_step_9_repair_if_needed(
            agent, generated_yaml, validation, SAMPLE_REQUIREMENTS, pipeline_type
        )
        
        # Accumulate token usage
        total_usage = llm_response.usage.model_dump() if llm_response.usage else {}
        if repair_usage:
            total_usage = {
                "prompt_tokens": total_usage.get("prompt_tokens", 0) + repair_usage.get("prompt_tokens", 0),
                "completion_tokens": total_usage.get("completion_tokens", 0) + repair_usage.get("completion_tokens", 0),
                "total_tokens": total_usage.get("total_tokens", 0) + repair_usage.get("total_tokens", 0),
            }
        
        # Step 10: Final result
        result_output = await debug_step_10_final_result(
            final_yaml, pipeline_type, confidence, validation, stages, total_usage
        )
        
        # Summary
        print_header("✅ DEBUG SESSION COMPLETE", level=1)
        print("\nSummary:")
        print(f"  Pipeline Type: {pipeline_type} (confidence: {confidence:.2%})")
        print(f"  Generation Stages: {stages}")
        print(f"  Final Status: {'✓ Valid' if validation['valid'] else '✗ Invalid'}")
        print(f"  Output Length: {len(final_yaml)} characters")
        
        if DEBUG.save_outputs:
            print(f"\n📁 All intermediate files saved to: debug_output/")
            print("   Files created:")
            print("     01_input_requirements.yaml")
            print("     02_input_infrastructure.yaml")
            print("     03_full_template.yaml")
            print("     04_schema_skeleton.yaml")
            print("     05_system_prompt.txt")
            print("     06_user_prompt.txt")
            print("     07_llm_raw_response.txt")
            print("     08_generated_yaml.yaml")
            print("     09_validation_report.json")
            if stages > 1:
                print("     10_repair_prompt.txt")
                print("     11_repaired_yaml.yaml")
            print("     12_final_pipeline.yaml")
            print("     13_task_result.json")
        
        print("\n🎉 You can now review all intermediate outputs to understand the process!")
        
    except Exception as e:
        print_header("❌ ERROR OCCURRED", level=1)
        print(f"\nError: {e}")
        import traceback
        print("\nFull traceback:")
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
