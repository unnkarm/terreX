import Link from "next/link";

export default function NotFound() {
  return (
    <main className="min-h-screen bg-black text-white flex items-center justify-center px-6">
      <div className="max-w-md space-y-5 text-center">
        <p className="font-mono text-xs uppercase tracking-widest text-neutral-500">
          404 / route not found
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">Nothing here yet.</h1>
        <p className="text-sm leading-6 text-neutral-400">
          The page you requested is not available in this TerreX workspace.
        </p>
        <Link
          href="/workspace"
          className="inline-flex items-center justify-center rounded border border-neutral-700 px-4 py-2 text-xs font-semibold uppercase tracking-widest text-neutral-200 hover:border-neutral-400 hover:text-white"
        >
          Open workspace
        </Link>
      </div>
    </main>
  );
}
