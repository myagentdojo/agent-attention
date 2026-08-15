import { chmodSync, mkdtempSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { dirname, join } from "node:path"

import { afterEach, expect, test } from "bun:test"

const temporaryRoots: string[] = []

afterEach(() => {
	for (const root of temporaryRoots.splice(0)) {
		rmSync(root, { recursive: true, force: true })
	}
})

function runMain(
	python: string,
	arguments_: string[] = ["commands"],
	stdin: string | undefined = undefined,
): ReturnType<typeof Bun.spawnSync> {
	return Bun.spawnSync({
		cmd: [process.execPath, join(import.meta.dir, "main.ts"), ...arguments_],
		env: { ...process.env, AGENT_ATTENTION_PYTHON: python },
		stdin: stdin === undefined ? "ignore" : Buffer.from(stdin),
		stdout: "pipe",
		stderr: "pipe",
	})
}

function writeFakePython(prefix: string, source: string): string {
	const root = mkdtempSync(join(tmpdir(), prefix))
	temporaryRoots.push(root)
	const executable = join(root, "python")
	writeFileSync(executable, `#!${process.execPath}\n${source}`)
	chmodSync(executable, 0o755)
	return executable
}

test("missing Python diagnostics preserve the command result envelope", () => {
	const completed = runMain("/missing/python3")
	const result = JSON.parse(completed.stdout.toString())

	expect(completed.exitCode).toBe(1)
	expect(result).toMatchObject({
		contract_id: "agent-attention.approval-gate",
		schema_version: "1",
		status: "error",
		error_category: "missing_python",
	})
	expect(result.run_id).toMatch(
		/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
	)
})

test("main flushes complete stdout and stderr before exiting", () => {
	const executable = writeFakePython(
		"agent-attention-output-",
		`
const stdout = "o".repeat(1_000_000)
const stderr = "e".repeat(1_000_000)
process.stdout.write(stdout)
process.stderr.write(stderr)
process.exitCode = 23
`,
	)

	const completed = runMain(executable)

	expect(completed.exitCode).toBe(23)
	expect(completed.stdout.byteLength).toBe(1_000_000)
	expect(completed.stderr.byteLength).toBe(1_000_000)
})

test("hook-stop parses owner output and returns a valid block", () => {
	const executable = writeFakePython(
		"agent-attention-stop-",
		`
if (process.argv.slice(3).join(" ") !== "check-stop --thread-id thread-123") process.exit(97)
console.log(JSON.stringify({ hook_action: "continue", reason: "Approval is still required." }))
`,
	)

	const completed = runMain(
		executable,
		["hook-stop"],
		JSON.stringify({ session_id: "thread-123", cwd: dirname(executable) }),
	)

	expect(completed.exitCode, completed.stderr.toString()).toBe(0)
	expect(JSON.parse(completed.stdout.toString())).toEqual({
		decision: "block",
		reason: "Approval is still required.",
	})
})

test("hook-stop fails closed on invalid stdin without invoking Python", () => {
	const completed = runMain("/missing/python3", ["hook-stop"], "not-json")
	const result = JSON.parse(completed.stdout.toString())

	expect(completed.exitCode, completed.stderr.toString()).toBe(0)
	expect(result).toMatchObject({ decision: "block" })
	expect(result.reason).toContain("could not correlate this Stop event")
})
