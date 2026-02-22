/**
 * Tool definitions — Anthropic-format JSON schemas for all tools.
 */

export interface ToolDefinition {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

/**
 * Where a tool executes.
 */
export type ToolLocation = 'local' | 'remote';

export interface ToolRegistryEntry {
  definition: ToolDefinition;
  location: ToolLocation;
}

/**
 * All registered tools.
 */
export const TOOL_REGISTRY: ToolRegistryEntry[] = [
  {
    definition: {
      name: 'ReadFile',
      description: 'Read the contents of a file',
      input_schema: {
        type: 'object',
        properties: {
          path: { type: 'string', description: 'File path to read' },
        },
        required: ['path'],
      },
    },
    location: 'local',
  },
  {
    definition: {
      name: 'WriteFile',
      description: 'Write content to a file',
      input_schema: {
        type: 'object',
        properties: {
          path: { type: 'string', description: 'File path to write' },
          content: { type: 'string', description: 'Content to write' },
        },
        required: ['path', 'content'],
      },
    },
    location: 'local',
  },
  {
    definition: {
      name: 'ListFiles',
      description: 'List files matching a glob pattern',
      input_schema: {
        type: 'object',
        properties: {
          pattern: { type: 'string', description: 'Glob pattern' },
          path: { type: 'string', description: 'Base directory' },
        },
        required: ['pattern'],
      },
    },
    location: 'local',
  },
  {
    definition: {
      name: 'Bash',
      description: 'Execute a shell command',
      input_schema: {
        type: 'object',
        properties: {
          command: { type: 'string', description: 'Shell command to execute' },
          timeout: { type: 'number', description: 'Timeout in milliseconds' },
        },
        required: ['command'],
      },
    },
    location: 'local',
  },
  {
    definition: {
      name: 'ExecuteCadQuery',
      description: 'Execute CadQuery code to create or modify 3D models',
      input_schema: {
        type: 'object',
        properties: {
          code: { type: 'string', description: 'CadQuery Python code' },
          output_name: { type: 'string', description: 'Output filename (without extension)' },
          format: { type: 'string', enum: ['stl', 'step'], description: 'Export format' },
        },
        required: ['code'],
      },
    },
    location: 'remote',
  },
  {
    definition: {
      name: 'AnalyzeMesh',
      description: 'Analyze a mesh file for geometry metrics and manufacturing issues',
      input_schema: {
        type: 'object',
        properties: {
          path: { type: 'string', description: 'Path to mesh file' },
        },
        required: ['path'],
      },
    },
    location: 'remote',
  },
  {
    definition: {
      name: 'SearchVault',
      description: 'Search the knowledge vault for relevant information',
      input_schema: {
        type: 'object',
        properties: {
          query: { type: 'string', description: 'Search query' },
          tags: { type: 'array', items: { type: 'string' }, description: 'Filter by tags' },
          limit: { type: 'number', description: 'Max results' },
        },
        required: ['query'],
      },
    },
    location: 'remote',
  },
  {
    definition: {
      name: 'ShowPreview',
      description: 'Open 3D preview of a mesh file',
      input_schema: {
        type: 'object',
        properties: {
          path: { type: 'string', description: 'Path to STL file' },
        },
        required: ['path'],
      },
    },
    location: 'remote',
  },
  {
    definition: {
      name: 'ExportModel',
      description: 'Export a model to a different format',
      input_schema: {
        type: 'object',
        properties: {
          source: { type: 'string', description: 'Source model path' },
          format: { type: 'string', enum: ['stl', 'step', '3mf'], description: 'Target format' },
          name: { type: 'string', description: 'Output filename' },
        },
        required: ['source'],
      },
    },
    location: 'remote',
  },
  {
    definition: {
      name: 'RenderModel',
      description: 'Render a 3D model (STL file) to PNG images from multiple camera angles',
      input_schema: {
        type: 'object',
        properties: {
          stl_path: { type: 'string', description: 'Path to the STL file to render' },
          output_dir: { type: 'string', description: 'Output directory for PNGs (defaults to same as STL)' },
          include_base64: { type: 'boolean', description: 'Include base64 image data in response' },
        },
        required: ['stl_path'],
      },
    },
    location: 'remote',
  },
  {
    definition: {
      name: 'GetPrinter',
      description: 'Get the active printer profile',
      input_schema: {
        type: 'object',
        properties: {},
      },
    },
    location: 'local',
  },
  {
    definition: {
      name: 'Task',
      description: 'Delegate a task to a subagent',
      input_schema: {
        type: 'object',
        properties: {
          agent_type: { type: 'string', enum: ['explore', 'plan', 'cad', 'design', 'competitive'], description: 'Subagent type' },
          prompt: { type: 'string', description: 'Task prompt' },
          context: { type: 'string', description: 'Additional context' },
        },
        required: ['agent_type', 'prompt'],
      },
    },
    location: 'local',
  },
];

/**
 * Get tool definitions in Anthropic API format.
 */
export function getToolDefinitions(): ToolDefinition[] {
  return TOOL_REGISTRY.map((entry) => entry.definition);
}
