/**
 * Protocol types for Node CLI ↔ Python Engine communication.
 * Mirrors the Pydantic models in cadforge_engine.models.
 */

// ── Health ──

export interface HealthResponse {
  status: string;
  version: string;
  capabilities: string[];
}

// ── CadQuery ──

export interface CadQueryRequest {
  code: string;
  output_name?: string;
  format?: 'stl' | 'step';
  project_root: string;
}

export interface CadQueryResponse {
  success: boolean;
  stdout?: string;
  stderr?: string;
  error?: string | null;
  output_path?: string | null;
  script_path?: string | null;
  message?: string | null;
}

// ── Mesh ──

export interface MeshAnalyzeRequest {
  path: string;
  project_root: string;
}

export interface MeshAnalysisResponse {
  success: boolean;
  error?: string | null;
  file_path?: string | null;
  is_watertight?: boolean | null;
  volume_mm3?: number | null;
  volume_cm3?: number | null;
  surface_area_mm2?: number | null;
  triangle_count?: number | null;
  vertex_count?: number | null;
  bounding_box?: Record<string, number> | null;
  center_of_mass?: number[] | null;
  issues?: string[] | null;
}

// ── Preview ──

export interface PreviewRequest {
  path: string;
  color?: string;
  background?: string;
}

export interface PreviewResponse {
  success: boolean;
  message?: string | null;
  error?: string | null;
}

// ── Export ──

export interface ExportRequest {
  source: string;
  format?: 'stl' | 'step' | '3mf';
  name?: string;
  project_root: string;
}

export interface ExportResponse {
  success: boolean;
  output_path?: string | null;
  message?: string | null;
  error?: string | null;
}

// ── Vault ──

export interface VaultSearchRequest {
  query: string;
  tags?: string[];
  limit?: number;
  project_root: string;
}

export interface VaultSearchResult {
  file_path: string;
  section: string;
  content: string;
  score: number;
  tags: string[];
}

export interface VaultSearchResponse {
  success: boolean;
  query: string;
  results: VaultSearchResult[];
  note?: string | null;
  error?: string | null;
}

export interface VaultIndexRequest {
  project_root: string;
  incremental?: boolean;
}

export interface VaultIndexResponse {
  success: boolean;
  files_indexed?: number;
  chunks_created?: number;
  files_deleted?: number;
  backend?: string | null;
  error?: string | null;
}

// ── Render ──

export interface RenderRequest {
  stl_path: string;
  output_dir?: string;
  include_base64?: boolean;
  window_size?: [number, number];
}

export interface RenderResult {
  view: string;
  path: string;
  base64_data?: string | null;
}

export interface RenderResponse {
  success: boolean;
  images: RenderResult[];
  error?: string | null;
}

// ── CAD Subagent ──

import type { ProviderType } from './config.js';

export interface CadSubagentProviderConfig {
  provider: ProviderType;
  api_key?: string | null;
  auth_token?: string | null;
  base_url?: string | null;
  aws_region?: string | null;
  aws_profile?: string | null;
}

export interface CadSubagentRequest {
  prompt: string;
  context: string;
  project_root: string;
  /** @deprecated Use provider_config instead */
  auth?: { api_key?: string | null; auth_token?: string | null };
  provider_config?: CadSubagentProviderConfig;
  model?: string;
  max_tokens?: number;
}

// ── Design Pipeline ──

export interface DesignPipelineRequest {
  prompt: string;
  project_root: string;
  provider_config?: CadSubagentProviderConfig;
  model?: string;
  max_tokens?: number;
  max_rounds?: number;
}

// ── Task API ──

export type TaskType = 'execute_cad' | 'analyze_mesh' | 'design_pipeline' | 'cad_subagent';
export type TaskStatusValue = 'pending' | 'running' | 'completed' | 'failed';

export interface CreateTaskRequest {
  type: TaskType;
  prompt?: string;
  project_root?: string;
  config?: Record<string, unknown>;
}

export interface CreateTaskResponse {
  task_id: string;
  status: string;
}

export interface TaskStatusResponse {
  id: string;
  type: string;
  status: TaskStatusValue;
  prompt: string;
  artifacts: Record<string, string>;
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

// ── Design Lifecycle ──

export interface CreateDesignRequest {
  title: string;
  prompt: string;
  specification?: string;
  constraints?: Record<string, unknown>;
  project_root: string;
}

export interface DesignResponse {
  id: string;
  title: string;
  prompt: string;
  specification: string;
  status: string;
  constraints: Record<string, unknown>;
  iterations: IterationResponse[];
  final_output_path: string | null;
  learnings_indexed: boolean;
  created_at: string;
  updated_at: string;
}

export interface ExecuteDesignRequest {
  provider_config?: CadSubagentProviderConfig;
  model?: string;
  max_tokens?: number;
  max_rounds?: number;
}

export interface IterationResponse {
  round_number: number;
  code: string;
  stl_path: string | null;
  png_paths: string[];
  verdict: string;
  approved: boolean;
  errors: string[];
  timestamp: string;
}

// ── SSE Events (CAD subagent + pipeline) ──

export type SSEEventType =
  | 'status'
  | 'text_delta'
  | 'tool_use_start'
  | 'tool_result'
  | 'completion'
  | 'done'
  | 'pipeline_step'
  | 'pipeline_round'
  | 'pipeline_image'
  | 'pipeline_verdict'
  | 'design_updated'
  | 'iteration_saved'
  | 'learnings_indexed'
  | 'competitive_status'
  | 'competitive_round'
  | 'competitive_supervisor'
  | 'competitive_proposal'
  | 'competitive_debate'
  | 'competitive_sandbox'
  | 'competitive_fidelity'
  | 'competitive_merger'
  | 'competitive_learning'
  | 'competitive_approval_requested'
  | 'competitive_approval_response';

// ── Competitive Pipeline ──

export interface CompetitivePipelineRequest {
  prompt: string;
  project_root: string;
  specification?: string;
  constraints?: Record<string, unknown>;
  pipeline_config?: Record<string, unknown>;
  max_rounds?: number;
}

export interface CompetitiveApprovalRequest {
  approved: boolean;
  feedback?: string;
}

export interface CompetitiveDesignResponse {
  id: string;
  title: string;
  prompt: string;
  specification: string;
  status: string;
  rounds: Record<string, unknown>[];
  final_code: string | null;
  final_stl_path: string | null;
  learnings_indexed: boolean;
  created_at: string;
  updated_at: string;
}

export interface SSEEvent {
  event: SSEEventType;
  data: Record<string, unknown>;
}
