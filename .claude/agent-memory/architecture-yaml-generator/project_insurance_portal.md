---
name: Insurance Portal Architecture YAML
description: Architecture.docx in D:\Learning\ConductorAI\Documents describes an Insurance Web Portal (general-project-infra.yaml template). Generated architecture.yaml at same location.
type: project
---

The architecture document at `D:\Learning\ConductorAI\Documents\Architecture.docx` describes an Insurance Web Portal — a general web application mapped to `general-project-infra.yaml`.

Generated output: `D:\Learning\ConductorAI\Documents\architecture.yaml`

**Why:** The portal is a microservices web application (Java/Spring Boot backend, ReactJS frontend, MySQL + PostgreSQL databases, Docker + Kubernetes deployment, Jenkins CI/CD, PySpark for data processing, OpenAI for agent bot, Power BI for reporting). It does not involve ETL pipelines or RAG/LLM retrieval patterns.

**How to apply:** If asked to regenerate or update this project's architecture YAML, use `general-project-infra.yaml` as the schema template and source content from `Architecture.docx`. The `infra_temp.yaml` in the same folder contains pre-derived microservice detail that can supplement the docx.
