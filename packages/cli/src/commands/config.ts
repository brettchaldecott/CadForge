/**
 * Config management command.
 * View and modify CadForge settings.
 */

import { Command, Args, Flags } from '@oclif/core';
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { findProjectRoot, getUserSettingsPath, getProjectSettingsPath } from '../config/paths.js';
import { loadSettings } from '../config/settings.js';

export default class Config extends Command {
  static override description = 'View or modify CadForge configuration';

  static override args = {
    action: Args.string({
      description: 'Action: show, set, get',
      default: 'show',
      options: ['show', 'set', 'get'],
    }),
    key: Args.string({ description: 'Setting key (e.g., model, provider)' }),
    value: Args.string({ description: 'Setting value (for set action)' }),
  };

  static override flags = {
    global: Flags.boolean({
      char: 'g',
      description: 'Modify user-level settings instead of project',
      default: false,
    }),
  };

  async run(): Promise<void> {
    const { args, flags } = await this.parse(Config);
    const projectRoot = findProjectRoot();

    switch (args.action) {
      case 'show': {
        const settings = loadSettings(projectRoot ?? undefined);
        this.log(JSON.stringify(settings, null, 2));
        break;
      }

      case 'get': {
        if (!args.key) {
          this.error('Key is required for get action');
        }
        const settings = loadSettings(projectRoot ?? undefined);
        const value = (settings as unknown as Record<string, unknown>)[args.key];
        if (value === undefined) {
          this.error(`Unknown setting: ${args.key}`);
        }
        this.log(typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value));
        break;
      }

      case 'set': {
        if (!args.key || args.value === undefined) {
          this.error('Key and value are required for set action');
        }

        const settingsPath = flags.global
          ? getUserSettingsPath()
          : projectRoot
            ? getProjectSettingsPath(projectRoot)
            : getUserSettingsPath();

        let current: Record<string, unknown> = {};
        if (existsSync(settingsPath)) {
          try {
            current = JSON.parse(readFileSync(settingsPath, 'utf-8'));
          } catch {
            // start fresh
          }
        }

        // Parse value (try JSON, fall back to string)
        let parsed: unknown;
        try {
          parsed = JSON.parse(args.value);
        } catch {
          parsed = args.value;
        }

        current[args.key] = parsed;
        writeFileSync(settingsPath, JSON.stringify(current, null, 2) + '\n', 'utf-8');
        this.log(`Set ${args.key} = ${JSON.stringify(parsed)} in ${settingsPath}`);
        break;
      }
    }
  }
}
