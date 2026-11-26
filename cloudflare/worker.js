// Fantasy bot on Cloudflare: serves the dashboard (static files in ../site) and fires the
// GitHub workflows on time. GitHub's own cron runs hours late on quiet repos; Cloudflare
// cron triggers fire within about a minute.
// Settings (wrangler.toml [vars]): REPO = "owner/repo", BRANCH = the repo's default branch.
// Worker secrets:
//   GH_TOKEN  fine-grained GitHub token, this repo only: Actions read/write, Contents read
//   VIEW_KEY  the secret-link key (see fetch below)
const ghHeaders = (token, accept) => ({
  Authorization: `Bearer ${token}`,
  Accept: accept,
  "User-Agent": "fantasy-bot-trigger",
  "X-GitHub-Api-Version": "2022-11-28",
});

const BY_CRON = {
  "0 7 * * *": "daily.yml",      // 15:00 Manila: main report
  "0 23 * * *": "check.yml",     // 07:00 Manila: pre-game lineup check
  "*/20 0-5 * * *": "watch.yml", // 08:00-13:40 Manila: injury watch during games
};

// Latest report, pushed by daily.yml to the "report" branch of the private repo.
async function report(env) {
  const r = await fetch(`https://api.github.com/repos/${env.REPO}/contents/report.json?ref=report`, {
    headers: ghHeaders(env.GH_TOKEN, "application/vnd.github.raw+json"),
  });
  if (!r.ok) return new Response("{}", { status: 404, headers: { "Content-Type": "application/json" } });
  return new Response(r.body, { headers: { "Content-Type": "application/json" } });
}

// The page itself, straight from the repo, so a pushed change to site/index.html goes live
// without redeploying the Worker. Falls back to the copy bundled at deploy time.
async function page(env, request, url) {
  const r = await fetch(`https://api.github.com/repos/${env.REPO}/contents/site/index.html?ref=${env.BRANCH || "master"}`, {
    headers: ghHeaders(env.GH_TOKEN, "application/vnd.github.raw+json"),
  });
  if (r.ok) return new Response(r.body, { headers: { "Content-Type": "text/html; charset=utf-8" } });
  return env.ASSETS.fetch(new Request(url, request));
}

async function dispatch(workflow, env) {
  const r = await fetch(`https://api.github.com/repos/${env.REPO}/actions/workflows/${workflow}/dispatches`, {
    method: "POST",
    headers: ghHeaders(env.GH_TOKEN, "application/vnd.github+json"),
    body: JSON.stringify({ ref: env.BRANCH || "master" }),
  });
  if (r.status !== 204) throw new Error(`${workflow}: GitHub said ${r.status} ${await r.text()}`);
}

export default {
  async scheduled(event, env, ctx) {
    const wf = BY_CRON[event.cron];
    if (wf) ctx.waitUntil(dispatch(wf, env));
  },
  // The dashboard is private by secret link: /?k=<VIEW_KEY> (built into the push's
  // "Open report" button) sets a cookie; requests without the key or cookie get a 404.
  async fetch(request, env) {
    const url = new URL(request.url);
    const key = env.VIEW_KEY;
    const cookie = (request.headers.get("Cookie") || "").match(/(?:^|;\s*)fb=([^;]+)/);
    const viaLink = key && url.searchParams.get("k") === key;
    const viaCookie = key && cookie && cookie[1] === key;
    if (!viaLink && !viaCookie) return new Response("Not found", { status: 404 });

    url.search = "";
    const res = url.pathname === "/report.json" ? await report(env)
      : url.pathname === "/" || url.pathname === "/index.html" ? await page(env, request, url)
      : await env.ASSETS.fetch(new Request(url, request));
    const out = new Response(res.body, res);
    out.headers.set("Cache-Control", "no-store");
    out.headers.set("X-Robots-Tag", "noindex");
    out.headers.set("Referrer-Policy", "no-referrer");
    if (viaLink) {
      out.headers.append("Set-Cookie", `fb=${key}; Path=/; Max-Age=31536000; Secure; HttpOnly; SameSite=Lax`);
    }
    return out;
  },
};
