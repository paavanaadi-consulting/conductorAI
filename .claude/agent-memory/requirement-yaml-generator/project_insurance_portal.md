---
name: Insurance Portal Application
description: Web-based insurance management portal with CRUD, RBAC, virtual assistant, and monthly reporting; requirement.yaml generated from Business Document.docx
type: project
---

The user requested generation of a requirement.yaml for the Insurance Portal Application.

**Source document**: `D:\Learning\ConductorAI\Documents\Business Document.docx`
**Output file**: `D:\Learning\ConductorAI\Documents\requirement.yaml`
**Template used**: `general-project-requirements.yaml` (general web application template)

**Why general-project-requirements.yaml**: The project is a web portal with role-based authentication (Admin, Employee, Customer), CRUD operations for policies/claims/users, a virtual assistant (Agent Bot), and monthly reporting. It is NOT a data pipeline or a pure RAG/document-Q&A system.

**Key project facts**:
- Domain: insurance
- User roles: Admin (full access), Employee (operational), Customer (self-service)
- Core features: user auth, policy management, claims submission and processing, policy renewal, ratings/feedback, virtual assistant, monthly reporting
- Out of scope (initial release): third-party integrations, fraud detection, real-time notifications (SMS/email), mobile app
- 11 use cases documented (UC-01 through UC-11)
- 8 risks identified (R-01 through R-08)
- 4 constraints documented (time, resource, budget, data availability)
- Technology stack preferences: Python / FastAPI / PostgreSQL
- YAML validated with Python yaml.safe_load — no syntax errors

**Top-level YAML keys generated** (beyond the base template):
  user_roles, use_cases, risks, constraints, out_of_scope
  (extended from the base general-project-requirements.yaml template)

**How to apply**: If the user asks to update or extend this requirement.yaml, start from the existing file at the output path above rather than regenerating from scratch.
