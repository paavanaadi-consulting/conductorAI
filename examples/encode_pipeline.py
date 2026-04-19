import requests
import base64

content = """
project:
  name: Insurance Web Portal
  version: "1.0.0"
  description: A comprehensive insurance web portal with microservices architecture supporting admin, employee, and customer user roles for managing policies, claims, and user accounts
  domain: Insurance Technology
  priority: High
  deadline: "2024-06-30"
  stakeholders:
    product_owner: Sarah Johnson
    tech_lead: Michael Chen
    team: Insurance Portal Development Team

functional_requirements:
  features:
    - id: F001
      name: User Management
      description: Complete user lifecycle management with role-based access control
      priority: High
      acceptance_criteria:
        - Admin can create, update, and delete users
        - Support for three distinct user roles (Admin, Employee, Customer)
        - Users can view and manage their own profile information
        - Role-based permissions are enforced across all operations
    - id: F002
      name: Policy Management
      description: Insurance policy creation, renewal, and cancellation capabilities
      priority: High
      acceptance_criteria:
        - Employees can create and manage insurance policies
        - Customers can view their own policies
        - Policy renewal and cancellation workflows
        - Policy document generation and storage
    - id: F003
      name: Claims Processing
      description: End-to-end claims submission and processing workflow
      priority: High
      acceptance_criteria:
        - Customers can submit insurance claims
        - Employees can process and update claim status
        - Claims tracking and status notifications
        - Document upload and management for claims
    - id: F004
      name: Reporting and Analytics
      description: Business intelligence and reporting capabilities
      priority: Medium
      acceptance_criteria:
        - Generate claims, policy, and user reports
        - Revenue and performance analytics
        - Exportable reports in multiple formats
        - Real-time dashboard views
  api_endpoints:
    - path: /api/users
      method: POST
      description: Create a new user account
      request_body:
        email: string
        password: string
        full_name: string
        role: string
        phone: string
      response:
        user_id: string
        email: string
        full_name: string
        role: string
        created_at: string
    - path: /api/users/{id}
      method: GET
      description: Retrieve user details by ID
      request_body: {}
      response:
        user_id: string
        email: string
        full_name: string
        role: string
        phone: string
        last_login: string
    - path: /api/policies
      method: POST
      description: Create a new insurance policy
      request_body:
        customer_id: string
        policy_type: string
        coverage_amount: number
        premium: number
        start_date: string
        end_date: string
      response:
        policy_id: string
        policy_number: string
        status: string
        created_at: string
    - path: /api/claims
      method: POST
      description: Submit a new insurance claim
      request_body:
        policy_id: string
        claim_type: string
        incident_date: string
        description: string
        amount_claimed: number
        documents: array
      response:
        claim_id: string
        claim_number: string
        status: string
        submitted_at: string
  business_rules:
    - rule: Only admins can manage user accounts
      enforcement: API Gateway JWT validation with role-based access control
    - rule: Customers can only view their own policies and claims
      enforcement: Database queries filtered by customer ID from JWT token
    - rule: Claims must be submitted within 30 days of incident
      enforcement: Business logic validation in claims service

non_functional_requirements:
  performance:
    response_time:
      api_endpoints: "< 500ms"
      page_load: "< 2s"
      database_queries: "< 200ms"
    throughput: "1000 requests per second"
    concurrent_users: 5000
  scalability:
    horizontal_scaling: true
    min_instances: 2
    max_instances: 10
    scale_up_threshold: "70% CPU utilization"
    scale_down_threshold: "30% CPU utilization"
  availability:
    uptime_sla: "99.9%"
    rpo: "1 hour"
    rto: "30 minutes"
    multi_region: false
  security:
    authentication: "JWT with Spring Security"
    authorization: "Role-based access control (RBAC)"
    encryption_at_rest: true
    encryption_in_transit: true
    security_scanning: true
    compliance_standards:
      - SOC 2 Type II
      - PCI DSS
      - GDPR
  reliability:
    error_rate_threshold: "< 0.1%"
    circuit_breaker: true
    retry_policy:
      max_attempts: 3
      backoff_strategy: exponential
      initial_delay: "1s"
    health_checks:
      endpoint: "/actuator/health"
      interval: "30s"
      timeout: "5s"

data_models:
  schemas:
    CreateUserRequest:
      type: object
      properties:
        email:
          type: string
          format: email
        password:
          type: string
          minLength: 8
        full_name:
          type: string
          minLength: 2
        role:
          type: string
          enum: [admin, employee, customer]
        phone:
          type: string
          pattern: "^\\+?[1-9]\\d{1,14}$"
    UserResponse:
      type: object
      properties:
        user_id:
          type: string
          format: uuid
        email:
          type: string
          format: email
        full_name:
          type: string
        role:
          type: string
        created_at:
          type: string
          format: date-time
    DataProcessRequest:
      type: object
      properties:
        operation:
          type: string
          enum: [create, update, delete]
        entity_type:
          type: string
        data:
          type: object
  database_tables:
    - name: users
      type: transactional
      columns:
        - name: user_id
          type: VARCHAR(36)
          constraints: PRIMARY KEY
        - name: email
          type: VARCHAR(255)
          constraints: UNIQUE NOT NULL
        - name: password_hash
          type: VARCHAR(255)
          constraints: NOT NULL
        - name: full_name
          type: VARCHAR(255)
          constraints: NOT NULL
        - name: role
          type: ENUM('admin', 'employee', 'customer')
          constraints: NOT NULL
        - name: phone
          type: VARCHAR(20)
          constraints: NULL
        - name: created_at
          type: TIMESTAMP
          constraints: DEFAULT CURRENT_TIMESTAMP
        - name: updated_at
          type: TIMESTAMP
          constraints: DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    - name: policies
      type: transactional
      columns:
        - name: policy_id
          type: VARCHAR(36)
          constraints: PRIMARY KEY
        - name: policy_number
          type: VARCHAR(50)
          constraints: UNIQUE NOT NULL
        - name: customer_id
          type: VARCHAR(36)
          constraints: FOREIGN KEY REFERENCES users(user_id)
        - name: policy_type
          type: VARCHAR(100)
          constraints: NOT NULL
        - name: coverage_amount
          type: DECIMAL(15,2)
          constraints: NOT NULL
        - name: premium
          type: DECIMAL(10,2)
          constraints: NOT NULL
        - name: start_date
          type: DATE
          constraints: NOT NULL
        - name: end_date
          type: DATE
          constraints: NOT NULL
        - name: status
          type: ENUM('active', 'expired', 'cancelled')
          constraints: DEFAULT 'active'

sample_data:
  test_users:
    - email: admin@insurance.com
      password: AdminPass123!
      full_name: System Administrator
      age: 35
    - email: employee@insurance.com
      password: EmpPass123!
      full_name: John Employee
      age: 28
    - email: customer@insurance.com
      password: CustPass123!
      full_name: Jane Customer
      age: 42
  test_data_payloads:
    - data_type: policy_creation
      payload:
        customer_id: "550e8400-e29b-41d4-a716-446655440000"
        policy_type: "Auto Insurance"
        coverage_amount: 50000.00
        premium: 1200.00
        start_date: "2024-01-01"
        end_date: "2024-12-31"
      priority: high
    - data_type: claim_submission
      payload:
        policy_id: "660e8400-e29b-41d4-a716-446655440001"
        claim_type: "Vehicle Accident"
        incident_date: "2024-03-15"
        description: "Rear-end collision at intersection"
        amount_claimed: 5000.00
      priority: high
  seed_data:
    admin_user:
      email: admin@insurance.com
      password_hash: "$2a$10$N.zmdr9k7uOCQb376NoUnuTJ8iYqiSfFe5ldjoiKSrmypzxJqMEYu"
      full_name: System Administrator
      role: admin
    default_configuration:
      jwt_expiry_seconds: 3600
      max_login_attempts: 5
      password_policy_min_length: 8

output_structures:
  artifacts:
    - name: API Documentation
      type: OpenAPI Specification
      structure:
        - paths
        - components
        - security
        - info
      description: Complete API documentation with request/response schemas
    - name: Database Schema
      type: SQL DDL Scripts
      structure:
        - table_definitions
        - indexes
        - constraints
        - seed_data
      description: Database schema creation and initialization scripts
  deliverables:
    - type: Docker Images
      format: Container Registry
      location: registry.insurance-portal.com
    - type: Kubernetes Manifests
      format: YAML
      location: k8s/ directory in repository
    - type: API Documentation
      format: HTML/JSON
      location: https://api-docs.insurance-portal.com

technology_stack:
  languages:
    primary: Java
    version: "17"
    secondary:
      - name: TypeScript
        version: "5.0"
        purpose: Frontend development
      - name: SQL
        version: "ANSI SQL"
        purpose: Database queries
  frameworks:
    backend:
      - name: Spring Boot
        version: "3.1"
        purpose: Microservices development
      - name: Spring Security
        version: "6.1"
        purpose: Authentication and authorization
    testing:
      - name: JUnit
        version: "5.9"
        purpose: Unit testing
      - name: Testcontainers
        version: "1.18"
        purpose: Integration testing
  databases:
    primary:
      type: MySQL
      version: "8.0"
      purpose: Transactional data storage
      port: 3306
    cache:
      type: Redis
      version: "7.0"
      purpose: Session storage and caching
      port: 6379
    document_store:
      type: PostgreSQL
      version: "15"
      purpose: Analytical workloads and reporting
      port: 5432
  message_broker:
    type: Apache Kafka
    version: "3.4"
    purpose: Asynchronous communication between services
    queues:
      - name: user-events
        partitions: 3
        replication_factor: 2
      - name: policy-events
        partitions: 5
        replication_factor: 2
      - name: claim-events
        partitions: 5
        replication_factor: 2
  infrastructure:
    container_orchestration:
      platform: Kubernetes
      version: "1.27"
      distribution: "Standard K8s"
    service_mesh:
      enabled: false
      reason: "Not required for initial deployment"
    api_gateway:
      type: Spring Cloud Gateway
      version: "4.0"
      features: [routing, authentication, rate_limiting]
    load_balancer:
      type: Kubernetes LoadBalancer
      provider: Cloud Provider Native

architecture:
  style: Microservices
  design_patterns:
    - pattern: API Gateway
      location: Entry point
      description: Single entry point for all client requests with cross-cutting concerns
      example: Spring Cloud Gateway handling authentication and routing
    - pattern: Database per Service
      location: Data layer
      description: Each microservice owns its data and database
      example: User service uses MySQL, Reporting service uses PostgreSQL
    - pattern: Circuit Breaker
      location: Service communication
      description: Prevents cascade failures between services
      example: Hystrix circuit breaker in service calls
  services:
    - name: api-gateway-service
      responsibility: Request routing, authentication, rate limiting
      database: none
      endpoints:
        - "/*"
    - name: user-service
      responsibility: User account and profile management
      database: MySQL
      endpoints:
        - "/api/users"
        - "/api/users/{id}"
        - "/api/users/{id}/profile"
    - name: policy-service
      responsibility: Insurance policy lifecycle management
      database: MySQL
      endpoints:
        - "/api/policies"
        - "/api/policies/{id}"
        - "/api/policies/customer/{customerId}"
    - name: claims-service
      responsibility: Claims submission and processing
      database: MySQL
      endpoints:
        - "/api/claims"
        - "/api/claims/{id}"
        - "/api/claims/customer/{customerId}"
    - name: reporting-service
      responsibility: Analytics and business reporting
      database: PostgreSQL
      endpoints:
        - "/api/reports/claims"
        - "/api/reports/policies"
        - "/api/reports/revenue"
  communication:
    synchronous:
      protocol: HTTP/REST
      format: JSON
      timeout: "5s"
    asynchronous:
      protocol: Apache Kafka
      format: JSON
      topics: ["user-events", "policy-events", "claim-events"]

monitoring:
  metrics:
    provider: Prometheus
    port: 9090
    scrape_interval: "15s"
    retention: "30d"
    custom_metrics:
      - name: business_transactions_total
        type: counter
        description: Total number of business transactions processed
      - name: policy_creation_duration
        type: histogram
        description: Time taken to create insurance policies
    alerts:
      - name: HighErrorRate
        condition: "error_rate > 0.05"
        severity: critical
        notification: ["email", "slack"]
      - name: ServiceDown
        condition: "up == 0"
        severity: critical
        notification: ["email", "slack", "pagerduty"]
  logging:
    provider: ELK Stack
    log_level: INFO
    structured_logging: true
    log_retention: "90d"
    log_fields:
      timestamp: ISO8601
      level: string
      service: string
      trace_id: string
      user_id: string
      message: string
    aggregation:
      tool: Logstash
      index_pattern: "insurance-portal-*"
    visualization:
      tool: Kibana
      dashboards: ["Application Logs", "Error Analysis", "User Activity"]
  tracing:
    provider: Jaeger
    sampling_rate: 0.1
    max_traces_per_second: 100
    instrumentation:
      - Spring Boot Auto-configuration
      - HTTP requests
      - Database queries
      - Kafka messages
  apm:
    provider: Spring Boot Actuator
    features:
      - Health checks
      - Metrics collection
      - Application info
      - Environment details
  dashboards:
    - name: Application Overview
      tool: Grafana
      panels:
        - Request Rate
        - Response Time
        - Error Rate
        - Active Users
    - name: Infrastructure Health
      tool: Grafana
      panels:
        - CPU Usage
        - Memory Usage
        - Disk I/O
        - Network Traffic
  health_checks:
    endpoints:
      - path: "/actuator/health"
        method: GET
        expected_status: 200
        timeout: "5s"
"""


encoded_content = base64.b64encode(content.encode()).decode()

print(encoded_content)

content = "# Heading 1\n ## Heading 2\n ### Heading 3\n <p> Paragraph <\\p>"

encoded_content = base64.b64encode(content.encode()).decode()

print(encoded_content)
