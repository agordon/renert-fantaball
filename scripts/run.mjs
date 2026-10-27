// Cross-platform launcher: node scripts/run.mjs <setup|dev|prod|test>
// Starts the Flask API (port 5010) and the Next.js frontend (port 3000) together. No extra dependencies.
import { spawn, spawnSync } from "node:child_process";
import { existsSync, copyFileSync } from "node:fs";
import { dirname, join } from "node:path";
import net from "node:net";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const frontend = join(root, "frontend");
const win = process.platform === "win32";
const venvPython = join(root, ".venv", win ? "Scripts/python.exe" : "bin/python");
const python = existsSync(venvPython) ? venvPython : win ? "python" : "python3";
const npm = win ? "npm.cmd" : "npm";
const mode = process.argv[2];

const run = (cmd, args, opts = {}) => spawnSync(cmd, args, { stdio: "inherit", shell: win && cmd.endsWith(".cmd"), ...opts });

function setup() {
  if (!existsSync(venvPython)) run(win ? "python" : "python3", ["-m", "venv", ".venv"], { cwd: root });
  run(venvPython, ["-m", "pip", "install", "-q", "-r", "requirements.txt", "-r", "requirements-dev.txt"], { cwd: root });
  if (!existsSync(join(root, ".env"))) copyFileSync(join(root, ".env.development.example"), join(root, ".env"));
  run(npm, ["install"], { cwd: frontend });
}

const portBusy = (port) => new Promise((res) => {
  const s = net.connect(port, "127.0.0.1");
  s.on("connect", () => { s.destroy(); res(true); });
  s.on("error", () => res(false));
});

async function serve(extraEnv, frontendArgs) {
  for (const port of [5010, 3000]) {
    if (await portBusy(port)) {
      console.error(`
Port ${port} is already in use by another program (maybe an old dev server). Close it and run again.`);
      process.exit(1);
    }
  }
  const procs = [
    spawn(python, ["-m", "flask", "--app", "app", "run", "--host", "127.0.0.1", "--port", "5010"], { cwd: root, stdio: "inherit", env: { ...process.env, ...extraEnv } }),
    spawn(npm, ["run", ...frontendArgs], { cwd: frontend, stdio: "inherit", shell: win }),
  ];
  console.log("\nFantaBall app: http://localhost:3000  (the API on :5010 has no pages - always use :3000)  Ctrl+C to stop\n");
  setTimeout(() => {
    const url = "http://localhost:3000";
    if (win) spawn("cmd", ["/c", "start", "", url], { stdio: "ignore" });
    else spawn(process.platform === "darwin" ? "open" : "xdg-open", [url], { stdio: "ignore" }).on("error", () => {});
  }, 6000);
  const stop = () => procs.forEach((p) => { try { win ? spawnSync("taskkill", ["/pid", String(p.pid), "/T", "/F"]) : p.kill(); } catch {} });
  process.on("SIGINT", () => { stop(); process.exit(0); });
  process.on("exit", stop);
  procs.forEach((p) => p.on("exit", (code) => { if (code) { stop(); process.exit(code); } }));
}

if (mode === "setup") setup();
else if (mode === "dev") await serve({ FLASK_DEBUG: "true" }, ["dev"]);
else if (mode === "prod") {
  const b = run(npm, ["run", "build"], { cwd: frontend });
  if (b.status) process.exit(b.status);
  await serve({ FLASK_DEBUG: "false" }, ["start"]);
} else if (mode === "test") {
  const r = run(python, ["-m", "pytest", "tests", "-q"], { cwd: root });
  const t = run(npm, ["run", "build"], { cwd: frontend });
  process.exit(r.status || t.status || 0);
} else if (mode === "nba") {
  // npm run sync | sync:daily | sync:status ...  ->  python -m flask --app app nba <command>
  const r = run(python, ["-m", "flask", "--app", "app", "nba", ...process.argv.slice(3)], { cwd: root });
  process.exit(r.status ?? 1);
} else { console.log("Usage: npm run <setup|dev|prod|test|sync|sync:daily|sync:status>"); process.exit(1); }
