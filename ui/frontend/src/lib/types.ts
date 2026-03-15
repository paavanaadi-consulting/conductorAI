// ConductorAI UI — TypeScript Types

export type ComponentSelection =
  | "code"
  | "unit_test"
  | "test_data"
  | "deployment"
  | "monitoring";

export const COMPONENTS: {
  id: ComponentSelection;
  label: string;
  description: string;
  phase: string;
}[] = [
  {
    id: "code",
    label: "Code",
    description: "Generate source code (Coding Agent)",
    phase: "DEVELOPMENT",
  },
  {
    id: "unit_test",
    label: "Unit Tests",
    description: "Generate & run tests (Test Agent)",
    phase: "DEVELOPMENT",
  },
  {
    id: "test_data",
    label: "Test Data",
    description: "Generate test fixtures (Test Data Agent)",
    phase: "DEVELOPMENT",
  },
  {
    id: "deployment",
    label: "Deployment",
    description: "CI/CD + deploy configs (DevOps Agent)",
    phase: "DEVOPS",
  },
  {
    id: "monitoring",
    label: "Monitoring Code",
    description: "Monitoring setup (Monitor Agent)",
    phase: "MONITORING",
  },
];

export interface Project {
  id: string;
  name: string;
  github_repo: string;
  github_app_installation_id?: number;
  requirements_yaml?: string;
  infra_yaml?: string;
  last_pipeline_yaml?: string;
  selected_components: string[];
  created_at: string;
  updated_at: string;
}

export interface ProjectSummary {
  id: string;
  name: string;
  github_repo: string;
  selected_components: string[];
  created_at: string;
  updated_at: string;
}

export interface WorkflowRun {
  id: string;
  project_id: string;
  status: "pending" | "in_progress" | "completed" | "failed";
  workflow_id?: string;
  selected_components: string[];
  pipeline_yaml?: string;
  result_summary?: string;
  created_at: string;
  completed_at?: string;
}

export interface WorkflowProgress {
  workflow_id: string;
  status: string;
  current_phase: string;
  completed_tasks: number;
  failed_tasks: number;
  feedback_count: number;
  phase_history: Record<string, unknown>[];
}

export interface TemplateInfo {
  filename: string;
  category: string;
}

export interface GitHubRepo {
  id: number;
  full_name: string;
  name: string;
  description?: string;
  html_url: string;
  default_branch: string;
  open_issues_count: number;
}

export interface PullRequest {
  number: number;
  title: string;
  state: string;
  user_login: string;
  user_avatar_url: string;
  created_at: string;
  updated_at: string;
  html_url: string;
  additions: number;
  deletions: number;
  changed_files: number;
}

export interface PRReview {
  id: string;
  pr_number: number;
  pr_title?: string;
  complexity_score: number;
  quality_score: number;
  review_summary: string;
  findings: string[];
  recommendations: string[];
  reviewed_at: string;
}
