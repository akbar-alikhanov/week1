"use client";

import Editor, { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor";
import { useTheme } from "next-themes";

// Bundle Monaco through Next.js instead of fetching it from a CDN at
// runtime, so the editor works offline and isn't at the mercy of a
// third-party CDN being reachable. Must run before <Editor> mounts and
// calls the default loader, so it happens at module scope, not an effect.
loader.config({ monaco });

export function SqlEditor({
  value,
  onChange,
  height = "160px",
}: {
  value: string;
  onChange: (value: string) => void;
  height?: string;
}) {
  const { resolvedTheme } = useTheme();

  return (
    <div className="overflow-hidden rounded-md border border-input">
      <Editor
        height={height}
        defaultLanguage="sql"
        value={value}
        onChange={(next) => onChange(next ?? "")}
        theme={resolvedTheme === "dark" ? "vs-dark" : "light"}
        options={{
          minimap: { enabled: false },
          fontSize: 13,
          lineNumbers: "on",
          scrollBeyondLastLine: false,
          wordWrap: "on",
          padding: { top: 8, bottom: 8 },
        }}
      />
    </div>
  );
}
