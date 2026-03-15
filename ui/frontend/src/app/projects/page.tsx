"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Trash2, Play, Eye, GitPullRequest } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { projectsApi, githubApi } from "@/lib/api";
import { PRReviewCard } from "@/components/github/pr-review-card";
import type { PullRequest, PRReview } from "@/lib/types";

export default function ProjectsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [installationId, setInstallationId] = useState("");

  const { data: projects, isLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: () => projectsApi.list(),
  });

  const { data: repos } = useQuery({
    queryKey: ["github-repos", installationId],
    queryFn: () => githubApi.listRepos(parseInt(installationId)),
    enabled: !!installationId && parseInt(installationId) > 0,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => projectsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      toast.success("Project deleted");
    },
  });

  return (
    <div className="max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">Projects & Repos</h1>

      <Tabs defaultValue="projects">
        <TabsList>
          <TabsTrigger value="projects">My Projects</TabsTrigger>
          <TabsTrigger value="repos">GitHub Repos</TabsTrigger>
        </TabsList>

        {/* -- My Projects Tab -- */}
        <TabsContent value="projects" className="mt-4">
          {isLoading ? (
            <p className="text-muted-foreground">Loading...</p>
          ) : !projects?.length ? (
            <Card>
              <CardContent className="py-8 text-center text-muted-foreground">
                No projects yet.{" "}
                <button
                  onClick={() => router.push("/projects/new")}
                  className="underline text-primary"
                >
                  Create one
                </button>
              </CardContent>
            </Card>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Repository</TableHead>
                  <TableHead>Components</TableHead>
                  <TableHead>Updated</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {projects.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell className="font-medium">{p.name}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {p.github_repo}
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1 flex-wrap">
                        {p.selected_components.map((c) => (
                          <Badge key={c} variant="outline" className="text-xs">
                            {c}
                          </Badge>
                        ))}
                      </div>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {new Date(p.updated_at).toLocaleDateString()}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex gap-1 justify-end">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => router.push(`/projects/${p.id}`)}
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => router.push(`/projects/${p.id}/prs`)}
                        >
                          <GitPullRequest className="h-4 w-4" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="text-destructive"
                          onClick={() => deleteMutation.mutate(p.id)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </TabsContent>

        {/* -- GitHub Repos Tab -- */}
        <TabsContent value="repos" className="mt-4 space-y-4">
          <div className="flex items-end gap-3">
            <div className="space-y-1">
              <Label className="text-sm">GitHub App Installation ID</Label>
              <Input
                value={installationId}
                onChange={(e) => setInstallationId(e.target.value)}
                placeholder="12345678"
                type="number"
                className="w-48"
              />
            </div>
          </div>

          {repos && (
            <div className="grid gap-3 sm:grid-cols-2">
              {repos.map((repo) => (
                <Card key={repo.id}>
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-base">
                        <a
                          href={repo.html_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="hover:underline"
                        >
                          {repo.full_name}
                        </a>
                      </CardTitle>
                      {repo.open_issues_count > 0 && (
                        <Badge variant="outline">
                          {repo.open_issues_count} issues
                        </Badge>
                      )}
                    </div>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm text-muted-foreground line-clamp-2">
                      {repo.description || "No description"}
                    </p>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
