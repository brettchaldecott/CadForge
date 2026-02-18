/**
 * Context window management.
 *
 * Monitors token usage and performs automatic compaction
 * when approaching context limits.
 */

const CHARS_PER_TOKEN = 4;
const DEFAULT_CONTEXT_WINDOW = 200_000;
const COMPACTION_THRESHOLD = 0.80;

export interface ContextState {
  estimatedTokens: number;
  contextWindow: number;
  compactionCount: number;
}

export function createContextState(contextWindow = DEFAULT_CONTEXT_WINDOW): ContextState {
  return { estimatedTokens: 0, contextWindow, compactionCount: 0 };
}

export function usageRatio(state: ContextState): number {
  return state.contextWindow > 0 ? state.estimatedTokens / state.contextWindow : 0;
}

export function needsCompaction(state: ContextState): boolean {
  return usageRatio(state) >= COMPACTION_THRESHOLD;
}

export function remainingTokens(state: ContextState): number {
  return Math.max(0, state.contextWindow - state.estimatedTokens);
}

export function estimateTokens(text: string): number {
  return Math.max(1, Math.floor(text.length / CHARS_PER_TOKEN));
}

export function estimateMessageTokens(message: Record<string, unknown>): number {
  const content = message.content;
  if (typeof content === 'string') {
    return estimateTokens(content);
  }
  if (Array.isArray(content)) {
    let total = 0;
    for (const block of content) {
      if (typeof block === 'object' && block !== null) {
        const b = block as Record<string, unknown>;
        if (typeof b.text === 'string') {
          total += estimateTokens(b.text);
        } else if (b.input !== undefined) {
          total += estimateTokens(String(b.input));
        }
      } else if (typeof block === 'string') {
        total += estimateTokens(block);
      }
    }
    return total;
  }
  return 0;
}

export function estimateMessagesTokens(messages: Record<string, unknown>[]): number {
  return messages.reduce((sum, m) => sum + estimateMessageTokens(m), 0);
}

/**
 * Replace old messages with a summary, keeping recent messages.
 */
export function compactMessages(
  messages: Record<string, unknown>[],
  summary: string,
  keepRecent = 4,
): Record<string, unknown>[] {
  if (messages.length <= keepRecent) return [...messages];

  const summaryMessage = {
    role: 'user',
    content: `[Previous conversation summary]\n\n${summary}\n\n[End of summary — conversation continues below]`,
  };

  return [summaryMessage, ...messages.slice(-keepRecent)];
}

/**
 * Build a prompt for generating a conversation summary.
 */
export function buildSummaryPrompt(messages: Record<string, unknown>[]): string {
  const parts: string[] = [];
  for (const msg of messages) {
    const role = (msg.role as string) ?? 'unknown';
    const content = msg.content;
    if (typeof content === 'string') {
      parts.push(`**${role}**: ${content.slice(0, 500)}`);
    } else if (Array.isArray(content)) {
      const textParts: string[] = [];
      for (const block of content) {
        if (typeof block === 'object' && block !== null) {
          const b = block as Record<string, unknown>;
          if (typeof b.text === 'string') {
            textParts.push(b.text.slice(0, 200));
          }
        }
      }
      if (textParts.length > 0) {
        parts.push(`**${role}**: ${textParts.join(' ')}`);
      }
    }
  }

  const conversation = parts.join('\n\n');
  return (
    'Summarize the following conversation concisely, preserving:\n' +
    '- Key design decisions and parameters\n' +
    '- Generated file paths and model descriptions\n' +
    '- Important constraints and requirements\n' +
    '- Current state of the task\n\n' +
    `Conversation:\n${conversation}`
  );
}
