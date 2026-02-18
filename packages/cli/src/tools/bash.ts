/**
 * Local Bash tool handler.
 * Executes shell commands via child_process with stdout truncation.
 */

import { exec } from 'node:child_process';

const MAX_OUTPUT = 30_000; // Truncate stdout at 30K chars

export interface BashResult {
  stdout: string;
  stderr: string;
  exitCode: number;
}

export async function executeBash(
  command: string,
  options: { timeout?: number; cwd?: string } = {},
): Promise<BashResult> {
  return new Promise((resolve) => {
    exec(
      command,
      {
        timeout: options.timeout ?? 120_000,
        cwd: options.cwd ?? process.cwd(),
        maxBuffer: 1024 * 1024 * 10, // 10MB
      },
      (error, stdout, stderr) => {
        let out = stdout ?? '';
        if (out.length > MAX_OUTPUT) {
          out = out.slice(0, MAX_OUTPUT) + `\n... (truncated, ${out.length} total chars)`;
        }
        resolve({
          stdout: out,
          stderr: stderr ?? '',
          exitCode: error?.code ?? (error ? 1 : 0),
        });
      },
    );
  });
}

/**
 * Tool handler compatible with ToolExecutor.registerHandler().
 */
export function handleBash(
  input: Record<string, unknown>,
  projectRoot: string,
): Promise<Record<string, unknown>> {
  const command = input.command as string;
  const timeout = input.timeout as number | undefined;

  return executeBash(command, { cwd: projectRoot, timeout }).then((result) => ({
    success: result.exitCode === 0,
    stdout: result.stdout,
    stderr: result.stderr,
    exit_code: result.exitCode,
  }));
}
