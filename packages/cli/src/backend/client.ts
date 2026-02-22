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
  CadSubagentRequest,
  DesignPipelineRequest,
  CreateTaskRequest,
  CreateTaskResponse,
  TaskStatusResponse,
  SSEEvent,
  CreateDesignRequest,
  DesignResponse,
  ExecuteDesignRequest,
  IterationResponse,
  CompetitivePipelineRequest,
  CompetitiveApprovalRequest,
  CompetitiveDesignResponse,
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

  // ── CAD Subagent ──

  /**
   * Stream a CAD subagent session via SSE.
   * Parses the SSE wire format and calls onSSEEvent for each event.
   * Returns the final output from the 'completion' event.
   */
  async streamCadSubagent(
    req: CadSubagentRequest,
    onSSEEvent: (event: SSEEvent) => void,
  ): Promise<{ success: boolean; output: string; error?: string }> {
    const url = `${this.baseUrl}/subagent/cad`;
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });

    if (!response.ok) {
      const text = await response.text();
      return { success: false, output: '', error: `Engine API error ${response.status}: ${text}` };
    }

    if (!response.body) {
      return { success: false, output: '', error: 'No response body from SSE endpoint' };
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let finalOutput = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Parse SSE events from buffer
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';  // Keep incomplete line in buffer

        let currentEvent = '';
        let currentData = '';

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            currentData = line.slice(6);
          } else if (line === '' && currentEvent) {
            // End of SSE event (blank line)
            try {
              const data = JSON.parse(currentData) as Record<string, unknown>;
              const sseEvent: SSEEvent = {
                event: currentEvent as SSEEvent['event'],
                data,
              };
              onSSEEvent(sseEvent);

              if (currentEvent === 'completion') {
                finalOutput = (data.text as string) ?? '';
              }
            } catch {
              // Skip malformed events
            }
            currentEvent = '';
            currentData = '';
          }
        }
      }
    } finally {
      reader.releaseLock();
    }

    return { success: true, output: finalOutput };
  }

  // ── Design Pipeline ──

  /**
   * Stream a design pipeline session via SSE.
   * Returns the final output from the 'completion' event.
   */
  async streamDesignPipeline(
    req: DesignPipelineRequest,
    onSSEEvent: (event: SSEEvent) => void,
  ): Promise<{ success: boolean; output: string; error?: string }> {
    const url = `${this.baseUrl}/pipeline/design`;
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });

    if (!response.ok) {
      const text = await response.text();
      return { success: false, output: '', error: `Engine API error ${response.status}: ${text}` };
    }

    if (!response.body) {
      return { success: false, output: '', error: 'No response body from SSE endpoint' };
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let finalOutput = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        let currentEvent = '';
        let currentData = '';

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            currentData = line.slice(6);
          } else if (line === '' && currentEvent) {
            try {
              const data = JSON.parse(currentData) as Record<string, unknown>;
              const sseEvent: SSEEvent = {
                event: currentEvent as SSEEvent['event'],
                data,
              };
              onSSEEvent(sseEvent);

              if (currentEvent === 'completion') {
                finalOutput = (data.text as string) ?? '';
              }
            } catch {
              // Skip malformed events
            }
            currentEvent = '';
            currentData = '';
          }
        }
      }
    } finally {
      reader.releaseLock();
    }

    return { success: true, output: finalOutput };
  }

  // ── Task API ──

  async createTask(req: CreateTaskRequest): Promise<CreateTaskResponse> {
    return this.request<CreateTaskResponse>('POST', '/tasks', req);
  }

  async getTask(taskId: string): Promise<TaskStatusResponse> {
    return this.request<TaskStatusResponse>('GET', `/tasks/${taskId}`);
  }

  /**
   * Stream task events via SSE.
   */
  async streamTask(
    taskId: string,
    onSSEEvent: (event: SSEEvent) => void,
  ): Promise<{ success: boolean; error?: string }> {
    const url = `${this.baseUrl}/tasks/${taskId}/stream`;
    const response = await fetch(url, { method: 'GET' });

    if (!response.ok) {
      const text = await response.text();
      return { success: false, error: `Engine API error ${response.status}: ${text}` };
    }

    if (!response.body) {
      return { success: false, error: 'No response body from SSE endpoint' };
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        let currentEvent = '';
        let currentData = '';

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            currentData = line.slice(6);
          } else if (line === '' && currentEvent) {
            try {
              const data = JSON.parse(currentData) as Record<string, unknown>;
              const sseEvent: SSEEvent = {
                event: currentEvent as SSEEvent['event'],
                data,
              };
              onSSEEvent(sseEvent);
            } catch {
              // Skip malformed events
            }
            currentEvent = '';
            currentData = '';
          }
        }
      }
    } finally {
      reader.releaseLock();
    }

    return { success: true };
  }

  async getTaskArtifactUrl(taskId: string, name: string): Promise<string> {
    return `${this.baseUrl}/tasks/${taskId}/artifacts/${encodeURIComponent(name)}`;
  }

  // ── Designs ──

  async createDesign(req: CreateDesignRequest): Promise<DesignResponse> {
    return this.request<DesignResponse>('POST', '/designs', req);
  }

  async getDesign(id: string, projectRoot: string): Promise<DesignResponse> {
    return this.request<DesignResponse>('GET', `/designs/${id}?project_root=${encodeURIComponent(projectRoot)}`);
  }

  async listDesigns(projectRoot: string): Promise<DesignResponse[]> {
    return this.request<DesignResponse[]>('GET', `/designs?project_root=${encodeURIComponent(projectRoot)}`);
  }

  async approveDesign(id: string, projectRoot: string): Promise<DesignResponse> {
    return this.request<DesignResponse>('POST', `/designs/${id}/approve?project_root=${encodeURIComponent(projectRoot)}`);
  }

  async getDesignIterations(id: string, projectRoot: string): Promise<IterationResponse[]> {
    return this.request<IterationResponse[]>('GET', `/designs/${id}/iterations?project_root=${encodeURIComponent(projectRoot)}`);
  }

  /**
   * Stream a design execution pipeline via SSE.
   */
  async streamDesignExecution(
    id: string,
    req: ExecuteDesignRequest,
    projectRoot: string,
    onSSEEvent: (event: SSEEvent) => void,
  ): Promise<{ success: boolean; output: string; error?: string }> {
    const url = `${this.baseUrl}/designs/${id}/execute?project_root=${encodeURIComponent(projectRoot)}`;
    return this._streamSSE(url, req, onSSEEvent);
  }

  /**
   * Stream a design resume pipeline via SSE.
   */
  async streamDesignResume(
    id: string,
    req: ExecuteDesignRequest,
    projectRoot: string,
    onSSEEvent: (event: SSEEvent) => void,
  ): Promise<{ success: boolean; output: string; error?: string }> {
    const url = `${this.baseUrl}/designs/${id}/resume?project_root=${encodeURIComponent(projectRoot)}`;
    return this._streamSSE(url, req, onSSEEvent);
  }

  /**
   * Generic SSE streaming helper — POST body, parse SSE events.
   */
  private async _streamSSE(
    url: string,
    body: unknown,
    onSSEEvent: (event: SSEEvent) => void,
  ): Promise<{ success: boolean; output: string; error?: string }> {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const text = await response.text();
      return { success: false, output: '', error: `Engine API error ${response.status}: ${text}` };
    }

    if (!response.body) {
      return { success: false, output: '', error: 'No response body from SSE endpoint' };
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let finalOutput = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        let currentEvent = '';
        let currentData = '';

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            currentData = line.slice(6);
          } else if (line === '' && currentEvent) {
            try {
              const data = JSON.parse(currentData) as Record<string, unknown>;
              const sseEvent: SSEEvent = {
                event: currentEvent as SSEEvent['event'],
                data,
              };
              onSSEEvent(sseEvent);

              if (currentEvent === 'completion') {
                finalOutput = (data.text as string) ?? '';
              }
            } catch {
              // Skip malformed events
            }
            currentEvent = '';
            currentData = '';
          }
        }
      }
    } finally {
      reader.releaseLock();
    }

    return { success: true, output: finalOutput };
  }

  // ── Competitive Pipeline ──

  async streamCompetitivePipeline(
    req: CompetitivePipelineRequest,
    onSSEEvent: (event: SSEEvent) => void,
  ): Promise<{ success: boolean; output: string; error?: string }> {
    const url = `${this.baseUrl}/competitive`;
    return this._streamSSE(url, req, onSSEEvent);
  }

  async approveCompetitiveDesign(
    id: string,
    approved: boolean,
    projectRoot: string,
    feedback?: string,
  ): Promise<CompetitiveDesignResponse> {
    const req: CompetitiveApprovalRequest = { approved, feedback };
    return this.request<CompetitiveDesignResponse>(
      'POST',
      `/competitive/${id}/approve?project_root=${encodeURIComponent(projectRoot)}`,
      req,
    );
  }

  async getCompetitiveDesign(
    id: string,
    projectRoot: string,
  ): Promise<CompetitiveDesignResponse> {
    return this.request<CompetitiveDesignResponse>(
      'GET',
      `/competitive/${id}?project_root=${encodeURIComponent(projectRoot)}`,
    );
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
      case 'RenderModel':
        return this.request('POST', '/tools/render', input);
      case 'SearchVault':
        return this.request('POST', '/vault/search', input);
      default:
        return { success: false, error: `Unknown remote tool: ${toolName}` };
    }
  }
}
