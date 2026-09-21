import { createDefaultRuntime, AntigravityAcpBroker } from "../../broker.mjs";

const [stateRoot, workspace, runtimeDir, geminiHome] = process.argv.slice(2);
const model = "gemini-3.8-flash-high";

const broker = new AntigravityAcpBroker({
  stateRoot,
  runtimeDir,
  geminiHome,
  processEnv: { PATH: process.env.PATH ?? "" },
  runtimeFactory: (options) => {
    const runtime = createDefaultRuntime(options);
    runtime.close = async () => {
      await new Promise((resolve) => setTimeout(resolve, 100));
      throw new Error("synthetic runtime close uncertainty");
    };
    return runtime;
  },
});

await broker.init();
const submitted = await broker.delegate({
  workspace,
  model,
  prompt: "Complete one synthetic bounded task, then exercise uncertain cleanup.",
  timeoutMs: 30_000,
});
const result = await broker.result({ jobId: submitted.jobId, waitMs: 30_000 });
const persisted = await broker.getJob(submitted.jobId);
process.stdout.write(`${JSON.stringify({
  pid: process.pid,
  owner: persisted.owner,
  jobId: submitted.jobId,
  status: result.status,
  complete: result.complete,
  cleanup: result.cleanup?.status,
  cleanupObserved: result.cleanup?.observed,
})}\n`);

// Deliberately exit without broker.close()/runtime.shutdown(). The test owns
// the resulting ACP peer and cleans it by exact PID in the parent finally.
process.exit(0);
