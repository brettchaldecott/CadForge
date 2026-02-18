/**
 * Initialize a new CadForge project.
 * Creates .cadforge/ directory, CADFORGE.md, and vault/ directory.
 */

import { Command, Flags } from '@oclif/core';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { join, basename } from 'node:path';

export default class Init extends Command {
  static override description = 'Initialize a new CadForge project';

  static override flags = {
    force: Flags.boolean({
      char: 'f',
      description: 'Overwrite existing project files',
      default: false,
    }),
  };

  async run(): Promise<void> {
    const { flags } = await this.parse(Init);
    const cwd = process.cwd();
    const projectName = basename(cwd);

    // Check for existing project
    if (existsSync(join(cwd, 'CADFORGE.md')) && !flags.force) {
      this.error('CadForge project already exists. Use --force to overwrite.');
    }

    // Create directories
    const dirs = [
      '.cadforge',
      'vault',
      'output',
      'output/stl',
      'output/step',
      'output/scripts',
      'skills',
    ];

    for (const dir of dirs) {
      mkdirSync(join(cwd, dir), { recursive: true });
    }

    // Create CADFORGE.md
    const cadforgemd = `# ${projectName}

## Project Description
AI-powered CAD project for 3D printing.

## Conventions
- Models are generated using CadQuery
- Output formats: STL (for slicing), STEP (for CAD exchange)
- Vault contains reference materials and design knowledge
`;

    writeFileSync(join(cwd, 'CADFORGE.md'), cadforgemd, 'utf-8');

    // Create default settings
    const defaultSettings = {
      provider: 'anthropic',
      model: 'claude-sonnet-4-5-20250929',
      max_tokens: 8192,
      temperature: 0,
      permissions: {
        deny: ['Bash(rm:*)', 'Bash(sudo:*)', 'WriteFile(**/.env)'],
        allow: [
          'ReadFile(*)',
          'SearchVault(*)',
          'AnalyzeMesh(*)',
          'GetPrinter(*)',
          'Task(explore)',
          'Task(plan)',
        ],
        ask: [
          'ExecuteCadQuery(*)',
          'WriteFile(*)',
          'Bash(*)',
          'ExportModel(*)',
          'Task(cad)',
        ],
      },
      hooks: [],
    };

    writeFileSync(
      join(cwd, '.cadforge', 'settings.json'),
      JSON.stringify(defaultSettings, null, 2) + '\n',
      'utf-8',
    );

    this.log(`Initialized CadForge project: ${projectName}`);
    this.log('');
    this.log('Created:');
    this.log('  CADFORGE.md          — Project description');
    this.log('  .cadforge/           — Configuration');
    this.log('  vault/               — Knowledge vault');
    this.log('  output/              — Generated models');
    this.log('  skills/              — Custom skills');
    this.log('');
    this.log("Run 'cadforge chat' to start the interactive REPL.");
  }
}
