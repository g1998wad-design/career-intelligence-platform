"use client";

import { useMemo, useState } from "react";
import type { Job } from "@/types/job";

function scoreColor(score: number): string {
  if (score >= 90) return "text-emerald-700 bg-emerald-50";
  if (score >= 80) return "text-blue-700 bg-blue-50";
  if (score >= 75) return "text-amber-700 bg-amber-50";
  return "text-zinc-700 bg-zinc-100";
}

export default function JobTable({ jobs }: { jobs: Job[] }) {
  const [query, setQuery] = useState("");
  const [minScore, setMinScore] = useState(0);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return jobs.filter((j) => {
      if (j.match_score < minScore) return false;
      if (!q) return true;
      return (
        j.title.toLowerCase().includes(q) ||
        j.company.toLowerCase().includes(q) ||
        (j.location ?? "").toLowerCase().includes(q)
      );
    });
  }, [jobs, query, minScore]);

  return (
    <div className="w-full">
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <input
          type="text"
          placeholder="Search title, company, location..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="flex-1 min-w-[220px] rounded-md border border-zinc-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-400"
        />
        <label className="flex items-center gap-2 text-sm text-zinc-600">
          Min score
          <select
            value={minScore}
            onChange={(e) => setMinScore(Number(e.target.value))}
            className="rounded-md border border-zinc-300 px-2 py-2 text-sm"
          >
            {[0, 75, 80, 85, 90, 95].map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <span className="text-sm text-zinc-500">
          {filtered.length} of {jobs.length} jobs
        </span>
      </div>

      <div className="overflow-x-auto rounded-lg border border-zinc-200">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-zinc-50 text-left text-zinc-600">
              <th className="px-4 py-3 font-medium">Match</th>
              <th className="px-4 py-3 font-medium">Company</th>
              <th className="px-4 py-3 font-medium">Title</th>
              <th className="px-4 py-3 font-medium">Location</th>
              <th className="px-4 py-3 font-medium">Applicants</th>
              <th className="px-4 py-3 font-medium">Resume</th>
              <th className="px-4 py-3 font-medium">Cover Letter</th>
              <th className="px-4 py-3 font-medium">Posting</th>
              <th className="px-4 py-3 font-medium">Direct Apply</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((j) => (
              <tr
                key={j.job_id}
                className="border-t border-zinc-100 hover:bg-zinc-50"
              >
                <td className="px-4 py-3">
                  <span
                    className={`inline-block rounded-full px-2.5 py-1 font-semibold ${scoreColor(
                      j.match_score
                    )}`}
                  >
                    {j.match_score}
                  </span>
                </td>
                <td className="px-4 py-3">{j.company}</td>
                <td className="px-4 py-3">{j.title}</td>
                <td className="px-4 py-3 text-zinc-600">
                  {j.location || "—"}
                </td>
                <td className="px-4 py-3 text-zinc-600">
                  {j.applicant_count ?? "—"}
                </td>
                <td className="px-4 py-3">
                  <a
                    href={`/pdfs/${j.resume_filename}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-600 hover:underline"
                  >
                    Open PDF
                  </a>
                </td>
                <td className="px-4 py-3">
                  {j.cover_letter_filename ? (
                    <a
                      href={`/pdfs/${j.cover_letter_filename}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-600 hover:underline"
                    >
                      Open PDF
                    </a>
                  ) : (
                    <span className="text-zinc-400">—</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <a
                    href={j.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-600 hover:underline"
                  >
                    View posting
                  </a>
                </td>
                <td className="px-4 py-3">
                  {j.has_direct_apply ? (
                    <span className="text-emerald-600">Yes</span>
                  ) : (
                    <span className="text-zinc-400">No (LinkedIn only)</span>
                  )}
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={9} className="px-4 py-8 text-center text-zinc-500">
                  No jobs match your filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
