/*
  Warnings:

  - Added the required column `deliverables` to the `Project` table without a default value. This is not possible if the table is not empty.
  - Added the required column `evaluationCriteria` to the `Project` table without a default value. This is not possible if the table is not empty.

*/
-- AlterTable
ALTER TABLE "Project" ADD COLUMN     "deliverables" JSONB NOT NULL,
ADD COLUMN     "evaluationCriteria" JSONB NOT NULL;
