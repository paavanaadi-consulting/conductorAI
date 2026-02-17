# Optimal Prompt Template for Unambiguous Requirements

## Overview

This guide provides the optimal prompt template for submitting unambiguous requirements to the ConductorAI multi-agent framework. Following this template ensures that all agents (Coding, Review, Testing, DevOps, Monitoring) have the context needed to generate, deploy, and maintain your application with minimal ambiguity.

---

## Quick Start

### Basic Prompt Structure

```
I need to build [PROJECT_TYPE] that [PRIMARY_PURPOSE].

**Core Requirements:**
- [Functional requirement 1]
- [Functional requirement 2]
- [Functional requirement 3]

**Technology Stack:**
- Language: [LANGUAGE & VERSION]
- Framework: [FRAMEWORK]
- Database: [DATABASE_TYPE]

**Expected Output:**
- [Deliverable 1]
- [Deliverable 2]

**Constraints:**
- [Performance/Security/Compliance requirement]
```

### Example: Simple Prompt

```
I need to build a REST API that processes payment webhooks from Stripe.

**Core Requirements:**
- Receive webhook POST requests at /api/webhooks/stripe
- Validate webhook signatures using Stripe's secret
- Store successful payments in PostgreSQL
- Send confirmation emails via SendGrid

**Technology Stack:**
- Language: Python 3.11
- Framework: FastAPI
- Database: PostgreSQL 15

**Expected Output:**
- Dockerized application
- Unit tests with 80%+ coverage
- OpenAPI documentation

**Constraints:**
- Process webhooks within 5 seconds
- Handle 1000 requests/minute
```

---

## Complete Prompt Template

For complex projects requiring comprehensive specification, use the following template:

### 1. Project Overview Section

```markdown
## PROJECT: [Project Name]

**Domain:** [e.g., Fintech, Healthcare, E-commerce, ML/AI]
**Priority:** [Low | Medium | High | Critical]
**Deadline:** [ISO 8601 date, e.g., 2026-06-30]

**Description:**
[2-3 paragraphs describing:
- What problem this solves
- Who the users are
- What value it provides
- Key success metrics]

**Example:**
I need to build a real-time trading analytics platform for cryptocurrency traders.
The system should ingest market data from multiple exchanges, apply technical 
indicators, and alert users when trading opportunities match their criteria.
Target users are individual traders managing portfolios of $10K-$500K.
Success is measured by <100ms data processing latency and 99.9% uptime.
```

### 2. Functional Requirements Section

```markdown
## FUNCTIONAL REQUIREMENTS

### Core Features

**Feature: [Feature Name]**
- **ID:** FEAT-001
- **Priority:** [Critical | High | Medium | Low]
- **Description:** [Detailed description of what this does]
- **User Story:** As a [user type], I want to [action] so that [benefit]
- **Acceptance Criteria:**
  - [ ] [Specific, testable criterion 1]
  - [ ] [Specific, testable criterion 2]
  - [ ] [Specific, testable criterion 3]

### API Endpoints (if applicable)

**Endpoint:** POST /api/v1/[resource]
- **Purpose:** [What this endpoint does]
- **Authentication:** [Required | Optional | None]
- **Request Body:**
  ```json
  {
    "field": "type (constraints)"
  }
  ```
- **Success Response:** [Status code + example]
- **Error Responses:** [List possible errors]
- **Rate Limit:** [e.g., 100 requests/minute per user]

### Business Rules

- **Rule:** [Clear statement of business rule]
- **Enforcement:** [How/where this is enforced]
- **Example:** User accounts must verify email within 24 hours or be suspended
```

**Best Practices for This Section:**
- ✅ Use measurable acceptance criteria (e.g., "Process in <5 seconds")
- ✅ Specify all edge cases (e.g., "What happens when payment fails?")
- ✅ Include example data for complex inputs
- ❌ Avoid vague terms like "fast," "user-friendly," "robust"
- ❌ Don't assume implied behavior—be explicit

---

### 3. Non-Functional Requirements Section

```markdown
## NON-FUNCTIONAL REQUIREMENTS

### Performance
- **Response Time:**
  - p50: [e.g., 100ms]
  - p95: [e.g., 300ms]
  - p99: [e.g., 500ms]
- **Throughput:** [e.g., 10,000 requests/minute]
- **Concurrent Users:** [e.g., 5,000 simultaneous users]

### Scalability
- **Horizontal Scaling:** [Yes/No]
- **Auto-scaling Trigger:** [e.g., CPU > 70% for 5 minutes]
- **Min/Max Instances:** [e.g., 2-20 instances]

### Reliability
- **Uptime SLA:** [e.g., 99.95%]
- **Error Rate Threshold:** [e.g., <0.1%]
- **Recovery Time Objective (RTO):** [e.g., 30 minutes]
- **Recovery Point Objective (RPO):** [e.g., 1 hour]

### Security
- **Authentication:** [e.g., OAuth2 + JWT]
- **Authorization:** [e.g., Role-Based Access Control]
- **Data Encryption:** [At rest: Yes/No, In transit: Yes/No]
- **Compliance:** [e.g., GDPR, SOC2, HIPAA]

### Availability
- **Multi-Region:** [Yes/No]
- **Disaster Recovery:** [Strategy description]
```

**Best Practices for This Section:**
- ✅ Provide specific numbers (not "fast" but "p95 < 300ms")
- ✅ Define thresholds for alerts (e.g., "Alert when error rate > 1%")
- ✅ Specify compliance requirements early
- ❌ Don't use relative terms ("better than," "faster than")

---

### 4. Data Models & Schemas Section

```markdown
## DATA MODELS

### API Schemas

**Schema: UserRegistration**
```json
{
  "email": "string (email format, required, max 255 chars)",
  "password": "string (min 12 chars, required, must contain uppercase/lowercase/number/symbol)",
  "full_name": "string (required, max 255 chars)",
  "age": "integer (min 18, required)",
  "phone": "string (E.164 format, optional)"
}
```

### Database Tables

**Table: users**
| Column | Type | Constraints | Index |
|--------|------|-------------|-------|
| id | UUID | PRIMARY KEY | Yes |
| email | VARCHAR(255) | UNIQUE, NOT NULL | Yes |
| password_hash | VARCHAR(255) | NOT NULL | No |
| full_name | VARCHAR(255) | NOT NULL | No |
| created_at | TIMESTAMP | DEFAULT NOW() | Yes |

**Relationships:**
- One user HAS MANY sessions (1:N)
- One user HAS MANY orders (1:N)

### Example Data

**Sample Valid Input:**
```json
{
  "email": "user@example.com",
  "password": "SecurePass123!",
  "full_name": "John Doe",
  "age": 25
}
```

**Sample Invalid Inputs (for testing):**
```json
[
  {"email": "invalid-email", "error": "Invalid email format"},
  {"age": 17, "error": "Must be 18 or older"},
  {"password": "short", "error": "Password too short"}
]
```
```

**Best Practices for This Section:**
- ✅ Show concrete examples of valid and invalid data
- ✅ Specify data formats (ISO 8601 dates, E.164 phone numbers)
- ✅ Define all validation rules explicitly
- ✅ Include edge cases (null, empty, very large values)
- ❌ Don't leave field types ambiguous

---

### 5. Technology Stack Section

```markdown
## TECHNOLOGY STACK

### Programming Language
- **Primary:** Python 3.11+
- **Secondary:** TypeScript 5.0+ (for frontend, if applicable)

### Frameworks & Libraries
- **Web Framework:** FastAPI >=0.110.0
- **ORM:** SQLAlchemy >=2.0.0
- **Task Queue:** Celery >=5.3.0
- **Testing:** pytest >=8.0.0, pytest-cov >=4.1.0
- **[Other key dependencies]**

### Databases
- **Primary Database:** PostgreSQL 15
  - Purpose: Transactional data
  - Connection pool: 20 connections
- **Cache:** Redis 7
  - Purpose: Session storage, caching
  - Max memory: 2GB

### Infrastructure
- **Container Orchestration:** Kubernetes 1.28 (AWS EKS)
- **Service Mesh:** Istio 1.20 (optional but recommended)
- **API Gateway:** Kong 3.5
- **Load Balancer:** Application Load Balancer (AWS ALB)

### Message Queue
- **Broker:** RabbitMQ 3.12
- **Queues:**
  - high_priority (durable)
  - default (durable)
  - low_priority (non-durable)
```

**Best Practices for This Section:**
- ✅ Specify exact versions or minimum version requirements
- ✅ Explain the purpose of each component
- ✅ Mention any version compatibility constraints
- ❌ Don't say "latest" without version constraints
- ❌ Don't omit critical infrastructure components

---

### 6. Architecture & Design Patterns Section

```markdown
## ARCHITECTURE & DESIGN PATTERNS

### Architectural Style
- **Style:** Microservices
- **Alternative:** [If considering multiple, explain why]

### Design Patterns to Implement

**Pattern: Facade**
- **Location:** src/api/facades/
- **Purpose:** Simplify complex external API integrations
- **Example:** PaymentFacade abstracts Stripe, PayPal, Square differences
- **Implementation:**
  ```python
  class PaymentFacade:
      def charge(amount: Decimal, source: str) -> PaymentResult:
          # Unified interface regardless of provider
          pass
  ```

**Pattern: Repository**
- **Location:** src/repositories/
- **Purpose:** Abstract data access from business logic
- **Example:** UserRepository for all user data operations

**Pattern: Circuit Breaker**
- **Location:** src/resilience/
- **Purpose:** Prevent cascading failures
- **Configuration:**
  - Failure threshold: 5 failures in 10 seconds
  - Open state duration: 30 seconds
  - Half-open test requests: 3

### Service Boundaries (for Microservices)

**Service: auth-service**
- **Responsibility:** Authentication and authorization
- **Database:** auth_db (PostgreSQL)
- **Endpoints:**
  - POST /api/v1/auth/login
  - POST /api/v1/auth/register
  - GET /api/v1/auth/verify
- **Dependencies:** None (foundational service)

**Service: order-service**
- **Responsibility:** Order processing and management
- **Database:** order_db (PostgreSQL)
- **Dependencies:**
  - auth-service (for user validation)
  - payment-service (for payment processing)
  - notification-service (for order confirmations)
```

**Best Practices for This Section:**
- ✅ Explain WHY each pattern is chosen
- ✅ Show concrete implementation examples
- ✅ Map patterns to specific code locations
- ✅ Define clear service boundaries with dependencies
- ❌ Don't just list patterns without context

---

### 7. Monitoring, Logging & Observability Section

```markdown
## MONITORING, LOGGING & OBSERVABILITY

### Metrics Collection
- **Provider:** Prometheus
- **Scrape Interval:** 15s
- **Retention:** 15 days

**Custom Metrics:**
1. **api_request_duration_seconds** (histogram)
   - Labels: method, endpoint, status_code
   - Buckets: 0.01, 0.05, 0.1, 0.5, 1.0, 5.0

2. **processing_jobs_total** (counter)
   - Labels: status (success/failure), priority
   
3. **active_connections_gauge** (gauge)
   - Labels: service_name

### Alerts

**Alert: HighErrorRate**
- **Condition:** error_rate > 1% for 5 minutes
- **Severity:** Critical
- **Notification:** PagerDuty + Slack #incidents
- **Runbook:** [Link to incident response doc]

**Alert: HighLatency**
- **Condition:** p95_latency > 500ms for 10 minutes
- **Severity:** Warning
- **Notification:** Slack #engineering
- **Auto-remediation:** Scale up by 2 instances

### Logging
- **Provider:** Elasticsearch (ELK stack)
- **Format:** JSON (structured logging)
- **Level:** INFO (DEBUG in development)
- **Retention:** 30 days

**Required Log Fields:**
```json
{
  "timestamp": "2026-02-16T10:00:00Z",
  "level": "INFO",
  "service": "auth-service",
  "trace_id": "abc123",
  "message": "User logged in",
  "user_id": "usr_123",
  "duration_ms": 45
}
```

### Distributed Tracing
- **Provider:** Jaeger
- **Sampling Rate:** 10% (all errors)
- **Instrumentation:**
  - All HTTP requests
  - Database queries
  - External API calls
  - Message queue operations

### Dashboards

**Dashboard: System Health (Grafana)**
- Panel: Request rate (RPS) - time series
- Panel: Error rate (%) - time series
- Panel: Latency (p50, p95, p99) - time series
- Panel: CPU usage by service - heatmap
- Panel: Active database connections - gauge
```

**Best Practices for This Section:**
- ✅ Define specific alert thresholds with durations
- ✅ Specify notification channels for each severity
- ✅ Include structured logging format examples
- ✅ Link alerts to runbooks
- ❌ Don't set up alerts without clear remediation steps

---

### 8. Cloud Infrastructure Section

```markdown
## CLOUD INFRASTRUCTURE

### Cloud Provider
- **Provider:** AWS
- **Primary Region:** us-east-1
- **Secondary Region:** us-west-2 (DR)

### Compute
**Kubernetes Cluster:**
- **Name:** production-cluster
- **Version:** 1.28
- **Node Groups:**
  - **general-purpose**
    - Instance: t3.large (2 vCPU, 8GB RAM)
    - Min: 3, Max: 10
    - Disk: 50GB gp3
  - **compute-optimized**
    - Instance: c6i.xlarge (4 vCPU, 8GB RAM)
    - Min: 2, Max: 20
    - Disk: 100GB gp3
    - Label: workload=processing

### Storage
**Block Storage (EBS):**
- Type: gp3
- IOPS: 3000
- Throughput: 125 MB/s

**Object Storage (S3):**
- **Bucket: app-data-prod**
  - Versioning: Enabled
  - Encryption: AES-256
  - Lifecycle: Move to Glacier after 90 days
  
### Networking
**VPC Configuration:**
- CIDR: 10.0.0.0/16
- **Public Subnets:**
  - 10.0.1.0/24 (us-east-1a)
  - 10.0.2.0/24 (us-east-1b)
- **Private Subnets:**
  - 10.0.10.0/24 (us-east-1a)
  - 10.0.11.0/24 (us-east-1b)

**Load Balancer:**
- Type: Application Load Balancer
- Scheme: Internet-facing
- SSL Policy: ELBSecurityPolicy-TLS-1-2-2017-01
- Health Check: /health/ready every 30s

### Security
**IAM Roles:**
- **app-service-role**
  - Policies: s3-read-write, secrets-manager-read, cloudwatch-write

**Secrets Management:**
- Provider: AWS Secrets Manager
- Rotation: 30 days (database creds), 90 days (API keys)

**Network Security:**
- Security Group: app-sg
  - Inbound: 443 (HTTPS) from 0.0.0.0/0
  - Inbound: 80 (HTTP) from 0.0.0.0/0 (redirects to HTTPS)
  - Outbound: All traffic

### Backup & Disaster Recovery
- **Database Backups:** Daily, 30-day retention
- **Cross-Region Replication:** Enabled to us-west-2
- **RTO:** 30 minutes
- **RPO:** 1 hour
```

**Best Practices for This Section:**
- ✅ Specify exact instance types and sizes
- ✅ Define network topology with CIDR blocks
- ✅ Include security configurations
- ✅ Specify backup schedules and retention
- ❌ Don't assume default configurations—be explicit

---

### 9. Deployment & CI/CD Section

```markdown
## DEPLOYMENT & CI/CD

### CI/CD Platform
- **Platform:** GitHub Actions
- **Trigger:** Push to main, pull requests

### Pipeline Stages

**Stage 1: Build & Lint**
- Checkout code
- Install dependencies (cache pip packages)
- Run ruff (linting)
- Run mypy (type checking)
- Build Docker image

**Stage 2: Test**
- Run pytest (unit + integration tests)
- Coverage threshold: 80%
- Security scan: bandit, safety
- Container scan: trivy

**Stage 3: Deploy to Staging**
- Environment: staging.company.com
- Deploy to Kubernetes (namespace: staging)
- Run smoke tests
- Run E2E tests (Playwright)

**Stage 4: Deploy to Production**
- **Requires:** Manual approval from tech-lead
- **Strategy:** Blue-Green deployment
- **Steps:**
  1. Deploy green environment
  2. Run smoke tests on green
  3. Switch traffic to green (10% → 50% → 100%)
  4. Monitor for 10 minutes
  5. If metrics good, tear down blue
  6. If metrics bad, rollback to blue

### Deployment Strategy
- **Type:** Blue-Green
- **Rollback:** Automatic if error rate > 1% for 5 minutes
- **Health Check Grace Period:** 60 seconds
- **Max Unavailable Pods:** 25%

### Environments

**Development:**
- URL: https://dev.company.com
- Auto-deploy: Yes (on push to develop branch)
- Database: Shared dev database

**Staging:**
- URL: https://staging.company.com
- Auto-deploy: Yes (on push to main branch)
- Database: Production-like dataset (anonymized)

**Production:**
- URL: https://api.company.com
- Auto-deploy: No (requires approval)
- Database: Production database
```

**Best Practices for This Section:**
- ✅ Define exact deployment strategy with steps
- ✅ Specify rollback criteria and automation
- ✅ Include approval workflows for production
- ✅ Define health check grace periods
- ❌ Don't skip smoke tests before production traffic

---

### 10. Key Considerations & Constraints Section

```markdown
## KEY CONSIDERATIONS & CONSTRAINTS

### Technical Constraints
- ⚠️ Must support offline mode (mobile app)
- ⚠️ API responses must be cacheable for 5 minutes
- ⚠️ Database migrations must be backward compatible
- ⚠️ Docker image size must not exceed 500MB
- ⚠️ Maximum cold start time: 3 seconds

### Performance Targets
- Database query time < 50ms (p95)
- Background job processing < 10 seconds
- File upload handling up to 100MB

### Compliance Requirements

**GDPR Compliance:**
- User data deletion within 30 days of request
- Data export in machine-readable format (JSON)
- Consent management for data processing
- Right to be forgotten implementation

**SOC2 Compliance:**
- Audit logs for all data access (immutable)
- Encryption at rest and in transit
- Access control reviews quarterly
- Incident response procedures documented

### External Dependencies

**Dependency: Stripe API**
- Purpose: Payment processing
- Timeout: 10 seconds
- Fallback: PayPal
- Rate Limit: 100 req/second
- SLA: 99.99%

**Dependency: SendGrid API**
- Purpose: Email delivery
- Timeout: 5 seconds
- Fallback: AWS SES
- Rate Limit: 600 emails/second (plan dependent)

### Edge Cases & Error Scenarios

**Scenario: Database connection pool exhausted**
- Detection: Connection timeout after 5 seconds
- Handling: Queue request, return 503 with Retry-After: 60
- Monitoring: Alert if pool >80% utilized for 5 minutes

**Scenario: External API rate limit exceeded**
- Detection: 429 response from external API
- Handling: Exponential backoff (1s, 2s, 4s, 8s)
- Fallback: Use cached data if available (<5 minutes old)

**Scenario: Invalid input data**
- Detection: Schema validation failure
- Handling: Return 422 with detailed error messages
- Example:
  ```json
  {
    "error": "Validation failed",
    "details": [
      {"field": "email", "message": "Invalid email format"},
      {"field": "age", "message": "Must be 18 or older"}
    ]
  }
  ```

### Operational Requirements
- ✅ Zero-downtime deployments required
- ✅ Database migrations < 5 minutes execution time
- ✅ Rollback capability within 2 minutes
- ✅ Automated health checks every 30 seconds
```

**Best Practices for This Section:**
- ✅ List all hard constraints upfront
- ✅ Define specific error handling for each edge case
- ✅ Specify timeouts, retries, and fallbacks
- ✅ Include compliance requirements with specific actions
- ❌ Don't leave edge cases unhandled

---

### 11. Testing Strategy Section

```markdown
## TESTING STRATEGY

### Test Coverage Requirements
- **Unit Tests:** 85% minimum
- **Integration Tests:** 70% minimum
- **E2E Tests:** Critical user paths only

### Test Types

**Unit Tests:**
- Framework: pytest
- Mocking: pytest-mock
- Coverage: pytest-cov
- Run on: Every commit

**Integration Tests:**
- Framework: pytest with testcontainers
- Scope: API endpoints, database interactions
- Database: Real PostgreSQL (via testcontainers)
- External APIs: Mocked (responses library)

**End-to-End Tests:**
- Framework: Playwright
- Browser: Chromium (headless)
- Critical Paths:
  - User registration → email verification → login
  - Create order → payment → confirmation email
  - Data upload → processing → download results

**Performance Tests:**
- Tool: Locust
- Scenarios:
  - **Normal Load:** 100 users, 10 req/s, 5 minutes
  - **Peak Load:** 1000 users, 100 req/s, 10 minutes
  - **Stress Test:** 5000 users, 500 req/s until failure
- Success Criteria:
  - p95 latency < 300ms under peak load
  - Zero errors under normal load
  - Graceful degradation under stress

**Security Tests:**
- **SAST:** bandit (Python security linter)
- **Dependency Scan:** safety check
- **Container Scan:** trivy
- **Penetration Test:** Annual third-party audit

### Test Data Management
- **Strategy:** Factory pattern (factory_boy)
- **Anonymization:** Required for production data
- **Fixtures:** Shared fixtures in tests/conftest.py
```

**Best Practices for This Section:**
- ✅ Define coverage thresholds per test type
- ✅ Specify performance test scenarios with criteria
- ✅ Include security testing in pipeline
- ❌ Don't skip integration tests to save time

---

### 12. Documentation Requirements Section

```markdown
## DOCUMENTATION REQUIREMENTS

### Required Documents

**API Documentation:**
- Format: OpenAPI 3.0 (auto-generated from code)
- Hosting: https://api.company.com/docs
- Interactive: Swagger UI
- Examples: Include request/response examples for all endpoints

**Architecture Documentation:**
- Format: Markdown with Mermaid diagrams
- Include:
  - System architecture diagram
  - Data flow diagrams
  - Deployment diagram
  - Sequence diagrams for critical workflows

**Runbook:**
- Format: Markdown
- Sections:
  - Deployment procedures
  - Incident response steps
  - Rollback procedures
  - Common troubleshooting
  - Contact information (on-call rotation)

**Developer Guide:**
- Format: Markdown
- Sections:
  - Local development setup
  - Code standards and conventions
  - Testing guide
  - Contribution guidelines
  - Git workflow (branch strategy)
```

---

### 13. Success Criteria Section

```markdown
## SUCCESS CRITERIA

### Technical Acceptance
- [ ] All unit tests pass with >85% coverage
- [ ] All integration tests pass with >70% coverage
- [ ] Zero critical or high security vulnerabilities
- [ ] API p95 response time <300ms under normal load
- [ ] System uptime >99.9% over 30-day period

### Performance Acceptance
- [ ] Handles 10,000 requests/minute without degradation
- [ ] Database queries <50ms (p95)
- [ ] Deployment completes in <10 minutes
- [ ] Rollback completes in <2 minutes

### Operational Readiness
- [ ] Monitoring dashboards configured in Grafana
- [ ] Critical alerts configured in PagerDuty
- [ ] Runbooks complete and tested
- [ ] Backup and restore procedures validated
- [ ] Security scans automated in CI/CD

### Business Acceptance
- [ ] All functional requirements implemented
- [ ] All edge cases handled
- [ ] User acceptance testing completed
- [ ] Compliance requirements validated (GDPR, SOC2)
```

---

## Tips for Writing Unambiguous Requirements

### DO's ✅

1. **Use Specific Numbers**
   - ✅ "Process requests in <300ms (p95)"
   - ❌ "Process requests quickly"

2. **Provide Examples**
   - ✅ Include valid and invalid input examples
   - ✅ Show expected outputs for edge cases

3. **Define All Terms**
   - ✅ "Active user = logged in within last 30 days"
   - ❌ Assume everyone knows what "active user" means

4. **Specify Versions**
   - ✅ "Python 3.11+", "PostgreSQL 15"
   - ❌ "Latest version"

5. **Include Error Scenarios**
   - ✅ "If payment fails, refund and notify user within 5 minutes"
   - ❌ "Handle payment failures"

6. **Measurable Acceptance Criteria**
   - ✅ "Uptime >99.95% measured over 30 days"
   - ❌ "High availability system"

### DON'Ts ❌

1. **Avoid Vague Terms**
   - ❌ "Fast", "user-friendly", "robust", "scalable"
   - ✅ Use concrete metrics instead

2. **Don't Assume Context**
   - ❌ "Standard authentication"
   - ✅ "OAuth2 with JWT tokens, 24-hour expiry"

3. **Don't Skip Edge Cases**
   - ❌ "User can log in"
   - ✅ "User can log in. After 3 failed attempts, account locked for 15 minutes."

4. **Don't Use Ambiguous Quantifiers**
   - ❌ "Most requests should be fast"
   - ✅ "95% of requests complete in <300ms"

5. **Don't Leave Dependencies Unspecified**
   - ❌ "Integrate with payment provider"
   - ✅ "Integrate with Stripe API v2023-10-16, fallback to PayPal"

---

## Example: Complete Unambiguous Prompt

```markdown
## PROJECT: Real-Time Trading Analytics Platform

**Domain:** Fintech
**Priority:** High
**Deadline:** 2026-08-01

**Description:**
Build a real-time cryptocurrency trading analytics platform that ingests
market data from 3 exchanges (Binance, Coinbase, Kraken), calculates 
technical indicators (RSI, MACD, Bollinger Bands), and sends alerts when
user-defined conditions are met. Target 1000 concurrent users, each 
monitoring 5-10 trading pairs. Success: <100ms indicator calculation,
99.9% uptime, <1% alert false positive rate.

---

## FUNCTIONAL REQUIREMENTS

### Core Features

**Feature: Market Data Ingestion**
- **ID:** FEAT-001
- **Priority:** Critical
- **Description:** Subscribe to WebSocket feeds from Binance, Coinbase, 
  Kraken and store OHLCV data every 1 second.
- **Acceptance Criteria:**
  - [ ] Connect to all 3 exchange WebSockets within 5 seconds of startup
  - [ ] Store data with <50ms latency from exchange timestamp
  - [ ] Handle disconnections with automatic reconnect (exponential backoff)
  - [ ] No data loss during reconnection (resume from last timestamp)

**Feature: Technical Indicator Calculation**
- **ID:** FEAT-002
- **Priority:** Critical
- **Description:** Calculate RSI(14), MACD(12,26,9), BB(20,2) for each pair
- **Acceptance Criteria:**
  - [ ] Calculate indicators within 100ms of receiving new data point
  - [ ] Handle missing data points (forward fill up to 10 seconds)
  - [ ] Store calculated values in TimescaleDB for historical analysis

**Feature: Alert System**
- **ID:** FEAT-003
- **Priority:** High
- **Description:** Notify users via webhook when conditions met
- **Acceptance Criteria:**
  - [ ] Evaluate conditions within 200ms of indicator calculation
  - [ ] Send webhook POST within 1 second of condition trigger
  - [ ] Retry failed webhooks 3 times (1s, 5s, 15s backoff)
  - [ ] Rate limit: Max 10 alerts per user per minute

---

## NON-FUNCTIONAL REQUIREMENTS

### Performance
- Response Time:
  - p50: 50ms (indicator calculation)
  - p95: 100ms
  - p99: 150ms
- WebSocket message processing: <10ms per message
- Throughput: 100,000 messages/second (across all pairs)

### Scalability
- Horizontal scaling: Yes
- Auto-scale trigger: CPU >70% for 2 minutes OR message queue depth >10,000
- Min/Max instances: 3-30

### Reliability
- Uptime SLA: 99.9%
- Error rate: <0.1%
- RTO: 15 minutes
- RPO: 0 (no data loss)

---

## DATA MODELS

**WebSocket Message Schema:**
```json
{
  "exchange": "binance",
  "pair": "BTC-USD",
  "timestamp": "2026-02-16T10:00:00.123Z",
  "open": 45000.50,
  "high": 45100.00,
  "low": 44950.00,
  "close": 45050.00,
  "volume": 123.456
}
```

**Database Table: ohlcv_data**
| Column | Type | Constraints |
|--------|------|-------------|
| id | BIGSERIAL | PRIMARY KEY |
| exchange | VARCHAR(20) | NOT NULL |
| pair | VARCHAR(20) | NOT NULL, INDEX |
| timestamp | TIMESTAMPTZ | NOT NULL, INDEX |
| open | DECIMAL(18,8) | NOT NULL |
| high | DECIMAL(18,8) | NOT NULL |
| low | DECIMAL(18,8) | NOT NULL |
| close | DECIMAL(18,8) | NOT NULL |
| volume | DECIMAL(18,8) | NOT NULL |

**Hypertable:** Partition by timestamp (1-day chunks)

---

## TECHNOLOGY STACK

- **Language:** Python 3.11
- **WebSocket:** websockets 12.0
- **Database:** TimescaleDB 2.13 (PostgreSQL 15)
- **Cache:** Redis 7 (for indicator lookups)
- **Message Queue:** Apache Kafka 3.6 (for data distribution)
- **Framework:** FastAPI 0.110.0 (for REST API)
- **Deployment:** Kubernetes 1.28 (AWS EKS)

---

## ARCHITECTURE

- **Style:** Event-Driven Microservices
- **Services:**
  1. **Ingestion Service:** WebSocket → Kafka
  2. **Calculation Service:** Kafka → Compute indicators → TimescaleDB + Redis
  3. **Alert Service:** Redis (condition eval) → Webhook delivery
  4. **API Service:** FastAPI (historical queries, user config)

**Design Patterns:**
- **Observer:** Alert conditions observe indicator streams
- **Repository:** Data access abstraction for TimescaleDB
- **Circuit Breaker:** Protect webhook delivery (open after 5 failures in 30s)

---

## MONITORING

**Metrics:**
- `ws_messages_received_total` (counter, labels: exchange, pair)
- `indicator_calculation_duration_seconds` (histogram, labels: indicator)
- `alert_delivery_success_total` (counter, labels: delivery_method)

**Alerts:**
- HighWebSocketLatency: ws_latency >500ms for 5 minutes → Slack
- IndicatorCalculationSlow: calc_duration >200ms for 10 minutes → PagerDuty
- KafkaConsumerLag: lag >10,000 messages for 5 minutes → PagerDuty

**Dashboards (Grafana):**
- Panel: Messages/second by exchange
- Panel: Indicator calculation latency (p50, p95, p99)
- Panel: Alert delivery success rate

---

## CLOUD INFRASTRUCTURE

- **Provider:** AWS
- **Region:** us-east-1 (primary), us-west-2 (DR)
- **Compute:** EKS cluster, c6i.2xlarge nodes (8 vCPU, 16GB)
- **Database:** RDS TimescaleDB r6g.xlarge (4 vCPU, 32GB)
- **Cache:** ElastiCache Redis r6g.large (2 vCPU, 13GB)
- **Message Queue:** MSK (Managed Kafka) kafka.m5.large

---

## SUCCESS CRITERIA

- [ ] Ingest data from all 3 exchanges with <50ms latency
- [ ] Calculate indicators in <100ms (p95)
- [ ] Deliver alerts within 1 second of trigger
- [ ] Handle 100,000 messages/second
- [ ] Achieve 99.9% uptime over 30 days
- [ ] Unit test coverage >85%
- [ ] Zero critical security vulnerabilities
```

---

## Checklist Before Submitting Requirements

- [ ] Project purpose and success metrics clearly defined
- [ ] All functional requirements have measurable acceptance criteria
- [ ] Non-functional requirements include specific numbers (not "fast")
- [ ] Data models include example valid and invalid inputs
- [ ] Technology stack specifies versions
- [ ] Architecture pattern choices are explained
- [ ] Monitoring includes custom metrics and alert thresholds
- [ ] Cloud infrastructure specifies instance types and sizes
- [ ] Edge cases and error scenarios are documented
- [ ] Security and compliance requirements are explicit
- [ ] Testing strategy defines coverage thresholds
- [ ] Success criteria are objective and testable

---

## Quick Reference: YAML Template

The complete YAML template is available at:
`/project-requirements-template.yaml`

Copy and fill in all sections to provide comprehensive, unambiguous requirements to the ConductorAI framework.
