// ConductorAI UI — API Client

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

async function fetchJSON<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail?.message || body.detail || res.statusText);
  }
  return res.json();
}

// ---------- Projects ----------

export const projectsApi = {
  list: (githubRepo?: string) =>
    fetchJSON<import("./types").ProjectSummary[]>(
      `/projects${githubRepo ? `?github_repo=${encodeURIComponent(githubRepo)}` : ""}`
    ),

  get: (id: string) =>
    fetchJSON<import("./types").Project>(`/projects/${id}`),

  create: (data: {
    name: string;
    github_repo: string;
    github_app_installation_id?: number;
    requirements_yaml?: string;
    infra_yaml?: string;
    selected_components: string[];
  }) =>
    fetchJSON<import("./types").Project>("/projects", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  update: (
    id: string,
    data: {
      name?: string;
      requirements_yaml?: string;
      infra_yaml?: string;
      selected_components?: string[];
    }
  ) =>
    fetchJSON<import("./types").Project>(`/projects/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    fetch(`${API_BASE}/projects/${id}`, { method: "DELETE" }),

  run: (
    id: string,
    data: { selected_components: string[]; pipeline_type?: string }
  ) =>
    fetchJSON<import("./types").WorkflowRun>(`/projects/${id}/run`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// ---------- Workflows ----------

export const workflowsApi = {
  get: (runId: string) =>
    fetchJSON<import("./types").WorkflowRun>(`/workflows/${runId}`),

  listByProject: (projectId: string) =>
    fetchJSON<import("./types").WorkflowRun[]>(
      `/workflows/project/${projectId}`
    ),
};

// ---------- Templates ----------

export const templatesApi = {
  listRequirements: () =>
    fetchJSON<import("./types").TemplateInfo[]>("/templates/requirements"),

  listInfrastructure: () =>
    fetchJSON<import("./types").TemplateInfo[]>("/templates/infrastructure"),

  getContent: (category: string, filename: string) =>
    fetchJSON<{ content: string }>(`/templates/${category}/${filename}`),
};

// ---------- Upload ----------

export async function uploadYaml(
  file: File
): Promise<{ filename: string; content: string; valid: boolean; error?: string }> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/upload`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error("Upload failed");
  return res.json();
}

// ---------- GitHub ----------

export const githubApi = {
  listRepos: (installationId: number) =>
    fetchJSON<import("./types").GitHubRepo[]>(
      `/github/repos?installation_id=${installationId}`
    ),

  listPRs: (
    owner: string,
    repo: string,
    installationId: number,
    state = "open"
  ) =>
    fetchJSON<import("./types").PullRequest[]>(
      `/github/repos/${owner}/${repo}/prs?installation_id=${installationId}&state=${state}`
    ),

  reviewPR: (
    owner: string,
    repo: string,
    prNumber: number,
    projectId: string,
    installationId: number,
    submitToGithub = false
  ) =>
    fetchJSON<import("./types").PRReview>(
      `/github/repos/${owner}/${repo}/prs/${prNumber}/review?project_id=${projectId}`,
      {
        method: "POST",
        body: JSON.stringify({
          installation_id: installationId,
          submit_to_github: submitToGithub,
        }),
      }
    ),

  getPRReviews: (
    owner: string,
    repo: string,
    prNumber: number,
    projectId: string
  ) =>
    fetchJSON<import("./types").PRReview[]>(
      `/github/repos/${owner}/${repo}/prs/${prNumber}/review?project_id=${projectId}`
    ),
};
