/**
 * CreatePage — stub placeholder.
 * Actual content (Express generators: song ideas, practice plans, reflections)
 * lands in US-6.
 */
export default function CreatePage(): React.ReactElement {
  return (
    <div className="flex min-h-screen flex-col bg-[#0F172A] pb-24">
      <header className="border-b border-slate-700 px-4 py-3">
        <h1 className="text-lg font-semibold text-slate-100">Create</h1>
      </header>
      <main className="flex flex-1 items-center justify-center">
        <p className="text-sm text-slate-500">Express generators coming in US-6.</p>
      </main>
    </div>
  );
}
