import { spawn } from "node:child_process";
import { once } from "node:events";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repositoryRoot = fileURLToPath(new URL("../", import.meta.url));
const apiRequire = createRequire(new URL("../apps/api/package.json", import.meta.url));
const webRequire = createRequire(new URL("../apps/web/package.json", import.meta.url));
const tsxCli = apiRequire.resolve("tsx/cli");
const viteCli = resolve(dirname(webRequire.resolve("vite/package.json")), "bin/vite.js");

const definitions = [
  {
    name: "api",
    arguments: [tsxCli, "watch", "apps/api/src/main.ts"],
  },
  {
    name: "web",
    arguments: [viteCli, "--config", "apps/web/vite.config.ts"],
  },
];

const children = definitions.map(({ name, arguments: commandArguments }) => ({
  name,
  process: spawn(process.execPath, commandArguments, {
    cwd: repositoryRoot,
    env: process.env,
    stdio: "inherit",
    windowsHide: true,
  }),
}));

let finishing = false;

const stopChild = async (child) => {
  if (child.exitCode !== null || child.signalCode !== null || child.pid === undefined) {
    return;
  }

  if (process.platform === "win32") {
    const taskkill = spawn("taskkill.exe", ["/PID", String(child.pid), "/T", "/F"], {
      stdio: "ignore",
      windowsHide: true,
    });

    const result = await new Promise((resolveResult) => {
      const timeout = setTimeout(() => resolveResult(1), 3_000);
      const complete = (code) => {
        clearTimeout(timeout);
        resolveResult(code ?? 1);
      };

      taskkill.once("exit", complete);
      taskkill.once("error", () => complete(1));
    });

    if (result !== 0 && child.exitCode === null && child.signalCode === null) {
      child.kill("SIGKILL");
    }
    return;
  }

  child.kill("SIGTERM");

  await Promise.race([
    once(child, "exit"),
    new Promise((resolveTimeout) => {
      setTimeout(resolveTimeout, 3_000);
    }),
  ]);

  if (child.exitCode === null && child.signalCode === null) {
    child.kill("SIGKILL");
  }
};

const finish = async (exitCode, source) => {
  if (finishing) {
    return;
  }

  finishing = true;
  await Promise.all(
    children
      .filter(({ process: child }) => child !== source)
      .map(({ process: child }) => stopChild(child)),
  );
  process.exit(exitCode);
};

for (const { name, process: child } of children) {
  child.once("error", (error) => {
    console.error(`Unable to start the ${name} development process.`, error);
    void finish(1, child);
  });
  child.once("exit", (code, signal) => {
    if (!finishing) {
      const exitCode = code ?? (signal === null ? 1 : 128);
      void finish(exitCode, child);
    }
  });
}

process.once("SIGINT", () => {
  void finish(130);
});
process.once("SIGTERM", () => {
  void finish(143);
});
