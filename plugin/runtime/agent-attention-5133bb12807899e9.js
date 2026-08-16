// @bun
// packages/agent-attention/src/main.ts
import { randomUUID } from "crypto";
import { join } from "path";

// packages/agent-attention/src/stop.ts
var invalidStopInput = {
  decision: "block",
  reason: "Agent Attention could not correlate this Stop event to structured owner state. Repair the hook payload contract before stopping."
};
function isAgentAttentionStopInput(value) {
  if (!value || typeof value !== "object" || Array.isArray(value))
    return false;
  const input = value;
  if (input.cwd !== undefined && typeof input.cwd !== "string")
    return false;
  if (typeof input.session_id !== "string" || input.session_id.trim() === "")
    return false;
  return input.stop_hook_active === undefined || typeof input.stop_hook_active === "boolean";
}
async function handleAgentAttentionStop(input, runtime) {
  if (input.stop_hook_active)
    return { continue: true, suppressOutput: true };
  const check = await runtime.checkStop(input.session_id);
  if (check.hook_action === "continue") {
    return {
      decision: "block",
      reason: check.reason ?? "Agent Attention owner state requires an actionable repair before stopping."
    };
  }
  return { continue: true, suppressOutput: true };
}
async function runAgentAttentionStop(input, runtime) {
  if (!isAgentAttentionStopInput(input))
    return invalidStopInput;
  try {
    return await handleAgentAttentionStop(input, runtime);
  } catch (error) {
    const detail = error instanceof Error ? error.message : "unknown error";
    return {
      decision: "block",
      reason: `Agent Attention could not verify structured owner state. Repair the owner check before stopping: ${detail}`
    };
  }
}
function invalidAgentAttentionStopInput() {
  return invalidStopInput;
}

// packages/agent-attention/src/main.ts
async function writeOutput(stream, content) {
  if (content.length === 0)
    return;
  await new Promise((resolve, reject) => {
    stream.write(content, (error) => {
      if (error)
        reject(error);
      else
        resolve();
    });
  });
}
function pythonExecutable() {
  return process.env.AGENT_ATTENTION_PYTHON || "python3";
}
async function runPython(arguments_, timeout) {
  const owner = join(import.meta.dir, "agent-attention.py");
  try {
    const child = Bun.spawn([pythonExecutable(), owner, ...arguments_], {
      stdin: "inherit",
      stdout: "pipe",
      stderr: "pipe",
      ...timeout === undefined ? {} : { timeout }
    });
    const [stdout, stderr, exitCode] = await Promise.all([
      new Response(child.stdout).text(),
      new Response(child.stderr).text(),
      child.exited
    ]);
    return { exitCode, stdout, stderr };
  } catch (error) {
    const detail = error instanceof Error ? error.message : "unknown error";
    return {
      exitCode: 1,
      stdout: `${JSON.stringify({
        contract_id: "agent-attention.approval-gate",
        schema_version: "1",
        run_id: randomUUID(),
        status: "error",
        changed: false,
        retry_safe: false,
        error_category: "missing_python",
        next_safe_action: "Install python3 in a standard system location, then retry."
      })}
`,
      stderr: `Agent Attention could not start python3: ${detail}
`
    };
  }
}
function installedStopRuntime() {
  return {
    checkStop: async (threadId) => {
      const result = await runPython(["check-stop", "--thread-id", threadId], 5000);
      if (result.exitCode !== 0)
        throw new Error(result.stderr.trim() || "owner check failed");
      const parsed = JSON.parse(result.stdout);
      if (parsed.hook_action !== "allow" && parsed.hook_action !== "continue") {
        throw new Error("Agent Attention stop check returned an invalid action");
      }
      return {
        hook_action: parsed.hook_action,
        ...typeof parsed.reason === "string" ? { reason: parsed.reason } : {}
      };
    }
  };
}
async function main() {
  const arguments_ = process.argv.slice(2);
  if (arguments_[0] === "hook-stop") {
    let input;
    try {
      input = await Bun.stdin.json();
    } catch {
      await writeOutput(process.stdout, `${JSON.stringify(invalidAgentAttentionStopInput())}
`);
      return 0;
    }
    const output = await runAgentAttentionStop(input, installedStopRuntime());
    await writeOutput(process.stdout, `${JSON.stringify(output)}
`);
    return 0;
  }
  const result = await runPython(arguments_);
  await Promise.all([
    writeOutput(process.stdout, result.stdout),
    writeOutput(process.stderr, result.stderr)
  ]);
  return result.exitCode;
}
process.exitCode = await main();
