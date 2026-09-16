export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-6 px-6 text-center">
      <p className="text-sm font-medium text-muted-foreground">
        Excel → SQL → Power BI → Python → Statistics → Business Analytics
      </p>
      <h1 className="max-w-2xl text-4xl font-semibold tracking-tight sm:text-5xl">
        Learn Data Analytics by doing.
      </h1>
      <p className="max-w-xl text-lg text-muted-foreground">
        Theory, hands-on exercises, an in-browser SQL sandbox and real projects — one path
        from zero to job-ready Junior Data Analyst.
      </p>
    </main>
  );
}
