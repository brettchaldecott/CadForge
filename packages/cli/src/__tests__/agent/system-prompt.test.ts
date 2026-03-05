import { jest, describe, it, expect, beforeAll } from '@jest/globals';
import { DEFAULT_SETTINGS } from '@cadforge/shared';
import type { CadForgeSettings } from '@cadforge/shared';

jest.unstable_mockModule('../../memory/memory.js', () => ({
  loadMemory: jest.fn().mockReturnValue({ entries: [] }),
  getSystemPromptContent: jest.fn().mockReturnValue(''),
}));

jest.unstable_mockModule('../../tools/project.js', () => ({
  getPrinter: jest.fn().mockReturnValue({
    success: true,
    printer: {
      name: 'TestPrinter',
      build_volume: { x: 220, y: 220, z: 250 },
      constraints: {
        min_wall_thickness: 0.8,
        max_overhang_angle: 45,
      },
    },
  }),
}));

let buildSystemPrompt: typeof import('../../agent/system-prompt.js').buildSystemPrompt;

beforeAll(async () => {
  const mod = await import('../../agent/system-prompt.js');
  buildSystemPrompt = mod.buildSystemPrompt;
});

describe('buildSystemPrompt', () => {
  const settings: CadForgeSettings = { ...DEFAULT_SETTINGS };

  it('includes base identity', () => {
    const prompt = buildSystemPrompt('/tmp', settings);
    expect(prompt).toContain('You are CadForge');
  });

  it('includes competitive refinement guidance', () => {
    const prompt = buildSystemPrompt('/tmp', settings);
    expect(prompt).toContain('design_id');
  });

  it('injects printer context when printer is set', () => {
    const withPrinter = { ...settings, printer: 'TestPrinter' };
    const prompt = buildSystemPrompt('/tmp', withPrinter);
    expect(prompt).toContain('220');
    expect(prompt).toContain('250');
  });

  it('omits printer section when printer is null', () => {
    const noPrinter = { ...settings, printer: null };
    const prompt = buildSystemPrompt('/tmp', noPrinter);
    expect(prompt).not.toContain('Active printer');
  });

  it('appends extraContext', () => {
    const prompt = buildSystemPrompt('/tmp', settings, 'CUSTOM_CONTEXT_STRING');
    expect(prompt).toContain('CUSTOM_CONTEXT_STRING');
  });
});
