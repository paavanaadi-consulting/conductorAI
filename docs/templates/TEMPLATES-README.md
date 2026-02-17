# Requirements Templates - Quick Reference

## 📁 All Available Templates

### Core Templates
1. **[General Project Requirements](project-requirements-template.yaml)** - Web apps, APIs, microservices
2. **[Data Pipeline Requirements](data-pipeline-requirements-template.yaml)** - ETL/ELT, streaming, data lakes
3. **[AI/ML Requirements](ai-ml-requirements-template.yaml)** - ML models, training, MLOps
4. **[ML Pipeline Requirements](ml-pipeline-requirements-template.yaml)** - Points to AI/ML template
5. **[Agentic Ops Requirements](agentic-ops-pipeline-template.yaml)** - Autonomous agents, multi-agent systems
6. **[RAG & LLM Requirements](rag-llm-pipeline-template.yaml)** - RAG systems, LLM apps, knowledge assistants
7. **[Pipeline Integration Requirements](pipeline-integration-template.yaml)** - Legacy migration, platform consolidation

### Documentation
- **[Pipeline Templates Guide](docs/pipeline-templates-guide.md)** - Comprehensive guide to choosing and using templates
- **[Prompt Template Guide](docs/prompt-template-guide.md)** - How to write unambiguous requirements
- **[Requirements Submission Guide](docs/requirements-submission-guide.md)** - Quick reference for submitting requirements

### Examples
- **[Sample Project: Payment Webhook API](examples/sample-project-requirements.yaml)** - Complete example

---

## 🎯 Which Template Should I Use?

**Building a web application or API?**
→ [project-requirements-template.yaml](project-requirements-template.yaml)

**Processing data (ETL, streaming, data warehouse)?**
→ [data-pipeline-requirements-template.yaml](data-pipeline-requirements-template.yaml)

**Training ML models or building MLOps?**
→ [ai-ml-requirements-template.yaml](ai-ml-requirements-template.yaml)

**Building RAG system or LLM application?**
→ [rag-llm-pipeline-template.yaml](rag-llm-pipeline-template.yaml)

**Building autonomous agent systems?**
→ [agentic-ops-pipeline-template.yaml](agentic-ops-pipeline-template.yaml)

**Integrating/migrating existing pipelines?**
→ [pipeline-integration-template.yaml](pipeline-integration-template.yaml)

**Not sure?**
→ Read [docs/pipeline-templates-guide.md](docs/pipeline-templates-guide.md)

---

## 🚀 Quick Start

1. **Choose your template** from the list above
2. **Copy the template file**
   ```bash
   cp <template-name>.yaml my-project-requirements.yaml
   ```
3. **Fill in all sections** (see guides in docs/)
4. **Validate completeness** using checklist in prompt-template-guide.md
5. **Submit to ConductorAI** framework

---

## 📊 Template Comparison

| Template | Best For | Key Features |
|----------|----------|--------------|
| **General Project** | Web apps, APIs, microservices | Architecture patterns, cloud infra, CI/CD |
| **Data Pipeline** | ETL/ELT, data lakes | Data sources, transformations, quality checks |
| **AI/ML** | ML models, MLOps | Training, deployment, monitoring, retraining |
| **Agentic Ops** | Autonomous agents | Multi-agent orchestration, LLM decisions |
| **RAG/LLM** | Knowledge assistants | Vector DB, retrieval, LLM integration |
| **Integration** | Legacy migration | Current state, migration strategy, rollback |

---

## 📖 Detailed Documentation

For comprehensive guidance on using these templates, see:

- **[Pipeline Templates Guide](docs/pipeline-templates-guide.md)** - 2000+ lines covering:
  - Template selection decision tree
  - Use case examples
  - Quick start guides
  - Best practices

- **[Prompt Template Guide](docs/prompt-template-guide.md)** - How to write requirements:
  - Section-by-section explanations
  - DO's and DON'Ts
  - Common mistakes
  - Complete examples

- **[Requirements Submission Guide](docs/requirements-submission-guide.md)** - Quick reference:
  - Checklist before submission
  - The 5 W's, 3 M's, 2 T's
  - Common questions

---

**Need help?** Open an issue or check the guides above.
