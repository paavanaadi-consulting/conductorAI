# Pipeline YAML Generator - Debugging Guide

## Quick Start

### 1. **Basic Run** (Shows all steps with summaries)
```bash
cd /Users/ashokasangapallar/Desktop/studyrepos/tradingproject/conductorAI
source .venv/bin/activate
python examples/debug_pipeline_generator.py
```

### 2. **Interactive Mode** (Pause at each step)
```bash
python examples/debug_pipeline_generator.py --interactive
```
- Pauses after each step
- Press Enter to continue
- Great for learning the flow

### 3. **Verbose Mode** (Show all data)
```bash
python examples/debug_pipeline_generator.py --verbose
```
- Shows complete outputs (no truncation)
- Displays full prompts and responses
- Best for deep inspection

### 4. **Combined Mode** (Interactive + Verbose)
```bash
python examples/debug_pipeline_generator.py --interactive --verbose
```
- Most detailed debugging experience
- Pause and inspect everything

### 5. **No File Saving**
```bash
python examples/debug_pipeline_generator.py --no-save
```
- Doesn't create debug_output/ folder
- Good for quick runs

---

## What You'll See

The script traces **10 major steps**:

### **STEP 1: INITIALIZATION**
- Creates `ConductorConfig`
- Creates `MockLLMProvider` 
- Creates `PipelineYamlGeneratorAgent`
- Shows agent identity and status

### **STEP 2: AGENT STARTUP**
- Calls `agent.start()`
- Validates LLM provider
- Sets agent to IDLE status

### **STEP 3: INPUT VALIDATION & PARSING**
- Shows requirements YAML (business needs)
- Parses requirements to Python dict
- Shows infrastructure YAML (available services)
- Parses infrastructure to Python dict

### **STEP 4: PIPELINE TYPE AUTO-DETECTION**
- Lists all pipeline types and indicators
- Scores each type based on keyword matches
- Shows which keywords were found
- Determines winner and confidence %

### **STEP 5: SCHEMA SKELETON LOADING**
- Maps pipeline type to template file
- Loads full template (800-2300 lines)
- Extracts schema skeleton (~200 lines)
- Shows compression ratio

### **STEP 6: LLM PROMPT CONSTRUCTION**
- Builds system prompt (instructions for LLM)
- Builds user prompt (requirements + infra + schema)
- Shows required sections
- Displays full prompts (if --verbose)

### **STEP 7: LLM GENERATION**
- Calls LLM with prompts
- Shows token usage
- Displays raw response
- Strips markdown fences (```yaml```)

### **STEP 8: YAML VALIDATION**
- **Layer 1**: Checks YAML parsability
- **Layer 2**: Checks required sections
- **Layer 3**: Checks field types
- Shows validation report

### **STEP 9: REPAIR (IF NEEDED)**
- Only runs if validation fails
- Builds repair prompt
- Makes 2nd LLM call
- Re-validates repaired YAML

### **STEP 10: FINAL RESULT ASSEMBLY**
- Shows final pipeline YAML
- Displays metadata summary
- Assembles TaskResult structure

---

## Output Files

All intermediate files are saved to `debug_output/`:

| File | Description |
|------|-------------|
| `01_input_requirements.yaml` | Business requirements input |
| `02_input_infrastructure.yaml` | Infrastructure capabilities input |
| `03_full_template.yaml` | Full template (800+ lines) |
| `04_schema_skeleton.yaml` | Compressed schema (~200 lines) |
| `05_system_prompt.txt` | LLM system instructions |
| `06_user_prompt.txt` | User prompt (requirements + infra + schema) |
| `07_llm_raw_response.txt` | Raw LLM output (may have markdown fences) |
| `08_generated_yaml.yaml` | Cleaned generated YAML |
| `09_validation_report.json` | Validation results |
| `10_repair_prompt.txt` | Repair instructions (if needed) |
| `11_repaired_yaml.yaml` | Repaired YAML (if needed) |
| `12_final_pipeline.yaml` | **Final output** |
| `13_task_result.json` | Complete TaskResult metadata |

---

## Example Session Output

```
================================================================================
  🔍 PIPELINE YAML GENERATOR - STEP-BY-STEP DEBUG
================================================================================

This script traces EVERY step of the pipeline YAML generation process.
✓ Saving intermediate files to debug_output/

Tip: Use --interactive to pause at each step for inspection

================================================================================
  STEP 1: INITIALIZATION
================================================================================

1.1 Creating ConductorConfig...
  ✓ Environment: dev
  ✓ Log Level: INFO
  ✓ LLM Provider: mock
  ✓ LLM Model: gpt-4
  ✓ Max Tokens: 4096

1.2 Creating MockLLMProvider...
  ✓ Provider: mock
  ✓ Model: gpt-4
  ✓ Queued responses: 1

1.3 Creating PipelineYamlGeneratorAgent...
  ✓ Agent ID: pipeline-gen-debug-001
  ✓ Agent Type: AgentType.PIPELINE_GENERATOR
  ✓ Status: AgentStatus.IDLE
  ✓ Templates Dir: /path/to/templates

[... continues through all 10 steps ...]

================================================================================
  ✅ DEBUG SESSION COMPLETE
================================================================================

Summary:
  Pipeline Type: data_pipeline (confidence: 83%)
  Generation Stages: 1
  Final Status: ✓ Valid
  Output Length: 1847 characters

📁 All intermediate files saved to: debug_output/
   Files created:
     01_input_requirements.yaml
     02_input_infrastructure.yaml
     [... etc ...]
     12_final_pipeline.yaml
     13_task_result.json

🎉 You can now review all intermediate outputs to understand the process!
```

---

## Understanding the Flow

```
INPUT (30-60 lines)
    ↓
Parse YAMLs
    ↓
Detect Type → data_pipeline (83% confidence)
    ↓
Load Schema → 800 lines → 200 lines skeleton
    ↓
Build Prompts → System + User
    ↓
LLM Call #1 → Generate YAML (4000 tokens)
    ↓
Validate → ✓ Parseable, ✗ Missing sections
    ↓
LLM Call #2 → Repair (1500 tokens)
    ↓
Re-Validate → ✓ All sections OK
    ↓
OUTPUT (800-2300 lines)
```

---

## Debugging Tips

### 1. **Focus on Specific Steps**

Edit the script to comment out steps you don't need:

```python
# Skip steps 1-5, start from prompts
# await debug_step_1_initialization()
# ...
system_prompt, user_prompt = await debug_step_6_prompt_building(...)
```

### 2. **Modify Sample Data**

Change `SAMPLE_REQUIREMENTS` in the script to test different scenarios:
- Add/remove indicators → affects type detection
- Change cloud provider → affects infrastructure mapping
- Add invalid YAML → triggers repair

### 3. **Test Different Pipeline Types**

```python
# Force a specific type
task.input_data["pipeline_type"] = "ml_pipeline"  # Instead of "auto"
```

### 4. **Watch Token Usage**

Check `llm_usage` in the output to understand costs:
- Prompt tokens: How much context sent to LLM
- Completion tokens: How much LLM generated
- Stage 1 vs Stage 2 (repair) costs

### 5. **Compare Outputs**

Run multiple times with different inputs and compare:
```bash
python examples/debug_pipeline_generator.py
mv debug_output debug_output_run1
python examples/debug_pipeline_generator.py  # with modified SAMPLE_REQUIREMENTS
mv debug_output debug_output_run2
diff debug_output_run1/12_final_pipeline.yaml debug_output_run2/12_final_pipeline.yaml
```

---

## Troubleshooting

### "Template file not found"
- Make sure you're running from the project root
- Check that `templates/` directory exists
- Verify template files are present

### "Module not found"
- Activate virtual environment: `source .venv/bin/activate`
- Install dependencies: `pip install -e ".[dev]"`

### "No LLM response"
- Check MockLLMProvider has responses queued
- For real LLM: ensure API key is set

---

## Next Steps

After understanding the debug flow:

1. **Use Real LLM**: Replace `MockLLMProvider` with `OpenAIProvider` or `AnthropicProvider`
2. **Try Real Templates**: Use actual requirements from your projects
3. **Integrate with ConductorAI**: Run through the full facade API
4. **Test Edge Cases**: Invalid YAML, missing sections, contradictory requirements

Enjoy debugging! 🐛🔍
