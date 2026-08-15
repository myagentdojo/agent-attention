import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"

import { afterAll, beforeAll, expect, test } from "bun:test"

import { copyPluginPayload } from "./plugin-files"
import { hookDeclarationBody } from "./plugin-config"

const root = join(import.meta.dir, "..")
const temporaryRoot = mkdtempSync(join(tmpdir(), "agent-attention-installed-"))
const installedRoot = join(temporaryRoot, "installed")

beforeAll(() => copyPluginPayload(root, installedRoot))

afterAll(() => rmSync(temporaryRoot, { recursive: true, force: true }))

test("Agent Attention is generated into the installable payload", () => {
	const catalog = JSON.parse(
		readFileSync(join(root, "runtime", "skill-catalog.json"), "utf8"),
	)
	const inventory = JSON.parse(
		readFileSync(join(installedRoot, "runtime", "bundle-inventory.json"), "utf8"),
	)

	expect(catalog.skills["agent-attention"]).toEqual({
		entry: "runtime/agent-attention.js",
		runtimeProfile: "bun",
		workspace: "packages/agent-attention",
	})
	expect(inventory.bundles["agent-attention"].path).toMatch(
		/^runtime\/agent-attention-[a-f0-9]{16}\.js$/,
	)
	expect(readFileSync(join(installedRoot, "runtime", "agent-attention.py"))).toEqual(
		readFileSync(
			join(
				root,
				"experiments",
				"agent-attention",
				"runtime",
				"agent-attention",
				"agent-attention.py",
			),
		),
	)
	expect(
		readFileSync(join(installedRoot, "skills", "agent-attention", "SKILL.md")),
	).toEqual(
		readFileSync(
			join(root, "experiments", "agent-attention", "skill", "SKILL.md"),
		),
	)
})

test("Codex Stop declares the custody-launched installed adapter", () => {
	const declaration = hookDeclarationBody("codex") as {
		hooks: { Stop: Array<{ hooks: Array<{ command: string; timeout?: number }> }> }
	}
	const commands = declaration.hooks.Stop.flatMap((group) => group.hooks)

	expect(commands).toContainEqual({
		type: "command",
		command: '"${PLUGIN_ROOT}/bin/agent-attention" hook-stop',
		timeout: 10,
		statusMessage: "Checking Agent Attention owner state",
	})
})

test("installed Stop adapter fails closed when Python is unavailable", () => {
	const inventory = JSON.parse(
		readFileSync(join(installedRoot, "runtime", "bundle-inventory.json"), "utf8"),
	)
	const bundlePath = join(installedRoot, inventory.bundles["agent-attention"].path)
	const completed = Bun.spawnSync({
		cmd: [process.execPath, bundlePath, "hook-stop"],
		cwd: temporaryRoot,
		env: { ...process.env, AGENT_ATTENTION_PYTHON: "/missing/python3" },
		stdin: Buffer.from(
			JSON.stringify({
				cwd: temporaryRoot,
				session_id: "019fc54e-ff95-7ca1-af49-5720c36fdc0d",
			}),
		),
		stdout: "pipe",
		stderr: "pipe",
	})
	const result = JSON.parse(completed.stdout.toString())

	expect(completed.exitCode, completed.stderr.toString()).toBe(0)
	expect(result).toMatchObject({ decision: "block" })
	expect(result.reason).toContain("could not verify structured owner state")
	expect(result.reason).toContain("could not start python3")
	expect(completed.stderr.toString()).not.toContain(root)
})

test("installed Python sidecar passes the bounded lifecycle suite", () => {
	const completed = Bun.spawnSync({
		cmd: [
			"python3",
			"-m",
			"unittest",
			"experiments/agent-attention/runtime/agent-attention/test_agent_attention.py",
		],
		cwd: root,
		env: {
			...process.env,
			AGENT_ATTENTION_RUNTIME: join(installedRoot, "runtime", "agent-attention.py"),
		},
		stdout: "pipe",
		stderr: "pipe",
	})

	expect(completed.exitCode, completed.stderr.toString()).toBe(0)
	expect(completed.stderr.toString()).toContain("OK")
}, 30_000)

test("installed Stop adapter blocks unresolved exact-task state", () => {
	const threadId = "019fc54e-ff95-7ca1-af49-5720c36fdc0d"
	const stateRoot = join(temporaryRoot, "state")
	const requestDirectory = join(stateRoot, "agent-attention", "requests")
	mkdirSync(requestDirectory, { recursive: true, mode: 0o700 })
	writeFileSync(
		join(requestDirectory, `${threadId}.json`),
		`${JSON.stringify({
			version: 1,
			thread_id: threadId,
			status: "declared",
			intent: { continuation: "Run the exact continuation." },
		})}\n`,
		{ mode: 0o600 },
	)
	const inventory = JSON.parse(
		readFileSync(join(installedRoot, "runtime", "bundle-inventory.json"), "utf8"),
	)
	const bundlePath = join(installedRoot, inventory.bundles["agent-attention"].path)
	const completed = Bun.spawnSync({
		cmd: [process.execPath, bundlePath, "hook-stop"],
		cwd: temporaryRoot,
		env: { ...process.env, XDG_STATE_HOME: stateRoot },
		stdin: Buffer.from(JSON.stringify({ cwd: temporaryRoot, session_id: threadId })),
		stdout: "pipe",
		stderr: "pipe",
	})
	const result = JSON.parse(completed.stdout.toString())

	expect(completed.exitCode, completed.stderr.toString()).toBe(0)
	expect(result).toMatchObject({ decision: "block" })
	expect(result.reason).toContain("declared but has no gate")
})
