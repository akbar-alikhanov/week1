import { z } from "zod";

export const submittedAnswerSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("MULTIPLE_CHOICE"),
    selectedIndices: z.array(z.number().int()),
  }),
  z.object({ type: z.literal("TEXT_INPUT"), value: z.string().max(500) }),
  z.object({ type: z.literal("FORMULA_INPUT"), formula: z.string().max(500) }),
  z.object({ type: z.literal("SQL_QUERY"), query: z.string().max(4000) }),
  z.object({ type: z.literal("TRUE_FALSE"), value: z.boolean() }),
  z.object({ type: z.literal("MATCHING"), pairs: z.array(z.number().int()) }),
  z.object({ type: z.literal("ORDERING"), order: z.array(z.number().int()) }),
  z.object({ type: z.literal("DATA_ANALYSIS"), value: z.string().max(500) }),
]);
