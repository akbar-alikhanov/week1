import type { Metadata } from "next";

import {
  businessCases,
  excelQuestions,
  sqlQuestions,
} from "@/features/career/content/interview-content";
import { QuestionCard } from "@/features/career/components/question-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/ui/tabs";

export const metadata: Metadata = {
  title: "Interview prep",
  robots: { index: false, follow: false },
};

export default function CareerPage() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Interview prep</h1>
        <p className="text-muted-foreground">
          Practice answering common Data Analyst interview questions and business cases.
        </p>
      </div>

      <Tabs defaultValue="sql">
        <TabsList>
          <TabsTrigger value="sql">SQL</TabsTrigger>
          <TabsTrigger value="excel">Excel</TabsTrigger>
          <TabsTrigger value="cases">Business cases</TabsTrigger>
        </TabsList>

        <TabsContent value="sql" className="space-y-2">
          {sqlQuestions.map((q) => (
            <QuestionCard key={q.id} question={q.question} answer={q.answer} />
          ))}
        </TabsContent>

        <TabsContent value="excel" className="space-y-2">
          {excelQuestions.map((q) => (
            <QuestionCard key={q.id} question={q.question} answer={q.answer} />
          ))}
        </TabsContent>

        <TabsContent value="cases" className="space-y-4">
          {businessCases.map((c) => (
            <Card key={c.id}>
              <CardHeader>
                <CardTitle className="text-base">{c.title}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <p>{c.prompt}</p>
                <details className="group">
                  <summary className="cursor-pointer text-sm font-medium text-primary">
                    Show a suggested approach
                  </summary>
                  <p className="mt-2 text-muted-foreground">{c.approach}</p>
                </details>
              </CardContent>
            </Card>
          ))}
        </TabsContent>
      </Tabs>
    </main>
  );
}
