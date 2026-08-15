import { chmodSync, mkdtempSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"

import { afterEach, expect, test } from "bun:test"

const temporaryRoots: string[] = []

afterEach(() => {
	for (const root of temporaryRoots.splice(0)) {
		rmSync(root, { recursive: true, force: true })
	}
})

function runMain(python: string): ReturnType<typeof Bun.spawnSync> {
	return Bun.spawnSync({
		cmd: [process.execPath, join(import.meta.dir, "main.ts"), "commands"],
		env: { ...process.env, AGENT_ATTENTION_PYTHON: python },
		stdout: "pipe",
		stderr: "pipe",
	})
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
	const root = mkdtempSync(join(tmpdir(), "agent-attention-output-"))
	temporaryRoots.push(root)
	const executable = join(root, "python")
	writeFileSync(
		executable,
		`#!/usr/bin/env bun
const stdout = "o".repeat(1_000_000)
const stderr = "e".repeat(1_000_000)
process.stdout.write(stdout)
process.stderr.write(stderr)
process.exitCode = 23
`,
	)
	chmodSync(executable, 0o755)

	const completed = runMain(executable)

	expect(completed.exitCode).toBe(23)
	expect(completed.stdout.byteLength).toBe(1_000_000)
	expect(completed.stderr.byteLength).toBe(1_000_000)
})
