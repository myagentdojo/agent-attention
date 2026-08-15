import {
	chmodSync,
	existsSync,
	mkdirSync,
	readFileSync,
	statSync,
	writeFileSync,
} from "node:fs"
import { dirname, join } from "node:path"

import type { GeneratedFile } from "./plugin-config"

const projections = [
	{
		source: "experiments/agent-attention/runtime/agent-attention/agent-attention.py",
		target: "plugin/runtime/agent-attention.py",
		executable: true,
	},
	{
		source: "experiments/agent-attention/skill/SKILL.md",
		target: "plugin/skills/agent-attention/SKILL.md",
		executable: false,
	},
] as const

/** Render Agent Attention sidecars from reviewed experiment sources. */
export function renderAgentAttentionPayload(root: string): GeneratedFile[] {
	return projections.map(({ source, target }) => ({
		path: target,
		contents: readFileSync(join(root, source), "utf8"),
	}))
}

/** Write Agent Attention sidecars and preserve runtime executability. */
export function writeAgentAttentionPayload(root: string): GeneratedFile[] {
	const files = renderAgentAttentionPayload(root)
	for (const [index, file] of files.entries()) {
		const path = join(root, file.path)
		mkdirSync(dirname(path), { recursive: true })
		writeFileSync(path, file.contents)
		if (projections[index].executable) chmodSync(path, 0o755)
	}
	return files
}

/** Return missing, stale, or non-executable Agent Attention projections. */
export function checkAgentAttentionPayload(root: string): string[] {
	return renderAgentAttentionPayload(root)
		.filter((file, index) => {
			const path = join(root, file.path)
			if (!existsSync(path) || readFileSync(path, "utf8") !== file.contents) return true
			return projections[index].executable && (statSync(path).mode & 0o111) === 0
		})
		.map((file) => file.path)
}
