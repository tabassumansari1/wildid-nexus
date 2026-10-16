import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";

const isWin = process.platform === "win32";
const pugmarkDir = join(process.cwd(), "pugmark");
const pythonBin = isWin
  ? join(pugmarkDir, ".venv", "Scripts", "python.exe")
  : join(pugmarkDir, ".venv", "bin", "python3");

const pythonExec = existsSync(pythonBin) ? pythonBin : (isWin ? "python" : "python3");

console.log(`Starting WILD-ID Nexus on http://127.0.0.1:8000 using ${pythonExec}...`);

const child = spawn(pythonExec, ["manage.py", "runserver", "127.0.0.1:8000"], {
  cwd: pugmarkDir,
  stdio: "inherit",
});

child.on("exit", (code) => process.exit(code || 0));
