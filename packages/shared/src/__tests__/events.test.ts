import { makeEvent, EventType } from '../events.js';

describe('makeEvent', () => {
  it('returns correct shape', () => {
    const event = makeEvent(EventType.STATUS, { message: 'hello' });
    expect(event).toHaveProperty('type', EventType.STATUS);
    expect(event).toHaveProperty('data');
    expect(event.data.message).toBe('hello');
    expect(event).toHaveProperty('timestamp');
  });

  it('has ISO-format timestamp', () => {
    const event = makeEvent(EventType.TEXT, { text: 'abc' });
    expect(event.timestamp).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);
  });
});

describe('EventType', () => {
  it('has STATUS member', () => {
    expect(EventType.STATUS).toBe('status');
  });

  it('has COMPETITIVE_STATUS member', () => {
    expect(EventType.COMPETITIVE_STATUS).toBe('competitive_status');
  });

  it('has COMPETITIVE_FIDELITY member', () => {
    expect(EventType.COMPETITIVE_FIDELITY).toBe('competitive_fidelity');
  });
});
