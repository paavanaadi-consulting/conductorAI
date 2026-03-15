"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { ComponentSelector } from "./component-selector";
import { YamlUpload } from "./yaml-upload";
import { projectsApi } from "@/lib/api";
import type { ComponentSelection } from "@/lib/types";

export function ProjectForm() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [name, setName] = useState("");
  const [githubRepo, setGithubRepo] = useState("");
  const [installationId, setInstallationId] = useState("");
  const [requirementsYaml, setRequirementsYaml] = useState("");
  const [infraYaml, setInfraYaml] = useState("");
  const [components, setComponents] = useState<ComponentSelection[]>([
    "code",
    "unit_test",
  ]);
  const [existingProject, setExistingProject] = useState<string | null>(null);

  // Check for existing project on repo blur
  const checkExisting = async () => {
    if (!githubRepo) return;
    try {
      const existing = await projectsApi.list(githubRepo);
      if (existing.length > 0) {
        setExistingProject(existing[0].id);
      } else {
        setExistingProject(null);
      }
    } catch {
      setExistingProject(null);
    }
  };

  const createMutation = useMutation({
    mutationFn: (andRun: boolean) =>
      projectsApi.create({
        name,
        github_repo: githubRepo,
        github_app_installation_id: installationId
          ? parseInt(installationId)
          : undefined,
        requirements_yaml: requirementsYaml || undefined,
        infra_yaml: infraYaml || undefined,
        selected_components: components,
      }),
    onSuccess: async (project, andRun) => {
      toast.success("Project created");
      queryClient.invalidateQueries({ queryKey: ["projects"] });

      if (andRun) {
        try {
          await projectsApi.run(project.id, {
            selected_components: components,
          });
          toast.success("Workflow started");
        } catch (e: any) {
          toast.error(`Workflow failed: ${e.message}`);
        }
      }
      router.push(`/projects/${project.id}`);
    },
    onError: (err: any) => {
      if (err.message?.includes("already exists")) {
        toast.error("Project with this repo already exists");
      } else {
        toast.error(err.message);
      }
    },
  });

  const updateMutation = useMutation({
    mutationFn: () =>
      projectsApi.update(existingProject!, {
        name: name || undefined,
        requirements_yaml: requirementsYaml || undefined,
        infra_yaml: infraYaml || undefined,
        selected_components: components,
      }),
    onSuccess: (project) => {
      toast.success("Project updated");
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      router.push(`/projects/${project.id}`);
    },
    onError: (err: any) => toast.error(err.message),
  });

  const loading = createMutation.isPending || updateMutation.isPending;

  return (
    <div className="max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">
        {existingProject ? "Update Project" : "New Project"}
      </h1>

      {existingProject && (
        <div className="mb-4 p-3 rounded-md bg-amber-50 border border-amber-200 text-sm text-amber-800">
          A project with this GitHub repo already exists.{" "}
          <button
            onClick={() => router.push(`/projects/${existingProject}`)}
            className="underline font-medium"
          >
            View existing project
          </button>{" "}
          or update it below.
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: Form fields + component selector */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Project Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="name">Project Name</Label>
                <Input
                  id="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="my-data-pipeline"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="repo">GitHub Repository</Label>
                <Input
                  id="repo"
                  value={githubRepo}
                  onChange={(e) => setGithubRepo(e.target.value)}
                  onBlur={checkExisting}
                  placeholder="org/repo"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="install-id">
                  GitHub App Installation ID{" "}
                  <span className="text-muted-foreground">(optional)</span>
                </Label>
                <Input
                  id="install-id"
                  value={installationId}
                  onChange={(e) => setInstallationId(e.target.value)}
                  placeholder="12345678"
                  type="number"
                />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Generation Options</CardTitle>
            </CardHeader>
            <CardContent>
              <ComponentSelector value={components} onChange={setComponents} />
            </CardContent>
          </Card>

          <div className="flex gap-3">
            {existingProject ? (
              <Button onClick={() => updateMutation.mutate()} disabled={loading}>
                {updateMutation.isPending ? "Updating..." : "Update Project"}
              </Button>
            ) : (
              <>
                <Button
                  onClick={() => createMutation.mutate(false)}
                  disabled={loading || !name || !githubRepo}
                  variant="outline"
                >
                  {createMutation.isPending ? "Creating..." : "Create Project"}
                </Button>
                <Button
                  onClick={() => createMutation.mutate(true)}
                  disabled={loading || !name || !githubRepo}
                >
                  Create & Run
                </Button>
              </>
            )}
          </div>
        </div>

        {/* Right: YAML uploads */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Requirements</CardTitle>
            </CardHeader>
            <CardContent>
              <YamlUpload
                label="Requirements YAML"
                category="requirements"
                value={requirementsYaml}
                onChange={setRequirementsYaml}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Infrastructure</CardTitle>
            </CardHeader>
            <CardContent>
              <YamlUpload
                label="Infrastructure YAML"
                category="infrastructure"
                value={infraYaml}
                onChange={setInfraYaml}
              />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
