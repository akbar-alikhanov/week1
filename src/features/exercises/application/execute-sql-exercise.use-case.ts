import type {
  SqlQueryResult,
  SqlSandboxService,
} from "@/features/exercises/application/ports";

/**
 * Runs an arbitrary SELECT query against the sandbox for live preview
 * (SQL Playground "Run Query", and the "Run" button on SQL_QUERY exercises).
 * Does not grade or persist anything - see SubmitExerciseUseCase for that.
 */
export class ExecuteSqlExerciseUseCase {
  constructor(private readonly sandbox: SqlSandboxService) {}

  async execute(query: string): Promise<SqlQueryResult> {
    return this.sandbox.run(query);
  }
}
