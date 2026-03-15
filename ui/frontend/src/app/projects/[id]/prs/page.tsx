"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { Bot, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
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
import type { PRReview } from "@/lib/types";

export default function ProjectPRsPage() {
  const { id } = useParams<{ id: string }>();
  const [submitToGithub, setSubmitToGithub] = useState(false);
  const [reviews, setReviews] = useState<Record<number, PRReview>>({});

  const { data: project } = useQuery({
    queryKey: ["project", id],
    queryFn: () => projectsApi.get(id),
  });

  const installationId = project?.github_app_installation_id;
  const [owner, repo] = (project?.github_repo || "/").split("/");

  const { data: prs, isLoading } = useQuery({
    queryKey: ["prs", owner, repo, installationId],
    queryFn: () => githubApi.listPRs(owner, repo, installationId!, "all"),
    enabled: !!owner && !!repo && !!installationId,
  });

  const reviewMutation = useMutation({
    mutationFn: (prNumber: number) =>
      githubApi.reviewPR(
        owner,
        repo,
        prNumber,
        id,
        installationId!,
        submitToGithub
      ),
    onSuccess: (review) => {
      setReviews((prev) => ({ ...prev, [review.pr_number]: review }));
      toast.success(`PR #${review.pr_number} reviewed`);
    },
    onError: (err: any) => toast.error(err.message),
  });

  if (!project) {
    return <p className="text-muted-foreground">Loading...</p>;
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Pull Requests</h1>
        <p className="text-muted-foreground">
          {project.name} &mdash; {project.github_repo}
        </p>
      </div>

      {!installationId ? (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            No GitHub App Installation ID configured for this project.
            Update the project to add one.
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="flex items-center gap-3">
            <Checkbox
              id="submit-gh"
              checked={submitToGithub}
              onCheckedChange={(v) => setSubmitToGithub(v === true)}
            />
            <Label htmlFor="submit-gh" className="text-sm">
              Also submit review comments to GitHub
            </Label>
          </div>

          {isLoading ? (
            <p className="text-muted-foreground">Loading PRs...</p>
          ) : !prs?.length ? (
            <Card>
              <CardContent className="py-8 text-center text-muted-foreground">
                No pull requests found.
              </CardContent>
            </Card>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>#</TableHead>
                  <TableHead>Title</TableHead>
                  <TableHead>Author</TableHead>
                  <TableHead>Changes</TableHead>
                  <TableHead>State</TableHead>
                  <TableHead className="text-right">Review</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {prs.map((pr) => (
                  <TableRow key={pr.number}>
                    <TableCell className="font-mono">{pr.number}</TableCell>
                    <TableCell>
                      <a
                        href={pr.html_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="hover:underline flex items-center gap-1"
                      >
                        {pr.title}
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    </TableCell>
                    <TableCell className="text-sm">{pr.user_login}</TableCell>
                    <TableCell className="text-sm">
                      <span className="text-green-600">+{pr.additions}</span>{" "}
                      <span className="text-red-600">-{pr.deletions}</span>{" "}
                      <span className="text-muted-foreground">
                        ({pr.changed_files} files)
                      </span>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="outline"
                        className={
                          pr.state === "open"
                            ? "bg-green-50 text-green-700"
                            : "bg-purple-50 text-purple-700"
                        }
                      >
                        {pr.state}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => reviewMutation.mutate(pr.number)}
                        disabled={
                          reviewMutation.isPending &&
                          reviewMutation.variables === pr.number
                        }
                      >
                        <Bot className="h-4 w-4 mr-1" />
                        {reviewMutation.isPending &&
                        reviewMutation.variables === pr.number
                          ? "Reviewing..."
                          : "AI Review"}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          {/* Review results */}
          {Object.values(reviews).length > 0 && (
            <div className="space-y-4 mt-6">
              <h2 className="text-lg font-semibold">Review Results</h2>
              {Object.values(reviews).map((review) => (
                <PRReviewCard key={review.id} review={review} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
