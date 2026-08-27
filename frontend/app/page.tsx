"use client";

import { DragEvent, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type ViewMode = "rendered" | "markdown" | "text";
type OCRResponse = {
  job_id: string; filename: string; document_type: string; status: string;
  pages: number; processing_time_seconds: number; file_size_bytes: number;
  gpu: { available: boolean; name: string | null; vram_total_gb: number; vram_allocated_gb: number; vram_reserved_gb: number; vram_peak_allocated_gb: number; };
  markdown: string;
};
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<OCRResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const [viewMode, setViewMode] = useState<ViewMode>("rendered");
  const [elapsed, setElapsed] = useState(0);
  const [previewUrl, setPreviewUrl] = useState("");

  useEffect(() => { if (!file) { setPreviewUrl(""); return; } const url = URL.createObjectURL(file); setPreviewUrl(url); return () => URL.revokeObjectURL(url); }, [file]);
  useEffect(() => { if (!loading) return; const start = Date.now(); const timer = setInterval(() => setElapsed((Date.now() - start) / 1000), 100); return () => clearInterval(timer); }, [loading]);

  function selectFile(selected: File | null) { if (!selected) return; const extension = selected.name.split(".").pop()?.toLowerCase(); if (!["png", "jpg", "jpeg", "pdf"].includes(extension || "")) { setError("Supported formats: PNG, JPG, JPEG and PDF"); return; } setFile(selected); setResult(null); setError(""); setElapsed(0); }
  function handleDrop(event: DragEvent<HTMLLabelElement>) { event.preventDefault(); setDragging(false); selectFile(event.dataTransfer.files?.[0] || null); }
  async function handleUpload() { if (!file) return; setLoading(true); setResult(null); setError(""); setElapsed(0); const formData = new FormData(); formData.append("file", file); const started = performance.now(); try { const response = await fetch(`${API_URL}/api/ocr`, { method: "POST", body: formData }); const data = await response.json(); if (!response.ok) throw new Error(data.detail || "OCR failed"); setResult(data); } catch (err) { setError(err instanceof Error ? err.message : "Something went wrong"); } finally { setElapsed((performance.now() - started) / 1000); setLoading(false); } }
  function cleanText(markdown: string) { return markdown.replace(/<\/?PAGE>/gi, "").replace(/#{1,6}\s*/g, "").replace(/\*\*/g, "").replace(/__/g, "").replace(/`{1,3}/g, "").trim(); }
  async function copyResult() { if (!result) return; await navigator.clipboard.writeText(viewMode === "text" ? cleanText(result.markdown) : result.markdown); }
  function download(content: string, extension: string, type: string) { if (!file) return; const baseName = file.name.replace(/\.[^/.]+$/, ""); const blob = new Blob([content], { type }); const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = `${baseName}-ocr.${extension}`; anchor.click(); URL.revokeObjectURL(url); }
  function downloadJson() { if (!result) return; download(JSON.stringify({ job_id: result.job_id, filename: result.filename, document_type: result.document_type, status: result.status, text: cleanText(result.markdown), markdown: result.markdown }, null, 2), "json", "application/json"); }
  function reset() { setFile(null); setResult(null); setError(""); setElapsed(0); setViewMode("rendered"); }

  return <main className="min-h-screen bg-slate-950 text-white">
    <header className="border-b border-slate-800"><div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5"><div><h1 className="text-3xl font-bold">OCRForge</h1><p className="text-sm text-slate-400">Self-hosted GPU document OCR</p></div><div className="flex items-center gap-4"><a href="/history" className="rounded-lg border border-slate-700 px-4 py-2 text-sm hover:bg-slate-800">History</a><div className="flex items-center gap-2 rounded-full border border-emerald-900 bg-emerald-950 px-4 py-2 text-sm text-emerald-300"><span className="h-2 w-2 rounded-full bg-emerald-400" />{result?.gpu?.name ?? "GPU Ready"}</div></div></div></header>
    <div className="mx-auto max-w-7xl px-6 py-8"><div className="grid gap-6 lg:grid-cols-2">
      <section className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900"><div className="border-b border-slate-800 px-6 py-4"><h2 className="font-semibold">Document</h2></div>
      {!file ? <div className="p-6"><label onDragOver={e => {e.preventDefault(); setDragging(true)}} onDragLeave={() => setDragging(false)} onDrop={handleDrop} className={`flex min-h-[500px] cursor-pointer items-center justify-center rounded-xl border-2 border-dashed p-8 text-center transition ${dragging ? "border-blue-400 bg-blue-950/30" : "border-slate-700 hover:border-slate-500"}`}><input type="file" className="hidden" accept=".png,.jpg,.jpeg,.pdf" onChange={e => selectFile(e.target.files?.[0] || null)} /><div><div className="text-5xl">＋</div><p className="mt-4 text-lg font-medium">Drop a document here</p><p className="mt-2 text-sm text-slate-500">or click to choose a file</p><p className="mt-6 text-xs text-slate-600">PNG • JPG • JPEG • PDF</p></div></label></div> : <><div className="bg-slate-950 p-4">{previewUrl ? file.type === "application/pdf" ? <iframe src={previewUrl} title="PDF preview" className="h-[500px] w-full rounded-lg bg-white" /> : <div className="flex h-[500px] items-center justify-center"><img src={previewUrl} alt="Document preview" className="max-h-full max-w-full rounded-lg object-contain" /></div> : <div className="flex h-[500px] items-center justify-center text-slate-500">Preparing preview...</div>}</div><div className="border-t border-slate-800 p-5"><div className="flex items-center justify-between gap-4"><div className="min-w-0"><p className="truncate font-medium">{file.name}</p><p className="mt-1 text-sm text-slate-500">{(file.size / 1024 / 1024).toFixed(2)} MB</p></div><button onClick={reset} disabled={loading} className="rounded-lg border border-slate-700 px-3 py-2 text-sm hover:bg-slate-800 disabled:opacity-50">Change</button></div><button onClick={handleUpload} disabled={loading} className="mt-5 w-full rounded-xl bg-white px-4 py-3 font-semibold text-black disabled:opacity-50">{loading ? `Processing ${elapsed.toFixed(1)}s` : "Run OCR"}</button>{error && <p className="mt-4 text-sm text-red-400">{error}</p>}</div></>}
      </section>
      <section className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900"><div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-6 py-4"><h2 className="font-semibold">OCR Result</h2>{result && <div className="flex gap-2"><button onClick={copyResult} className="rounded-lg border border-slate-700 px-3 py-2 text-xs">Copy</button><button onClick={() => download(result.markdown,"md","text/markdown")} className="rounded-lg border border-slate-700 px-3 py-2 text-xs">MD</button><button onClick={() => download(cleanText(result.markdown),"txt","text/plain")} className="rounded-lg border border-slate-700 px-3 py-2 text-xs">TXT</button><button onClick={downloadJson} className="rounded-lg border border-slate-700 px-3 py-2 text-xs">JSON</button></div>}</div>
      {result && <div className="flex border-b border-slate-800 px-4 pt-3">{(["rendered","markdown","text"] as ViewMode[]).map(mode => <button key={mode} onClick={() => setViewMode(mode)} className={`border-b-2 px-4 py-3 text-sm capitalize ${viewMode === mode ? "border-blue-400 text-white" : "border-transparent text-slate-500"}`}>{mode}</button>)}</div>}
      <div className="h-[650px] overflow-auto bg-slate-950 p-6">{loading ? <div className="flex h-full items-center justify-center"><div className="text-center"><div className="mx-auto h-10 w-10 animate-spin rounded-full border-4 border-slate-700 border-t-blue-400"/><p className="mt-5 text-slate-300">Processing document on GPU</p><p className="mt-2 font-mono text-sm text-slate-500">{elapsed.toFixed(1)} seconds</p></div></div> : result ? <>{viewMode === "rendered" && <article className="prose prose-invert max-w-none whitespace-pre-wrap"><ReactMarkdown remarkPlugins={[remarkGfm]}>{result.markdown.replace(/<\/?PAGE>/gi, "")}</ReactMarkdown></article>}{viewMode === "markdown" && <pre className="whitespace-pre-wrap font-mono text-sm text-slate-300">{result.markdown}</pre>}{viewMode === "text" && <pre className="whitespace-pre-wrap font-sans text-sm leading-7 text-slate-300">{cleanText(result.markdown)}</pre>}</> : <div className="flex h-full items-center justify-center text-center text-slate-600"><div><p className="text-lg">No OCR result yet</p><p className="mt-2 text-sm">Upload a document and run OCR.</p></div></div>}</div>
      {result && <div className="border-t border-slate-800 px-6 py-4 text-xs text-slate-500"><div className="flex flex-wrap gap-x-6 gap-y-2"><span>✓ Completed</span><span>{result.pages} {result.pages === 1 ? "page" : "pages"}</span><span>{result.processing_time_seconds.toFixed(1)} sec</span><span>{result.document_type.toUpperCase()}</span><span>GPU {result.gpu.vram_peak_allocated_gb.toFixed(2)} GB peak</span><span className="font-mono">{result.job_id.slice(0,8)}</span></div></div>}
      </section>
    </div></div>
  </main>;
}
