# Requirements Submission Guide

## Overview

This guide helps you submit comprehensive, unambiguous requirements to the ConductorAI multi-agent framework. Use the templates provided to ensure all agents have the context needed for successful code generation, testing, deployment, and monitoring.

---

## Files in This Package

### 1. **project-requirements-template.yaml**
📄 **Location:** `/project-requirements-template.yaml`

A comprehensive YAML template covering all aspects of project requirements:
- Project metadata and stakeholders
- Functional and non-functional requirements
- Data models and schemas
- Sample/seed data
- Technology stack specifications
- Architecture and design patterns
- Monitoring, logging, and observability
- Cloud infrastructure configuration
- Deployment and CI/CD pipelines
- Key considerations and constraints
- Testing strategy
- Documentation requirements
- Success criteria

**When to use:** Complex projects requiring detailed specification

### 2. **prompt-template-guide.md**
📖 **Location:** `/docs/prompt-template-guide.md`

A detailed guide on writing unambiguous requirements with:
- Quick start templates for simple projects
- Section-by-section explanations
- Best practices and anti-patterns
- Complete example (Real-Time Trading Analytics Platform)
- Submission checklist

**When to use:** Learn how to write clear, measurable requirements

---

## Quick Start

### Option A: Simple Project (Use Prompt Template)

For straightforward projects, use the basic prompt structure from the guide:

```markdown
I need to build [PROJECT_TYPE] that [PRIMARY_PURPOSE].

**Core Requirements:**
- [Requirement 1]
- [Requirement 2]

**Technology Stack:**
- Language: [LANGUAGE & VERSION]
- Framework: [FRAMEWORK]
- Database: [DATABASE]

**Expected Output:**
- [Deliverable 1]
- [Deliverable 2]

**Constraints:**
- [Performance/Security requirement]
```

### Option B: Complex Project (Use YAML Template)

For comprehensive projects, fill out the YAML template:

1. **Copy the template:**
   ```bash
   cp project-requirements-template.yaml my-project-requirements.yaml
   ```

2. **Fill in all sections** (see guide for help)

3. **Validate completeness** using checklist in prompt-template-guide.md

4. **Submit** to ConductorAI framework

---

## Template Sections Explained

### 🎯 Essential Sections (Required for All Projects)

| Section | Purpose | Key Points |
|---------|---------|------------|
| **Project Metadata** | Identify project context | Name, domain, priority, deadline |
| **Functional Requirements** | What the system should do | Measurable acceptance criteria |
| **Technology Stack** | Languages, frameworks, tools | Specific versions required |
| **Expected Output** | Deliverables structure | Source code, deployable artifacts, docs |
| **Success Criteria** | How to measure completion | Objective, testable criteria |

### ⚙️ Important Sections (Recommended for Production)

| Section | Purpose | Key Points |
|---------|---------|------------|
| **Non-Functional Requirements** | Performance, security, scalability | Specific metrics (p95 < 300ms) |
| **Data Models** | API schemas, database tables | Include example valid/invalid data |
| **Architecture** | Design patterns, service boundaries | Explain pattern choices |
| **Monitoring** | Metrics, alerts, dashboards | Define thresholds and notifications |
| **Cloud Infrastructure** | Compute, storage, networking | Instance types, CIDR blocks, regions |
| **CI/CD** | Deployment pipeline | Stages, approval workflows, strategies |

### 🔍 Optional Sections (For Specialized Needs)

| Section | When to Include |
|---------|-----------------|
| **Sample Data** | Development/testing requires specific test cases |
| **Business Rules** | Complex domain logic or compliance requirements |
| **External Dependencies** | Integrations with third-party APIs |
| **Edge Cases** | High-reliability systems needing exhaustive error handling |

---

## Best Practices Summary

### ✅ DO

- **Use specific numbers:** "p95 < 300ms" not "fast"
- **Provide examples:** Show valid and invalid inputs
- **Define all terms:** "Active user = logged in within 30 days"
- **Specify versions:** "Python 3.11+" not "latest"
- **Include error scenarios:** What happens when things fail
- **Make criteria measurable:** "99.95% uptime over 30 days"

### ❌ DON'T

- **Avoid vague terms:** "robust", "user-friendly", "scalable"
- **Don't assume context:** Be explicit about everything
- **Don't skip edge cases:** Handle failures gracefully
- **Don't use ambiguous quantifiers:** "most", "some", "usually"
- **Don't leave dependencies unspecified:** Name versions, timeouts, fallbacks

---

## Submission Checklist

Before submitting requirements, verify:

- [ ] **Project purpose** is clearly stated with success metrics
- [ ] **All functional requirements** have measurable acceptance criteria
- [ ] **Non-functional requirements** include specific numbers
- [ ] **Data models** include example valid and invalid inputs
- [ ] **Technology stack** specifies exact versions
- [ ] **Architecture patterns** choices are explained
- [ ] **Monitoring** includes custom metrics and alert thresholds
- [ ] **Cloud infrastructure** specifies instance types and sizes
- [ ] **Edge cases** and error scenarios are documented
- [ ] **Security** and compliance requirements are explicit
- [ ] **Testing strategy** defines coverage thresholds
- [ ] **Success criteria** are objective and testable

---

## Examples by Complexity

### 🟢 Simple: REST API for Webhooks
**Template:** Use basic prompt from guide  
**Time to complete:** 15 minutes  
**Sections needed:** 5 (Metadata, Functional, Tech Stack, Output, Success)

### 🟡 Medium: Microservices E-commerce Platform
**Template:** Use YAML template  
**Time to complete:** 2-4 hours  
**Sections needed:** 10 (Add NFRs, Architecture, Monitoring, CI/CD, Testing)

### 🔴 Complex: Real-Time Trading Analytics Platform
**Template:** Use full YAML template  
**Time to complete:** 1-2 days  
**Sections needed:** All 15 sections (Full specification required)

---

## Common Mistakes to Avoid

### ❌ Mistake 1: Vague Performance Requirements
**Bad:** "The system should be fast and scalable"  
**Good:** "API p95 response time <300ms under 10,000 req/min load"

### ❌ Mistake 2: Missing Error Handling
**Bad:** "User can login"  
**Good:** "User can login. After 3 failed attempts, lock account for 15 minutes. Send email notification."

### ❌ Mistake 3: Unspecified Versions
**Bad:** "Use PostgreSQL database"  
**Good:** "Use PostgreSQL 15 with TimescaleDB 2.13 extension"

### ❌ Mistake 4: No Edge Cases
**Bad:** "Process payment via Stripe"  
**Good:** "Process payment via Stripe (10s timeout). If fails, retry 3x exponential backoff. If still fails, fallback to PayPal."

### ❌ Mistake 5: Unmeasurable Success Criteria
**Bad:** "System should be reliable"  
**Good:** "System achieves 99.95% uptime measured over 30-day rolling window"

---

## Getting Help

### Template Questions
- **Q:** Which sections are mandatory?
- **A:** At minimum: Metadata, Functional Requirements, Tech Stack, Expected Output, Success Criteria

### Requirement Clarification
- **Q:** How specific should I be?
- **A:** Specific enough that two developers would implement the same thing. Use the "two developers test"—if they might interpret differently, add more detail.

### Version Constraints
- **Q:** Should I specify exact versions or ranges?
- **A:** Use minimum version ranges (e.g., `>=0.110.0`) unless you know of breaking changes in newer versions.

### Architecture Decisions
- **Q:** Should I dictate the architecture or let agents decide?
- **A:** Specify high-level style (monolith vs microservices) and required patterns (e.g., circuit breaker), but let agents optimize implementation details.

---

## Next Steps

1. **Choose your template:**
   - Simple project → Use basic prompt from guide
   - Complex project → Use YAML template

2. **Fill in requirements:**
   - Start with essential sections
   - Add recommended sections for production
   - Include optional sections as needed

3. **Review checklist:**
   - Verify all items in submission checklist
   - Test with "two developers test" (would they build the same thing?)

4. **Submit to ConductorAI:**
   - Provide YAML file or structured prompt
   - Monitor agent progress through workflow
   - Review generated artifacts

5. **Iterate:**
   - Agents will highlight ambiguities
   - Refine requirements based on feedback
   - Update YAML for future reference

---

## Resources

- **Full YAML Template:** [project-requirements-template.yaml](../project-requirements-template.yaml)
- **Detailed Guide:** [prompt-template-guide.md](prompt-template-guide.md)
- **ConductorAI Docs:** [README.md](../readme.md)
- **Architecture Overview:** [architecture-overview.md](architecture-overview.md)

---

## Appendix: Quick Reference Card

### The 5 W's of Requirements

1. **WHAT:** What does the system do? (Functional requirements)
2. **WHO:** Who are the users? What are their roles? (User personas)
3. **WHEN:** When should actions complete? (Performance SLAs)
4. **WHERE:** Where is it deployed? (Cloud infrastructure)
5. **WHY:** Why this approach? (Architecture justification)

### The 3 M's of Good Requirements

1. **MEASURABLE:** Can you verify completion objectively?
2. **MINIMAL:** No unnecessary complexity or gold-plating
3. **MAINTAINABLE:** Can you update/extend in the future?

### The 2 T's of Validation

1. **TESTABLE:** Can you write automated tests?
2. **TRACEABLE:** Can you link code back to requirements?

---

**Version:** 1.0.0  
**Last Updated:** 2026-02-16  
**Maintained By:** ConductorAI Team
