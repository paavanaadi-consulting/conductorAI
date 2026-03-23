# Pipeline YAML Generator - Testing & Debugging Scripts

This folder contains scripts to help you understand how the PipelineYamlGeneratorAgent works.

## 🎯 Which Script Should I Run?

### **Just Getting Started?** → Run this first
```bash
python examples/simple_pipeline_test.py
```
- Clean, simple output
- Shows the basic flow
- Takes ~5 seconds
- See what the agent produces

### **Want to Learn the Details?** → Run this next
```bash
python examples/debug_pipeline_generator.py
```
- Complete step-by-step trace
- Shows all 10 stages
- Saves 13 intermediate files
- Takes ~10 seconds

### **Need Deep Inspection?** → Run with options
```bash
python examples/debug_pipeline_generator.py --interactive --verbose
```
- Pauses at each step
- Shows full data (no truncation)
- Best for learning the internals

---

## 📚 Available Scripts

| Script | Purpose | Time | Output Files |
|--------|---------|------|--------------|
| `simple_pipeline_test.py` | Quick test run | 5s | 1 file |
| `debug_pipeline_generator.py` | Full debugging | 10s | 13 files |
| `debug_pipeline_generator.py --interactive` | Interactive learning | User-paced | 13 files |
| `debug_pipeline_generator.py --verbose` | Deep inspection | 15s | 13 files |

---

## 🚀 Quick Start

```bash
# 1. Activate virtual environment
cd /Users/ashokasangapallar/Desktop/studyrepos/tradingproject/conductorAI
source .venv/bin/activate

# 2. Run simple test
python examples/simple_pipeline_test.py

# Output:
# ======================================================================
#   Simple Pipeline YAML Generator Test
# ======================================================================
# 
# 1️⃣  Setting up...
#    ✓ Agent created
# 
# 2️⃣  Starting agent...
#    ✓ Status: idle
# 
# 3️⃣  Creating task...
#    ✓ Task: Generate Sales Analytics Pipeline
# 
# 4️⃣  Executing task...
#    ✓ Status: completed
#    ✓ Duration: 0.003s
# 
# 5️⃣  Results:
#    Pipeline Type: data_pipeline
#    Confidence: 67%
#    Validation: ✓ Valid
#    Sections: 7
#    Generation Stages: 1
# 
# [... Generated YAML shown here ...]
```

---

## 📖 Learning Path

### **Level 1: Basic Understanding**
1. Run `simple_pipeline_test.py`
2. Review generated YAML
3. Understand inputs → outputs

### **Level 2: Process Flow**
1. Run `debug_pipeline_generator.py`
2. Review `debug_output/` files
3. See 10 stages in action

### **Level 3: Deep Dive**
1. Run with `--interactive --verbose`
2. Pause at each step
3. Inspect all intermediate data
4. Modify `SAMPLE_REQUIREMENTS` and re-run

### **Level 4: Custom Testing**
1. Edit test data in scripts
2. Try different pipeline types
3. Test edge cases
4. Use real LLM providers

---

## 🔍 What Each Stage Does

When you run the debug script, you'll see these **10 stages**:

```
STAGE 1: INITIALIZATION
  └─ Create config, LLM provider, agent

STAGE 2: AGENT STARTUP  
  └─ Start agent, validate LLM

STAGE 3: INPUT VALIDATION
  └─ Parse requirements & infrastructure YAMLs

STAGE 4: TYPE DETECTION
  └─ Auto-detect pipeline type (scores each type)

STAGE 5: SCHEMA LOADING
  └─ Load template, extract skeleton (800→200 lines)

STAGE 6: PROMPT BUILDING
  └─ Build system + user prompts for LLM

STAGE 7: LLM GENERATION
  └─ Call LLM, get YAML response

STAGE 8: VALIDATION
  └─ 3-layer validation (parse, sections, types)

STAGE 9: REPAIR (optional)
  └─ If invalid, make 2nd LLM call to fix

STAGE 10: FINAL RESULT
  └─ Assemble complete TaskResult
```

---

## 📁 Debug Output Files

Running `debug_pipeline_generator.py` creates these files in `debug_output/`:

| File | Stage | Description |
|------|-------|-------------|
| `01_input_requirements.yaml` | 3 | Business requirements input |
| `02_input_infrastructure.yaml` | 3 | Infrastructure capabilities |
| `03_full_template.yaml` | 5 | Full template (800-2300 lines) |
| `04_schema_skeleton.yaml` | 5 | Compressed schema (~200 lines) |
| `05_system_prompt.txt` | 6 | LLM system instructions |
| `06_user_prompt.txt` | 6 | Complete user prompt |
| `07_llm_raw_response.txt` | 7 | Raw LLM output |
| `08_generated_yaml.yaml` | 7 | Cleaned YAML |
| `09_validation_report.json` | 8 | Validation results |
| `10_repair_prompt.txt` | 9 | Repair instructions (if needed) |
| `11_repaired_yaml.yaml` | 9 | Fixed YAML (if needed) |
| `12_final_pipeline.yaml` | 10 | **Final output** ⭐ |
| `13_task_result.json` | 10 | Complete metadata |

---

## 💡 Command Line Options

### `simple_pipeline_test.py`
No options - just runs.

### `debug_pipeline_generator.py`

| Option | Effect |
|--------|--------|
| (none) | Standard debug with summaries |
| `--interactive` | Pause at each step for inspection |
| `--verbose` | Show full data (no truncation) |
| `--no-save` | Don't create debug_output/ files |
| `--interactive --verbose` | Most detailed mode |

**Examples:**
```bash
# Standard debugging
python examples/debug_pipeline_generator.py

# Interactive learning mode
python examples/debug_pipeline_generator.py --interactive

# See everything
python examples/debug_pipeline_generator.py --verbose

# Pause and see everything
python examples/debug_pipeline_generator.py --interactive --verbose

# Quick run without files
python examples/debug_pipeline_generator.py --no-save
```

---

## 🛠️ Customization

### Change Test Data

Edit the sample data in the scripts:

**In `simple_pipeline_test.py`:**
```python
REQUIREMENTS = """
project_name: "your-project"
# ... your requirements ...
"""
```

**In `debug_pipeline_generator.py`:**
```python
SAMPLE_REQUIREMENTS = """
# ... your requirements ...
"""
```

### Test Different Pipeline Types

Force a specific type:
```python
task.input_data["pipeline_type"] = "ml_pipeline"  # Instead of "auto"
```

Available types:
- `data_pipeline` - ETL/data pipelines
- `ml_pipeline` - ML workflows
- `rag_llm` - RAG applications
- `agentic_ops` - Multi-agent systems
- `integration` - Legacy migrations
- `general` - Generic projects

### Use Real LLM

Replace `MockLLMProvider`:

```python
from conductor.integrations.llm.factory import create_llm_provider

# OpenAI
llm_provider = create_llm_provider(
    provider_name="openai",
    api_key="your-key",
    model="gpt-4"
)

# Anthropic
llm_provider = create_llm_provider(
    provider_name="anthropic",
    api_key="your-key",
    model="claude-3-sonnet-20240229"
)
```

---

## 🐛 Troubleshooting

### "ModuleNotFoundError"
```bash
# Make sure you're in the right directory
cd /Users/ashokasangapallar/Desktop/studyrepos/tradingproject/conductorAI

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"
```

### "Template file not found"
- Run from project root (not from examples/)
- Check that `templates/` directory exists

### "No output files created"
- Check you didn't use `--no-save`
- Check write permissions
- Look for `debug_output/` in current directory

---

## 📚 Additional Resources

- [Full Documentation](../docs/day-13-pipeline-yaml-generator.md)
- [Debug Guide](README_DEBUG.md)
- [Pipeline YAML to ZIP](../docs/pipeline-yaml-to-zip.md)
- [Tests](../tests/test_agents/test_pipeline/)

---

## 🎓 Next Steps

After running these scripts:

1. **Understand the flow**: Run debug script and review outputs
2. **Modify inputs**: Change requirements and see how output changes
3. **Test edge cases**: Invalid YAML, missing data, conflicting requirements
4. **Integrate**: Use the agent in full ConductorAI workflows
5. **Production**: Switch to real LLM providers and templates

Happy debugging! 🚀
