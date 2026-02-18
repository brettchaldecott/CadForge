/**
 * Index the vault for semantic search.
 * Delegates to the Python backend for embedding generation.
 */

import { Command, Flags } from '@oclif/core';
import { getProjectRoot } from '../config/paths.js';
import { loadSettings } from '../config/settings.js';
import { BackendManager } from '../backend/manager.js';

export default class Index extends Command {
  static override description = 'Index the vault for semantic search';

  static override flags = {
    incremental: Flags.boolean({
      char: 'i',
      description: 'Only re-index changed files',
      default: false,
    }),
  };

  async run(): Promise<void> {
    const { flags } = await this.parse(Index);

    const projectRoot = getProjectRoot();
    const settings = loadSettings(projectRoot);

    const manager = new BackendManager({
      engineUrl: settings.engineUrl,
      port: settings.enginePort,
      onProgress: (msg) => this.log(msg),
    });

    try {
      const client = await manager.start();

      this.log(flags.incremental ? 'Incremental indexing...' : 'Full vault indexing...');

      const result = await client.indexVault({
        project_root: projectRoot,
        incremental: flags.incremental,
      });

      if (!result.success) {
        this.error(`Indexing failed: ${result.error}`);
      }

      this.log(`Indexed ${result.files_indexed} files → ${result.chunks_created} chunks`);
      if (result.files_deleted && result.files_deleted > 0) {
        this.log(`Removed ${result.files_deleted} deleted files`);
      }
      this.log(`Backend: ${result.backend}`);
    } finally {
      await manager.stop();
    }
  }
}
