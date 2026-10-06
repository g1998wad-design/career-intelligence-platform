export interface Job {
  job_id: string;
  title: string;
  company: string;
  location: string | null;
  match_score: number;
  applicant_count: number | null;
  url: string;
  apply_url: string | null;
  has_direct_apply: boolean;
  resume_filename: string;
  cover_letter_filename: string | null;
  processed_at: string | null;
}
