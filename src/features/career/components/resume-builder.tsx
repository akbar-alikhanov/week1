"use client";

import { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { Separator } from "@/shared/ui/separator";
import { Textarea } from "@/shared/ui/textarea";

interface ExperienceEntry {
  id: string;
  role: string;
  company: string;
  period: string;
  description: string;
}

interface EducationEntry {
  id: string;
  school: string;
  degree: string;
  period: string;
}

interface ResumeData {
  fullName: string;
  title: string;
  email: string;
  phone: string;
  location: string;
  summary: string;
  skills: string;
  experience: ExperienceEntry[];
  education: EducationEntry[];
}

const STORAGE_KEY = "dala-resume-draft";

const EMPTY_RESUME: ResumeData = {
  fullName: "",
  title: "Data Analyst",
  email: "",
  phone: "",
  location: "",
  summary: "",
  skills: "Excel, SQL, Power BI",
  experience: [],
  education: [],
};

function newId() {
  return Math.random().toString(36).slice(2, 10);
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function ResumeBuilder() {
  const [resume, setResume] = useState<ResumeData>(EMPTY_RESUME);

  // Loading the saved draft only after mount avoids a hydration mismatch,
  // since the server can't know what's in the client's localStorage.
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setResume(JSON.parse(saved) as ResumeData);
      }
    } catch {
      // localStorage unavailable (private mode, blocked storage) - start blank.
    }
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(resume));
    } catch {
      // Ignore write failures; the form still works for this session.
    }
  }, [resume]);

  function update<K extends keyof ResumeData>(key: K, value: ResumeData[K]) {
    setResume((prev) => ({ ...prev, [key]: value }));
  }

  function addExperience() {
    update("experience", [
      ...resume.experience,
      { id: newId(), role: "", company: "", period: "", description: "" },
    ]);
  }

  function updateExperience(id: string, patch: Partial<ExperienceEntry>) {
    update(
      "experience",
      resume.experience.map((entry) =>
        entry.id === id ? { ...entry, ...patch } : entry,
      ),
    );
  }

  function removeExperience(id: string) {
    update(
      "experience",
      resume.experience.filter((entry) => entry.id !== id),
    );
  }

  function addEducation() {
    update("education", [
      ...resume.education,
      { id: newId(), school: "", degree: "", period: "" },
    ]);
  }

  function updateEducation(id: string, patch: Partial<EducationEntry>) {
    update(
      "education",
      resume.education.map((entry) => (entry.id === id ? { ...entry, ...patch } : entry)),
    );
  }

  function removeEducation(id: string) {
    update(
      "education",
      resume.education.filter((entry) => entry.id !== id),
    );
  }

  function handlePrint() {
    const skills = resume.skills
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);

    const win = window.open("", "_blank", "noopener,noreferrer");
    if (!win) return;

    win.document.write(`<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>${escapeHtml(resume.fullName || "Resume")}</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 700px; margin: 40px auto; color: #111; }
  h1 { margin-bottom: 0; }
  h2 { margin-top: 24px; border-bottom: 1px solid #ddd; padding-bottom: 4px; }
  .muted { color: #555; }
  .entry { margin-bottom: 12px; }
  .entry-title { font-weight: 600; }
</style>
</head>
<body>
  <h1>${escapeHtml(resume.fullName || "Your Name")}</h1>
  <p class="muted">${escapeHtml(resume.title)}${resume.location ? " · " + escapeHtml(resume.location) : ""}</p>
  <p class="muted">${escapeHtml(resume.email)}${resume.phone ? " · " + escapeHtml(resume.phone) : ""}</p>

  ${resume.summary ? `<h2>Summary</h2><p>${escapeHtml(resume.summary)}</p>` : ""}

  ${skills.length > 0 ? `<h2>Skills</h2><p>${skills.map(escapeHtml).join(", ")}</p>` : ""}

  ${
    resume.experience.length > 0
      ? `<h2>Experience</h2>${resume.experience
          .map(
            (e) =>
              `<div class="entry"><div class="entry-title">${escapeHtml(e.role)} — ${escapeHtml(e.company)}</div><div class="muted">${escapeHtml(e.period)}</div><p>${escapeHtml(e.description)}</p></div>`,
          )
          .join("")}`
      : ""
  }

  ${
    resume.education.length > 0
      ? `<h2>Education</h2>${resume.education
          .map(
            (e) =>
              `<div class="entry"><div class="entry-title">${escapeHtml(e.degree)} — ${escapeHtml(e.school)}</div><div class="muted">${escapeHtml(e.period)}</div></div>`,
          )
          .join("")}`
      : ""
  }
</body>
</html>`);
    win.document.close();
    win.focus();
    win.print();
  }

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Contact info</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="fullName">Full name</Label>
              <Input
                id="fullName"
                value={resume.fullName}
                onChange={(e) => update("fullName", e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="title">Target role</Label>
              <Input
                id="title"
                value={resume.title}
                onChange={(e) => update("title", e.target.value)}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  value={resume.email}
                  onChange={(e) => update("email", e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="phone">Phone</Label>
                <Input
                  id="phone"
                  value={resume.phone}
                  onChange={(e) => update("phone", e.target.value)}
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="location">Location</Label>
              <Input
                id="location"
                value={resume.location}
                onChange={(e) => update("location", e.target.value)}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Summary & skills</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="summary">Summary</Label>
              <Textarea
                id="summary"
                rows={3}
                value={resume.summary}
                onChange={(e) => update("summary", e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="skills">Skills (comma-separated)</Label>
              <Input
                id="skills"
                value={resume.skills}
                onChange={(e) => update("skills", e.target.value)}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle className="text-base">Experience</CardTitle>
            <Button variant="outline" size="sm" onClick={addExperience}>
              <Plus className="size-4" />
              Add
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            {resume.experience.map((entry) => (
              <div
                key={entry.id}
                className="space-y-2 rounded-md border border-border p-3"
              >
                <div className="grid grid-cols-2 gap-2">
                  <Input
                    placeholder="Role"
                    value={entry.role}
                    onChange={(e) => updateExperience(entry.id, { role: e.target.value })}
                  />
                  <Input
                    placeholder="Company"
                    value={entry.company}
                    onChange={(e) =>
                      updateExperience(entry.id, { company: e.target.value })
                    }
                  />
                </div>
                <Input
                  placeholder="Period (e.g. 2022 – present)"
                  value={entry.period}
                  onChange={(e) => updateExperience(entry.id, { period: e.target.value })}
                />
                <Textarea
                  placeholder="What did you do and achieve?"
                  rows={2}
                  value={entry.description}
                  onChange={(e) =>
                    updateExperience(entry.id, { description: e.target.value })
                  }
                />
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => removeExperience(entry.id)}
                  className="text-destructive"
                >
                  <Trash2 className="size-4" />
                  Remove
                </Button>
              </div>
            ))}
            {resume.experience.length === 0 ? (
              <p className="text-sm text-muted-foreground">No experience added yet.</p>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle className="text-base">Education</CardTitle>
            <Button variant="outline" size="sm" onClick={addEducation}>
              <Plus className="size-4" />
              Add
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            {resume.education.map((entry) => (
              <div
                key={entry.id}
                className="space-y-2 rounded-md border border-border p-3"
              >
                <Input
                  placeholder="Degree"
                  value={entry.degree}
                  onChange={(e) => updateEducation(entry.id, { degree: e.target.value })}
                />
                <Input
                  placeholder="School"
                  value={entry.school}
                  onChange={(e) => updateEducation(entry.id, { school: e.target.value })}
                />
                <Input
                  placeholder="Period"
                  value={entry.period}
                  onChange={(e) => updateEducation(entry.id, { period: e.target.value })}
                />
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => removeEducation(entry.id)}
                  className="text-destructive"
                >
                  <Trash2 className="size-4" />
                  Remove
                </Button>
              </div>
            ))}
            {resume.education.length === 0 ? (
              <p className="text-sm text-muted-foreground">No education added yet.</p>
            ) : null}
          </CardContent>
        </Card>
      </div>

      <div className="space-y-4 lg:sticky lg:top-6 lg:self-start">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Preview</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div>
              <p className="text-lg font-semibold">{resume.fullName || "Your Name"}</p>
              <p className="text-muted-foreground">
                {resume.title}
                {resume.location ? ` · ${resume.location}` : ""}
              </p>
              <p className="text-muted-foreground">
                {resume.email}
                {resume.phone ? ` · ${resume.phone}` : ""}
              </p>
            </div>

            {resume.summary ? (
              <>
                <Separator />
                <p>{resume.summary}</p>
              </>
            ) : null}

            {resume.skills.trim() ? (
              <>
                <Separator />
                <p className="text-muted-foreground">{resume.skills}</p>
              </>
            ) : null}

            {resume.experience.length > 0 ? (
              <>
                <Separator />
                <div className="space-y-2">
                  {resume.experience.map((entry) => (
                    <div key={entry.id}>
                      <p className="font-medium">
                        {entry.role || "Role"} — {entry.company || "Company"}
                      </p>
                      <p className="text-xs text-muted-foreground">{entry.period}</p>
                      <p className="text-muted-foreground">{entry.description}</p>
                    </div>
                  ))}
                </div>
              </>
            ) : null}

            {resume.education.length > 0 ? (
              <>
                <Separator />
                <div className="space-y-2">
                  {resume.education.map((entry) => (
                    <div key={entry.id}>
                      <p className="font-medium">
                        {entry.degree || "Degree"} — {entry.school || "School"}
                      </p>
                      <p className="text-xs text-muted-foreground">{entry.period}</p>
                    </div>
                  ))}
                </div>
              </>
            ) : null}
          </CardContent>
        </Card>

        <Button onClick={handlePrint} className="w-full">
          Print / save as PDF
        </Button>
      </div>
    </div>
  );
}
