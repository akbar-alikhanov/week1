"use client";

import { useState, useTransition } from "react";
import { CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

import { submitProjectAction } from "@/features/projects/actions";
import { toastNewAchievements } from "@/features/achievements/components/toast-achievements";
import type { ProjectSubmissionDetail } from "@/features/projects/application/get-project.use-case";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { Textarea } from "@/shared/ui/textarea";

export function ProjectSubmissionForm({
  projectId,
  initialSubmissions,
}: {
  projectId: string;
  initialSubmissions: ProjectSubmissionDetail[];
}) {
  const [submissions, setSubmissions] = useState(initialSubmissions);
  const [summary, setSummary] = useState("");
  const [deliverableUrl, setDeliverableUrl] = useState("");
  const [isPending, startTransition] = useTransition();

  function handleSubmit() {
    startTransition(async () => {
      const response = await submitProjectAction({
        projectId,
        summary,
        deliverableUrl,
      });
      if (!response.success) {
        toast.error(response.error);
        return;
      }
      if (response.data.xpAwarded > 0) {
        toast.success(`+${response.data.xpAwarded} XP — project submitted!`);
      } else {
        toast.success("Submission recorded.");
      }
      toastNewAchievements(response.data.newAchievements);
      setSubmissions((prev) => [
        {
          id: response.data.submissionId,
          summary,
          deliverableUrl: deliverableUrl || null,
          status: response.data.status,
          feedback: null,
          createdAt: new Date().toISOString(),
        },
        ...prev,
      ]);
      setSummary("");
      setDeliverableUrl("");
    });
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Submit your solution</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="summary">Summary of your approach and findings</Label>
            <Textarea
              id="summary"
              rows={5}
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              placeholder="Describe what you did, the key numbers you found, and your recommendations…"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="deliverableUrl">Deliverable link (optional)</Label>
            <Input
              id="deliverableUrl"
              type="url"
              value={deliverableUrl}
              onChange={(e) => setDeliverableUrl(e.target.value)}
              placeholder="https://…"
            />
          </div>
          <Button
            onClick={handleSubmit}
            disabled={isPending || summary.trim().length < 20}
          >
            {isPending ? "Submitting…" : "Submit project"}
          </Button>
        </CardContent>
      </Card>

      {submissions.length > 0 ? (
        <div className="space-y-2">
          <h3 className="text-sm font-medium">Your submissions</h3>
          <ul className="space-y-2">
            {submissions.map((submission) => (
              <li
                key={submission.id}
                className="rounded-md border border-border p-3 text-sm"
              >
                <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
                  <CheckCircle2 className="size-3.5 text-success" />
                  <span>{new Date(submission.createdAt).toLocaleString()}</span>
                </div>
                <p className="whitespace-pre-wrap">{submission.summary}</p>
                {submission.deliverableUrl ? (
                  <a
                    href={submission.deliverableUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-1 inline-block text-xs text-primary underline"
                  >
                    {submission.deliverableUrl}
                  </a>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
