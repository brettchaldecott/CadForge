/**
 * View an STL file in the 3D viewer.
 * Delegates to the Python backend for PyVista rendering.
 */

import { Command, Args } from '@oclif/core';
import { resolve } from 'node:path';
import { existsSync } from 'node:fs';
import { getProjectRoot } from '../config/paths.js';
import { loadSettings } from '../config/settings.js';
import { BackendManager } from '../backend/manager.js';

export default class View extends Command {
  static override description = 'Open 3D preview of an STL file';

  static override args = {
    path: Args.string({ description: 'Path to STL file', required: true }),
  };

  async run(): Promise<void> {
    const { args } = await this.parse(View);

    const filePath = resolve(args.path);
    if (!existsSync(filePath)) {
      this.error(`File not found: ${filePath}`);
    }

    let projectRoot: string;
    try {
      projectRoot = getProjectRoot();
    } catch {
      projectRoot = process.cwd();
    }

    const settings = loadSettings(projectRoot);

    const manager = new BackendManager({
      engineUrl: settings.engineUrl,
      port: settings.enginePort,
      onProgress: (msg) => this.log(msg),
    });

    try {
      const client = await manager.start();
      const result = await client.preview({ path: filePath });

      if (!result.success) {
        this.error(`Preview failed: ${result.error}`);
      }

      this.log(result.message ?? 'Viewer opened.');
    } finally {
      await manager.stop();
    }
  }
}
