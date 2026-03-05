import { jest, describe, it, expect, beforeEach } from '@jest/globals';
import { BackendClient } from '../../backend/client.js';

// Helper to build a ReadableStream from SSE text
function sseStream(text: string): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(text));
      controller.close();
    },
  });
}

beforeEach(() => {
  jest.restoreAllMocks();
});

describe('BackendClient', () => {
  const client = new BackendClient('http://localhost:8741');

  describe('health()', () => {
    it('calls GET /health', async () => {
      const spy = jest.spyOn(globalThis, 'fetch').mockResolvedValue(
        new Response(JSON.stringify({ status: 'ok' }), { status: 200 }),
      );

      const result = await client.health();
      expect(result).toEqual({ status: 'ok' });
      expect(spy).toHaveBeenCalledWith(
        'http://localhost:8741/health',
        expect.objectContaining({ method: 'GET' }),
      );
    });
  });

  describe('request() error handling', () => {
    it('throws on non-OK response with status and body', async () => {
      jest.spyOn(globalThis, 'fetch').mockResolvedValue(
        new Response('Not found', { status: 404 }),
      );

      await expect(client.health()).rejects.toThrow('Engine API error 404: Not found');
    });
  });

  describe('streamCompetitivePipeline', () => {
    it('uses /competitive for new designs (no design_id)', async () => {
      const spy = jest.spyOn(globalThis, 'fetch').mockResolvedValue(
        new Response(sseStream(''), { status: 200 }),
      );

      await client.streamCompetitivePipeline(
        { prompt: 'test', project_root: '/tmp' } as any,
        () => {},
      );

      expect(spy).toHaveBeenCalledWith(
        'http://localhost:8741/competitive',
        expect.anything(),
      );
    });

    it('uses /competitive/{id}/execute for refinement', async () => {
      const spy = jest.spyOn(globalThis, 'fetch').mockResolvedValue(
        new Response(sseStream(''), { status: 200 }),
      );

      await client.streamCompetitivePipeline(
        { prompt: 'refine', project_root: '/tmp', design_id: 'abc-123' } as any,
        () => {},
      );

      expect(spy).toHaveBeenCalledWith(
        'http://localhost:8741/competitive/abc-123/execute',
        expect.anything(),
      );
    });
  });

  describe('SSE parsing', () => {
    it('parses well-formed events and invokes callback', async () => {
      const sseText = [
        'event: status',
        'data: {"message":"working"}',
        '',
        'event: completion',
        'data: {"text":"done"}',
        '',
        '',
      ].join('\n');

      jest.spyOn(globalThis, 'fetch').mockResolvedValue(
        new Response(sseStream(sseText), { status: 200 }),
      );

      const events: any[] = [];
      const result = await client.streamCompetitivePipeline(
        { prompt: 'test', project_root: '/tmp' } as any,
        (ev) => events.push(ev),
      );

      expect(events).toHaveLength(2);
      expect(events[0].event).toBe('status');
      expect(events[0].data.message).toBe('working');
      expect(result.output).toBe('done');
    });

    it('captures completion event output', async () => {
      const sseText = [
        'event: completion',
        'data: {"text":"final output"}',
        '',
        '',
      ].join('\n');

      jest.spyOn(globalThis, 'fetch').mockResolvedValue(
        new Response(sseStream(sseText), { status: 200 }),
      );

      const result = await client.streamCompetitivePipeline(
        { prompt: 'test', project_root: '/tmp' } as any,
        () => {},
      );

      expect(result.success).toBe(true);
      expect(result.output).toBe('final output');
    });

    it('skips malformed JSON without throwing', async () => {
      const sseText = [
        'event: status',
        'data: {not valid json}',
        '',
        'event: completion',
        'data: {"text":"ok"}',
        '',
        '',
      ].join('\n');

      jest.spyOn(globalThis, 'fetch').mockResolvedValue(
        new Response(sseStream(sseText), { status: 200 }),
      );

      const events: any[] = [];
      const result = await client.streamCompetitivePipeline(
        { prompt: 'test', project_root: '/tmp' } as any,
        (ev) => events.push(ev),
      );

      // Malformed event skipped, only completion parsed
      expect(events).toHaveLength(1);
      expect(result.output).toBe('ok');
    });
  });
});
