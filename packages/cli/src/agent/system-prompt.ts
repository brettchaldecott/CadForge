/**
 * System prompt builder for CadForge agent.
 *
 * Builds the system prompt with memory hierarchy and printer context.
 */

import type { CadForgeSettings } from '@cadforge/shared';
import { loadMemory, getSystemPromptContent } from '../memory/memory.js';
import { getPrinter } from '../tools/project.js';

export function buildSystemPrompt(
  projectRoot: string,
  settings: CadForgeSettings,
  extraContext = '',
): string {
  const parts = [
    'You are CadForge, an AI-powered CAD assistant for 3D printing.',
    'You help users design parametric 3D models using CadQuery,',
    'analyze meshes for manufacturability, and leverage a knowledge vault',
    'of materials, design rules, and printer profiles.',
    '',
    'When generating CadQuery code:',
    '- Assign the final workpiece to `result`',
    '- Use `cq` as the CadQuery namespace',
    '- Use `np` for numpy operations',
    '- Keep code clean and well-commented',
    '',
    'Available tools: ExecuteCadQuery, ReadFile, WriteFile, ListFiles,',
    'SearchVault, AnalyzeMesh, ShowPreview, ExportModel, Bash, GetPrinter, SearchWeb, Task',
  ];

  // Inject memory hierarchy
  const memory = loadMemory(projectRoot);
  const memoryContent = getSystemPromptContent(memory);
  if (memoryContent) {
    parts.push('\n--- Project Memory ---\n');
    parts.push(memoryContent);
  }

  // Inject printer context
  if (settings.printer) {
    parts.push(`\nActive printer: ${settings.printer}`);
    injectPrinterContext(parts, projectRoot, settings.printer);
  }

  if (extraContext) {
    parts.push(`\n${extraContext}`);
  }

  return parts.join('\n');
}

function injectPrinterContext(parts: string[], projectRoot: string, printerName: string): void {
  const result = getPrinter(projectRoot, printerName);
  if (!result.success || !result.printer) return;

  const printer = result.printer;
  const bv = printer.build_volume as { x?: number; y?: number; z?: number } | undefined;
  if (bv) {
    parts.push(`Build volume: ${bv.x ?? '?'} x ${bv.y ?? '?'} x ${bv.z ?? '?'}mm`);
  }

  const constraints = printer.constraints as Record<string, unknown> | undefined;
  if (constraints) {
    parts.push(`Min wall thickness: ${constraints.min_wall_thickness ?? '?'}mm`);
    parts.push(`Max overhang angle: ${constraints.max_overhang_angle ?? '?'} degrees`);
  }
}
