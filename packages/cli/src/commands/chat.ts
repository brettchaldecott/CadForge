/**
 * Default command: interactive REPL.
 * This is the main entry point — runs when user types `cadforge` or `cadforge chat`.
 *
 * Starts the backend, resolves auth, then renders the Ink-based REPL.
 */

import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { PassThrough } from 'node:stream';
import { Command, Flags } from '@oclif/core';
import React from 'react';
import { render } from 'ink';
import { findProjectRoot } from '../config/paths.js';
import { loadSettings } from '../config/settings.js';
import { BackendManager } from '../backend/manager.js';
import { resolveAuthForProvider } from '../llm/auth.js';
import { App } from '../ui/App.js';

export default class Chat extends Command {
  static override description = 'Start interactive CadForge REPL';

  static override flags = {
    resume: Flags.string({ description: 'Resume a previous session' }),
    model: Flags.string({ description: 'Override LLM model' }),
  };

  async run(): Promise<void> {
    const { flags } = await this.parse(Chat);

    const projectRoot = findProjectRoot();
    if (!projectRoot) {
      this.error("No CadForge project found. Run 'cadforge init' to create one.");
    }

    const settings = loadSettings(projectRoot);
    if (flags.model) {
      settings.model = flags.model;
    }

    // Resolve auth
    const creds = resolveAuthForProvider(settings.provider, settings.providerConfig);

    // Detect local engine for dev installs
    const localEngine = join(projectRoot, 'engine');
    const enginePath = existsSync(join(localEngine, 'pyproject.toml')) ? localEngine : undefined;

    // Start backend
    const manager = new BackendManager({
      engineUrl: settings.engineUrl,
      port: settings.enginePort,
      enginePath,
      onProgress: (msg) => this.log(msg),
    });

    try {
      const client = await manager.start();

      // When stdin is not a TTY (e.g. piped input), provide a fallback
      // stream that fakes TTY support to prevent Ink from crashing.
      // Ink's handleSetRawMode checks stdin.isTTY, calls stdin.ref(),
      // stdin.setRawMode(), and stdin.addListener — so we must provide all of these.
      let stdin: NodeJS.ReadStream = process.stdin;
      if (!process.stdin.isTTY) {
        const passthrough = Object.assign(new PassThrough(), {
          isTTY: true as const,
          setRawMode: () => passthrough,
          ref: () => passthrough,
          unref: () => passthrough,
        });
        stdin = passthrough as unknown as NodeJS.ReadStream;
      }

      // Render Ink app
      const app = render(
        React.createElement(App, {
          projectRoot,
          settings,
          backendClient: client,
          sessionId: flags.resume,
          authSource: creds.source,
        }),
        { stdin: stdin as NodeJS.ReadStream, exitOnCtrlC: false },
      );

      await app.waitUntilExit();
    } finally {
      await manager.stop();
    }
  }
}
