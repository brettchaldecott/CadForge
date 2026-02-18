/**
 * Resume a previous session.
 * Placeholder for Phase 3 — will load JSONL session and restore conversation.
 */

import { Command, Args } from '@oclif/core';

export default class Resume extends Command {
  static override description = 'Resume a previous CadForge session';

  static override args = {
    session: Args.string({ description: 'Session ID to resume', required: true }),
  };

  async run(): Promise<void> {
    const { args } = await this.parse(Resume);
    this.log(`Session resume will be implemented in Phase 3.`);
    this.log(`Session ID: ${args.session}`);
  }
}
