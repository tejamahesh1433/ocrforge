"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const API_URL = "http://localhost:8001";

type Job = {
  job_id: string;
  filename: string;
  document_type: string;
  status: string;
  pages: number | null;
  processing_time_seconds: number | null;
  file_size_bytes: number | null;
  gpu: {
    name: string | null;
    vram_total_gb: number | null;
    vram_peak_allocated_gb: number | null;
  };
  error_message: string | null;
  created_at: string | null;
  completed_at: string | null;
  markdown?: string | null;
};

export default function HistoryPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadJobs() {
    setLoading(true);
    setError("");

    try {
      const response = await fetch(`${API_URL}/api/jobs`);

      if (!response.ok) {
        throw new Error("Unable to load OCR history");
      }

      const data = await response.json();
      setJobs(data.jobs);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load history"
      );
    } finally {
      setLoading(false);
    }
  }

  async function openJob(jobId: string) {
    setDetailLoading(true);
    setError("");

    try {
      const response = await fetch(`${API_URL}/api/jobs/${jobId}`);

      if (!response.ok) {
        throw new Error("Unable to load OCR job");
      }

      const data = await response.json();
      setSelectedJob(data);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load job"
      );
    } finally {
      setDetailLoading(false);
    }
  }

  async function deleteJob(jobId: string) {
    const confirmed = window.confirm(
      "Delete this OCR job and its stored files?"
    );

    if (!confirmed) return;

    try {
      const response = await fetch(`${API_URL}/api/jobs/${jobId}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        throw new Error("Unable to delete OCR job");
      }

      if (selectedJob?.job_id === jobId) {
        setSelectedJob(null);
      }

      await loadJobs();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to delete job"
      );
    }
  }

  useEffect(() => {
    loadJobs();
  }, []);

  function formatDate(value: string | null) {
    if (!value) return "-";

    return new Date(value).toLocaleString();
  }

  function formatSize(bytes: number | null) {
    if (!bytes) return "-";

    if (bytes < 1024 * 1024) {
      return `${(bytes / 1024).toFixed(1)} KB`;
    }

    return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
  }

  return (
    <main className="min-h-screen bg-slate-950 text-white">
      <header className="border-b border-slate-800">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
          <div>
            <h1 className="text-3xl font-bold">OCRForge</h1>
            <p className="text-sm text-slate-400">
              OCR processing history
            </p>
          </div>

          <a
            href="/"
            className="rounded-lg border border-slate-700 px-4 py-2 text-sm hover:bg-slate-800"
          >
            New OCR
          </a>
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-6 py-8">
        {error && (
          <div className="mb-6 rounded-xl border border-red-900 bg-red-950/40 p-4 text-red-300">
            {error}
          </div>
        )}

        <div className="grid gap-6 lg:grid-cols-[420px_1fr]">
          <section className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900">
            <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
              <div>
                <h2 className="font-semibold">History</h2>
                <p className="text-xs text-slate-500">
                  {jobs.length} saved jobs
                </p>
              </div>

              <button
                onClick={loadJobs}
                className="rounded-lg border border-slate-700 px-3 py-2 text-xs hover:bg-slate-800"
              >
                Refresh
              </button>
            </div>

            <div className="max-h-[720px] overflow-auto">
              {loading ? (
                <p className="p-6 text-slate-500">Loading history...</p>
              ) : jobs.length === 0 ? (
                <p className="p-6 text-slate-500">
                  No OCR jobs yet.
                </p>
              ) : (
                jobs.map((job) => (
                  <div
                    key={job.job_id}
                    className={`border-b border-slate-800 p-4 ${
                      selectedJob?.job_id === job.job_id
                        ? "bg-slate-800"
                        : "hover:bg-slate-800/50"
                    }`}
                  >
                    <button
                      onClick={() => openJob(job.job_id)}
                      className="w-full text-left"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <p className="truncate font-medium">
                          {job.filename}
                        </p>

                        <span
                          className={`rounded-full px-2 py-1 text-xs ${
                            job.status === "completed"
                              ? "bg-emerald-950 text-emerald-300"
                              : job.status === "failed"
                              ? "bg-red-950 text-red-300"
                              : "bg-yellow-950 text-yellow-300"
                          }`}
                        >
                          {job.status}
                        </span>
                      </div>

                      <div className="mt-3 flex flex-wrap gap-3 text-xs text-slate-500">
                        <span>
                          {job.pages ?? "-"}{" "}
                          {job.pages === 1 ? "page" : "pages"}
                        </span>

                        <span>
                          {job.processing_time_seconds
                            ? `${job.processing_time_seconds.toFixed(1)} sec`
                            : "-"}
                        </span>

                        <span>{job.document_type.toUpperCase()}</span>
                      </div>

                      <p className="mt-2 text-xs text-slate-600">
                        {formatDate(job.created_at)}
                      </p>
                    </button>

                    <button
                      onClick={() => deleteJob(job.job_id)}
                      className="mt-3 text-xs text-red-400 hover:text-red-300"
                    >
                      Delete
                    </button>
                  </div>
                ))
              )}
            </div>
          </section>

          <section className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900">
            {!selectedJob ? (
              <div className="flex min-h-[720px] items-center justify-center text-center text-slate-600">
                <div>
                  <p className="text-lg">Select an OCR job</p>
                  <p className="mt-2 text-sm">
                    Saved OCR results will appear here.
                  </p>
                </div>
              </div>
            ) : detailLoading ? (
              <div className="flex min-h-[720px] items-center justify-center text-slate-500">
                Loading OCR result...
              </div>
            ) : (
              <>
                <div className="border-b border-slate-800 px-6 py-5">
                  <h2 className="text-xl font-semibold">
                    {selectedJob.filename}
                  </h2>

                  <div className="mt-3 flex flex-wrap gap-x-6 gap-y-2 text-xs text-slate-500">
                    <span>
                      {selectedJob.pages ?? "-"}{" "}
                      {selectedJob.pages === 1 ? "page" : "pages"}
                    </span>

                    <span>
                      {selectedJob.processing_time_seconds
                        ? `${selectedJob.processing_time_seconds.toFixed(2)} sec`
                        : "-"}
                    </span>

                    <span>
                      {formatSize(selectedJob.file_size_bytes)}
                    </span>

                    <span>
                      Peak GPU{" "}
                      {selectedJob.gpu.vram_peak_allocated_gb ?? "-"} GB
                    </span>

                    <span className="font-mono">
                      {selectedJob.job_id.slice(0, 8)}
                    </span>
                  </div>
                </div>

                <div className="max-h-[650px] overflow-auto bg-slate-950 p-6">
                  {selectedJob.markdown ? (
                    <article className="prose prose-invert max-w-none whitespace-pre-wrap">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {selectedJob.markdown.replace(/<\/?PAGE>/gi, "")}
                      </ReactMarkdown>
                    </article>
                  ) : (
                    <p className="text-slate-500">
                      No OCR result stored for this job.
                    </p>
                  )}
                </div>
              </>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
