import { auth } from "@/infrastructure/auth/auth";
import { getContainer } from "@/infrastructure/container";
import { ForbiddenError } from "@/shared/errors/app-error";
import { Badge } from "@/shared/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import { Separator } from "@/shared/ui/separator";
import { LockedCourseNotice } from "@/features/courses/components/locked-course-notice";
import { ProjectSubmissionForm } from "@/features/projects/components/project-submission-form";

export default async function ProjectDetailPage({
  params,
}: PageProps<"/projects/[projectSlug]">) {
  const { projectSlug } = await params;
  const session = await auth();

  let project;
  try {
    project = await getContainer().getProjectUseCase.execute(
      projectSlug,
      session?.user?.id ?? null,
    );
  } catch (error) {
    if (error instanceof ForbiddenError) {
      return <LockedCourseNotice message={error.message} />;
    }
    throw error;
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 p-6">
      <div className="space-y-2">
        <p className="text-xs text-muted-foreground">{project.courseTitle}</p>
        <h1 className="text-2xl font-semibold tracking-tight">{project.title}</h1>
        <div className="flex items-center gap-2">
          <Badge variant="outline">+{project.xpReward} XP</Badge>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Business context</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="whitespace-pre-line text-sm text-muted-foreground">
            {project.businessContext}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Dataset</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="whitespace-pre-line text-sm text-muted-foreground">
            {project.datasetDescription}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Goal</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">{project.goal}</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Tasks</CardTitle>
        </CardHeader>
        <CardContent>
          <ol className="list-decimal space-y-2 pl-4 text-sm">
            {project.tasks.map((task) => (
              <li key={task.id}>
                <span className="font-medium">{task.title}.</span>{" "}
                <span className="text-muted-foreground">{task.description}</span>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Expected deliverables</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="list-disc space-y-1 pl-4 text-sm text-muted-foreground">
            {project.deliverables.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Hints</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="list-disc space-y-1 pl-4 text-sm text-muted-foreground">
            {project.hints.map((hint) => (
              <li key={hint}>{hint}</li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Evaluation</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="list-disc space-y-1 pl-4 text-sm text-muted-foreground">
            {project.evaluationCriteria.map((criterion) => (
              <li key={criterion}>{criterion}</li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <Separator />

      <ProjectSubmissionForm
        projectId={project.id}
        initialSubmissions={project.submissions}
      />
    </main>
  );
}
