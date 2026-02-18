/**
 * HTTP + SSE client for the Python CadForge Engine API.
 */

import type {
  HealthResponse,
  CadQueryRequest,
  CadQueryResponse,
  MeshAnalyzeRequest,
  MeshAnalysisResponse,
  PreviewRequest,
  PreviewResponse,
  ExportRequest,
  ExportResponse,
  VaultSearchRequest,
  VaultSearchResponse,
  VaultIndexRequest,
  VaultIndexResponse,
} from '@cadforge/shared';

export class BackendClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  /**
   * Make a request to the engine API.
   */
  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const init: RequestInit = {
      method,
      headers: { 'Content-Type': 'application/json' },
    };
    if (body !== undefined) {
      init.body = JSON.stringify(body);
    }

    const response = await fetch(url, init);
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`Engine API error ${response.status}: ${text}`);
    }
    return (await response.json()) as T;
  }

  // ── Health ──

  async health(): Promise<HealthResponse> {
    return this.request<HealthResponse>('GET', '/health');
  }

  /**
   * Wait for the engine to become healthy, with timeout.
   */
  async waitForHealth(timeoutMs: number = 30000): Promise<HealthResponse> {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      try {
        return await this.health();
      } catch {
        await new Promise((resolve) => setTimeout(resolve, 500));
      }
    }
    throw new Error(`Engine did not become healthy within ${timeoutMs}ms`);
  }

  // ── CadQuery ──

  async executeCadQuery(req: CadQueryRequest): Promise<CadQueryResponse> {
    return this.request<CadQueryResponse>('POST', '/tools/cadquery', req);
  }

  // ── Mesh ──

  async analyzeMesh(req: MeshAnalyzeRequest): Promise<MeshAnalysisResponse> {
    return this.request<MeshAnalysisResponse>('POST', '/tools/mesh', req);
  }

  async preview(req: PreviewRequest): Promise<PreviewResponse> {
    return this.request<PreviewResponse>('POST', '/tools/preview', req);
  }

  // ── Export ──

  async exportModel(req: ExportRequest): Promise<ExportResponse> {
    return this.request<ExportResponse>('POST', '/tools/export', req);
  }

  // ── Vault ──

  async searchVault(req: VaultSearchRequest): Promise<VaultSearchResponse> {
    return this.request<VaultSearchResponse>('POST', '/vault/search', req);
  }

  async indexVault(req: VaultIndexRequest): Promise<VaultIndexResponse> {
    return this.request<VaultIndexResponse>('POST', '/vault/index', req);
  }

  // ── Generic tool dispatch ──

  /**
   * Route a tool call to the appropriate engine endpoint.
   */
  async callTool(toolName: string, input: Record<string, unknown>): Promise<Record<string, unknown>> {
    switch (toolName) {
      case 'ExecuteCadQuery':
        return this.request('POST', '/tools/cadquery', input);
      case 'AnalyzeMesh':
        return this.request('POST', '/tools/mesh', input);
      case 'ShowPreview':
        return this.request('POST', '/tools/preview', input);
      case 'ExportModel':
        return this.request('POST', '/tools/export', input);
      case 'SearchVault':
        return this.request('POST', '/vault/search', input);
      default:
        return { success: false, error: `Unknown remote tool: ${toolName}` };
    }
  }
}
