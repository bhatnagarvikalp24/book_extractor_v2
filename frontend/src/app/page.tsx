"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "";
const POLL_INTERVAL_MS = 1500;
const MAX_FILES = 50;

// ── types ─────────────────────────────────────────────────────────────────────

type JobStatus = "queued" | "running" | "done" | "failed";

interface JobState {
  status: JobStatus;
  total_files: number;
  processed_files: number;
}

interface EvidenceItem {
  text: string;
  page: number;
}

interface FileResult {
  file_name: string;
  title: string | null;
  author: string | null;
  publisher: string | null;
  isbn: string | null;
  copyright_holder: "publisher" | "author" | "unknown";
  confidence: number;
  needs_review: boolean;
  llm_used: boolean;
  evidence: {
    title?: EvidenceItem;
    author?: EvidenceItem;
    publisher?: EvidenceItem;
    isbn?: EvidenceItem;
    copyright?: EvidenceItem;
  };
  error: string | null;
}

// ── small helpers ─────────────────────────────────────────────────────────────

function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color =
    pct >= 75
      ? "bg-emerald-100 text-emerald-800"
      : pct >= 50
      ? "bg-amber-100 text-amber-800"
      : "bg-rose-100 text-rose-800";
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${color}`}>
      {pct}%
    </span>
  );
}

function BoolBadge({ value, trueLabel = "Yes", falseLabel = "No" }: { value: boolean; trueLabel?: string; falseLabel?: string }) {
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
        value ? "bg-violet-100 text-violet-800" : "bg-slate-100 text-slate-500"
      }`}
    >
      {value ? trueLabel : falseLabel}
    </span>
  );
}

function Cell({ value }: { value: string | null | undefined }) {
  if (!value) return <span className="text-slate-300 text-xs italic">—</span>;
  return <span className="text-sm">{value}</span>;
}

// ── upload zone ───────────────────────────────────────────────────────────────

function UploadZone({
  onSubmit,
  uploading,
}: {
  onSubmit: (files: File[]) => void;
  uploading: boolean;
}) {
  const [files, setFiles] = useState<File[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const addFiles = (incoming: FileList | null) => {
    if (!incoming) return;
    const pdfs = Array.from(incoming).filter((f) =>
      f.name.toLowerCase().endsWith(".pdf")
    );
    setFiles((prev) => {
      const names = new Set(prev.map((f) => f.name));
      const unique = pdfs.filter((f) => !names.has(f.name));
      return [...prev, ...unique].slice(0, MAX_FILES);
    });
  };

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      addFiles(e.dataTransfer.files);
    },
    []
  );

  const removeFile = (name: string) =>
    setFiles((prev) => prev.filter((f) => f.name !== name));

  const canSubmit = files.length > 0 && !uploading;

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="text-center">
        <h1 className="text-3xl font-bold text-slate-800">PDF Book Metadata Extractor</h1>
        <p className="mt-2 text-slate-500">
          Upload up to {MAX_FILES} PDFs. Metadata is extracted automatically — no data is
          stored permanently.
        </p>
      </div>

      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`
          border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors
          ${dragOver
            ? "border-violet-400 bg-violet-50"
            : "border-slate-300 hover:border-violet-300 hover:bg-slate-100"}
        `}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf"
          multiple
          className="hidden"
          onChange={(e) => addFiles(e.target.files)}
        />
        <div className="text-5xl mb-3 select-none">📄</div>
        <p className="text-slate-600 font-medium">
          Drag &amp; drop PDFs here, or click to browse
        </p>
        <p className="text-slate-400 text-sm mt-1">
          Max {MAX_FILES} files &bull; 300 MB each &bull; PDF only
        </p>
      </div>

      {/* File list */}
      {files.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 divide-y divide-slate-100 max-h-64 overflow-y-auto">
          {files.map((f) => (
            <div key={f.name} className="flex items-center justify-between px-4 py-2 text-sm">
              <span className="truncate text-slate-700 max-w-[80%]">{f.name}</span>
              <div className="flex items-center gap-3 shrink-0 ml-2">
                <span className="text-slate-400 text-xs">
                  {(f.size / 1024 / 1024).toFixed(1)} MB
                </span>
                <button
                  onClick={(e) => { e.stopPropagation(); removeFile(f.name); }}
                  className="text-rose-400 hover:text-rose-600 font-bold leading-none"
                >
                  ×
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between">
        <span className="text-sm text-slate-500">
          {files.length} / {MAX_FILES} files selected
        </span>
        <button
          disabled={!canSubmit}
          onClick={() => onSubmit(files)}
          className={`px-6 py-2.5 rounded-lg font-semibold text-white transition-colors ${
            canSubmit
              ? "bg-violet-600 hover:bg-violet-700"
              : "bg-slate-300 cursor-not-allowed"
          }`}
        >
          {uploading ? "Uploading…" : "Extract Metadata"}
        </button>
      </div>
    </div>
  );
}

// ── progress view ─────────────────────────────────────────────────────────────

function ProgressView({ jobId, jobState }: { jobId: string; jobState: JobState | null }) {
  const pct =
    jobState && jobState.total_files > 0
      ? Math.round((jobState.processed_files / jobState.total_files) * 100)
      : 0;

  return (
    <div className="max-w-lg mx-auto text-center space-y-6">
      <h2 className="text-2xl font-bold text-slate-800">Processing PDFs…</h2>
      <p className="text-slate-500 text-sm font-mono break-all">Job: {jobId}</p>

      <div className="bg-white rounded-xl border border-slate-200 p-6 space-y-4">
        <div className="flex justify-between text-sm text-slate-600">
          <span>
            {jobState?.processed_files ?? 0} / {jobState?.total_files ?? "?"} files
          </span>
          <span>{pct}%</span>
        </div>
        <div className="w-full bg-slate-100 rounded-full h-3">
          <div
            className="bg-violet-500 h-3 rounded-full transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
        <p className="text-xs text-slate-400 capitalize">
          Status: {jobState?.status ?? "queued"}
        </p>
      </div>

      <p className="text-slate-400 text-xs animate-pulse">
        Polling every {POLL_INTERVAL_MS / 1000}s…
      </p>
    </div>
  );
}

// ── results table ─────────────────────────────────────────────────────────────

function ResultsTable({
  results,
  jobId,
}: {
  results: FileResult[];
  jobId: string;
}) {
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const [filterReview, setFilterReview] = useState(false);

  const download = (format: "csv" | "json") => {
    window.open(`${API}/extract/${jobId}/export?format=${format}`, "_blank");
  };

  const displayed = filterReview ? results.filter((r) => r.needs_review) : results;

  return (
    <div className="space-y-4">
      {/* Header row */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Results</h2>
          <p className="text-slate-500 text-sm">
            {results.length} file{results.length !== 1 ? "s" : ""} processed
          </p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={filterReview}
              onChange={(e) => setFilterReview(e.target.checked)}
              className="accent-violet-600"
            />
            Show needs_review only
          </label>
          <button
            onClick={() => download("csv")}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold rounded-lg transition-colors"
          >
            Export CSV
          </button>
          <button
            onClick={() => download("json")}
            className="px-4 py-2 bg-slate-700 hover:bg-slate-800 text-white text-sm font-semibold rounded-lg transition-colors"
          >
            Export JSON
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-slate-200">
        <table className="min-w-full text-sm bg-white">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200 text-slate-600 text-xs uppercase tracking-wide">
              <th className="px-3 py-3 text-left">File</th>
              <th className="px-3 py-3 text-left">Title</th>
              <th className="px-3 py-3 text-left">Author</th>
              <th className="px-3 py-3 text-left">Publisher</th>
              <th className="px-3 py-3 text-left">ISBN</th>
              <th className="px-3 py-3 text-left">Copyright</th>
              <th className="px-3 py-3 text-left">Conf.</th>
              <th className="px-3 py-3 text-left">LLM</th>
              <th className="px-3 py-3 text-left">Review</th>
              <th className="px-3 py-3 text-left">Info</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {displayed.map((row) => (
              <>
                <tr
                  key={row.file_name}
                  className={`hover:bg-slate-50 transition-colors ${
                    row.error ? "bg-rose-50" : ""
                  }`}
                >
                  <td className="px-3 py-2.5 max-w-[160px]">
                    <span
                      className="block truncate font-medium text-slate-700"
                      title={row.file_name}
                    >
                      {row.file_name}
                    </span>
                    {row.error && (
                      <span className="block text-rose-500 text-xs truncate" title={row.error}>
                        {row.error}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 max-w-[180px]">
                    <span className="block truncate" title={row.title ?? ""}>
                      <Cell value={row.title} />
                    </span>
                  </td>
                  <td className="px-3 py-2.5 max-w-[140px]">
                    <span className="block truncate" title={row.author ?? ""}>
                      <Cell value={row.author} />
                    </span>
                  </td>
                  <td className="px-3 py-2.5 max-w-[160px]">
                    <span className="block truncate" title={row.publisher ?? ""}>
                      <Cell value={row.publisher} />
                    </span>
                  </td>
                  <td className="px-3 py-2.5 font-mono text-xs">
                    <Cell value={row.isbn} />
                  </td>
                  <td className="px-3 py-2.5 capitalize text-xs">
                    <Cell value={row.copyright_holder} />
                  </td>
                  <td className="px-3 py-2.5">
                    <ConfidenceBadge value={row.confidence} />
                  </td>
                  <td className="px-3 py-2.5">
                    <BoolBadge value={row.llm_used} trueLabel="Yes" falseLabel="No" />
                  </td>
                  <td className="px-3 py-2.5">
                    <BoolBadge value={row.needs_review} trueLabel="Yes" falseLabel="No" />
                  </td>
                  <td className="px-3 py-2.5">
                    <button
                      onClick={() =>
                        setExpandedRow(
                          expandedRow === row.file_name ? null : row.file_name
                        )
                      }
                      className="text-violet-500 hover:text-violet-700 text-xs underline"
                    >
                      {expandedRow === row.file_name ? "Hide" : "Evidence"}
                    </button>
                  </td>
                </tr>

                {/* Evidence drawer */}
                {expandedRow === row.file_name && (
                  <tr key={`${row.file_name}-ev`} className="bg-violet-50">
                    <td colSpan={10} className="px-4 py-3">
                      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 text-xs">
                        {Object.entries(row.evidence || {}).map(([field, ev]) =>
                          ev ? (
                            <div key={field} className="bg-white rounded-lg border border-violet-100 p-3">
                              <p className="font-semibold text-violet-700 capitalize mb-1">
                                {field}{" "}
                                <span className="font-normal text-slate-400">(p.{ev.page})</span>
                              </p>
                              <p className="text-slate-600 break-words">{ev.text}</p>
                            </div>
                          ) : null
                        )}
                        {Object.keys(row.evidence || {}).length === 0 && (
                          <p className="text-slate-400 italic">No evidence recorded.</p>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </>
            ))}
            {displayed.length === 0 && (
              <tr>
                <td colSpan={10} className="text-center py-10 text-slate-400 text-sm">
                  No results to display.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── main page ─────────────────────────────────────────────────────────────────

type PageView = "upload" | "processing" | "results" | "error";

export default function HomePage() {
  const [view, setView] = useState<PageView>("upload");
  const [uploading, setUploading] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobState, setJobState] = useState<JobState | null>(null);
  const [results, setResults] = useState<FileResult[]>([]);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const startPolling = useCallback((id: string) => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${API}/extract/${id}/status`);
        if (!res.ok) throw new Error(`Status ${res.status}`);
        const data: JobState = await res.json();
        setJobState(data);

        if (data.status === "done" || data.status === "failed") {
          stopPolling();
          // Fetch results
          const rRes = await fetch(`${API}/extract/${id}/results`);
          if (rRes.ok) {
            const rData = await rRes.json();
            setResults(rData.results ?? []);
          }
          setView(data.status === "done" ? "results" : "error");
        }
      } catch (e) {
        console.error("Polling error:", e);
      }
    }, POLL_INTERVAL_MS);
  }, []);

  useEffect(() => () => stopPolling(), []);

  const handleUpload = async (files: File[]) => {
    setUploading(true);
    setErrorMsg(null);
    try {
      const form = new FormData();
      for (const f of files) form.append("files", f);

      const res = await fetch(`${API}/extract`, { method: "POST", body: form });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Upload failed" }));
        throw new Error(err.detail || "Upload failed");
      }
      const data: { job_id: string } = await res.json();
      setJobId(data.job_id);
      setJobState(null);
      setResults([]);
      setView("processing");
      startPolling(data.job_id);
    } catch (e: unknown) {
      setErrorMsg(e instanceof Error ? e.message : "Unknown error");
      setView("error");
    } finally {
      setUploading(false);
    }
  };

  const reset = () => {
    stopPolling();
    setView("upload");
    setJobId(null);
    setJobState(null);
    setResults([]);
    setErrorMsg(null);
  };

  return (
    <main className="min-h-screen p-6 md:p-12">
      {/* Navigation breadcrumb */}
      {view !== "upload" && (
        <div className="max-w-7xl mx-auto mb-6">
          <button
            onClick={reset}
            className="text-sm text-violet-600 hover:text-violet-800 underline"
          >
            ← New upload
          </button>
        </div>
      )}

      <div className={`mx-auto ${view === "results" ? "max-w-7xl" : "max-w-2xl"}`}>
        {view === "upload" && (
          <UploadZone onSubmit={handleUpload} uploading={uploading} />
        )}

        {view === "processing" && jobId && (
          <ProgressView jobId={jobId} jobState={jobState} />
        )}

        {view === "results" && jobId && (
          <ResultsTable results={results} jobId={jobId} />
        )}

        {view === "error" && (
          <div className="text-center space-y-4">
            <div className="text-5xl">⚠️</div>
            <h2 className="text-2xl font-bold text-slate-800">Something went wrong</h2>
            <p className="text-rose-600 text-sm">{errorMsg ?? "Job failed unexpectedly."}</p>
            <button
              onClick={reset}
              className="px-5 py-2.5 bg-violet-600 hover:bg-violet-700 text-white rounded-lg font-semibold transition-colors"
            >
              Try Again
            </button>
          </div>
        )}
      </div>
    </main>
  );
}
