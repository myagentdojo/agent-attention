/** Stable Stop fields used to correlate one exact task with owner state. */
export interface AgentAttentionStopInput {
	cwd?: string
	session_id: string
	stop_hook_active?: boolean
}

/** Minimal owner result consumed by the hook adapter. */
export interface AgentAttentionStopCheck {
	hook_action: "allow" | "continue"
	reason?: string
}

/** Structured owner seam shared by source and installed Stop adapters. */
export interface AgentAttentionStopRuntime {
	checkStop: (threadId: string) => Promise<AgentAttentionStopCheck>
}

/** Codex Stop output that either permits stop or requests one continuation. */
export type AgentAttentionStopOutput =
	| { continue: true; suppressOutput: true }
	| { decision: "block"; reason: string }

const invalidStopInput: AgentAttentionStopOutput = {
	decision: "block",
	reason:
		"Agent Attention could not correlate this Stop event to structured owner state. Repair the hook payload contract before stopping.",
}

/** Validate only stable task-correlation fields needed by structured owner state. */
function isAgentAttentionStopInput(value: unknown): value is AgentAttentionStopInput {
	if (!value || typeof value !== "object" || Array.isArray(value)) return false
	const input = value as Record<string, unknown>
	if (input.cwd !== undefined && typeof input.cwd !== "string") return false
	if (typeof input.session_id !== "string" || input.session_id.trim() === "") return false
	return input.stop_hook_active === undefined || typeof input.stop_hook_active === "boolean"
}

/** Enforce explicit owner state without reading assistant prose or transcripts. */
async function handleAgentAttentionStop(
	input: AgentAttentionStopInput,
	runtime: AgentAttentionStopRuntime,
): Promise<AgentAttentionStopOutput> {
	if (input.stop_hook_active) return { continue: true, suppressOutput: true }
	const check = await runtime.checkStop(input.session_id)
	if (check.hook_action === "continue") {
		return {
			decision: "block",
			reason:
				check.reason ??
				"Agent Attention owner state requires an actionable repair before stopping.",
		}
	}
	return { continue: true, suppressOutput: true }
}

/** Convert owner failures into one actionable Stop block. */
export async function runAgentAttentionStop(
	input: unknown,
	runtime: AgentAttentionStopRuntime,
): Promise<AgentAttentionStopOutput> {
	if (!isAgentAttentionStopInput(input)) return invalidStopInput
	try {
		return await handleAgentAttentionStop(input, runtime)
	} catch (error) {
		const detail = error instanceof Error ? error.message : "unknown error"
		return {
			decision: "block",
			reason: `Agent Attention could not verify structured owner state. Repair the owner check before stopping: ${detail}`,
		}
	}
}

/** Return the fail-closed response for malformed hook stdin. */
export function invalidAgentAttentionStopInput(): AgentAttentionStopOutput {
	return invalidStopInput
}
