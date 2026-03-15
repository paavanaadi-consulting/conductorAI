"use client";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { PRReview } from "@/lib/types";

function ScoreBadge({ label, score }: { label: string; score: number }) {
  const color =
    score >= 8
      ? "bg-green-100 text-green-800"
      : score >= 5
      ? "bg-amber-100 text-amber-800"
      : "bg-red-100 text-red-800";

  return (
    <div className="text-center">
      <div className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-bold ${color}`}>
        {score.toFixed(1)}
      </div>
      <p className="text-xs text-muted-foreground mt-1">{label}</p>
    </div>
  );
}

interface Props {
  review: PRReview;
}

export function PRReviewCard({ review }: Props) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">
          #{review.pr_number} {review.pr_title}
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          Reviewed {new Date(review.reviewed_at).toLocaleDateString()}
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex gap-6">
          <ScoreBadge label="Complexity" score={review.complexity_score} />
          <ScoreBadge label="Quality" score={review.quality_score} />
        </div>

        <p className="text-sm">{review.review_summary}</p>

        {review.findings.length > 0 && (
          <div>
            <h4 className="text-sm font-medium mb-1">Findings</h4>
            <ul className="text-sm space-y-1">
              {review.findings.map((f, i) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="text-amber-500 mt-0.5">&#9679;</span>
                  {f}
                </li>
              ))}
            </ul>
          </div>
        )}

        {review.recommendations.length > 0 && (
          <div>
            <h4 className="text-sm font-medium mb-1">Recommendations</h4>
            <ul className="text-sm space-y-1">
              {review.recommendations.map((r, i) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="text-blue-500 mt-0.5">&#9679;</span>
                  {r}
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
