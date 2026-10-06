import JobTable from "@/components/JobTable";
import jobsData from "../../data/jobs.json";
import type { Job } from "@/types/job";

const jobs = jobsData as Job[];

export default function Home() {
  return (
    <div className="min-h-screen bg-white px-6 py-10">
      <div className="mx-auto max-w-6xl">
        <h1 className="text-2xl font-semibold text-zinc-900">
          Tailored Resumes
        </h1>
        <p className="mt-1 text-sm text-zinc-500">
          {jobs.length} AI-tailored resumes, sorted by match score. Generated
          by a Python/SQLite pipeline that scores, tailors, and writes cover
          letters for scraped job postings.
        </p>
        <div className="mt-6">
          <JobTable jobs={jobs} />
        </div>
      </div>
    </div>
  );
}
