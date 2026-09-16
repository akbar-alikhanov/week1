import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import prettierConfig from "eslint-config-prettier";

const domainDependencyRule = {
  "no-restricted-imports": [
    "error",
    {
      paths: [
        { name: "react", message: "Domain/application layers must stay framework-free." },
        {
          name: "next",
          message: "Domain/application layers must not depend on Next.js.",
        },
        {
          name: "next-auth",
          message: "Domain/application layers must not depend on Next.js.",
        },
        {
          name: "@prisma/client",
          message:
            "Domain/application layers must not depend on Prisma. Depend on a repository interface instead.",
        },
      ],
      patterns: [
        {
          group: ["next/*"],
          message: "Domain/application layers must not depend on Next.js.",
        },
        {
          group: ["@/infrastructure/*"],
          message:
            "Domain/application layers must not depend on infrastructure implementations. Depend on an interface instead.",
        },
      ],
    },
  ],
};

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  prettierConfig,
  {
    rules: {
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
    },
  },
  {
    files: ["src/entities/**/*.{ts,tsx}", "src/features/**/application/**/*.{ts,tsx}"],
    rules: domainDependencyRule,
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts", "src/generated/**"]),
]);

export default eslintConfig;
