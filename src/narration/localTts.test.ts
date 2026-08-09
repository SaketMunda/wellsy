import { describe, expect, it, vi } from 'vitest';
import { createLocalTtsAdapter, type RawAudioLike, type TtsStatus } from './speech';

function fakeAudio(): RawAudioLike {
  return { audio: new Float32Array([0, 0.1, -0.1]), sampling_rate: 24000 };
}

describe('createLocalTtsAdapter', () => {
  it('loads the model once, plays the generated audio, and reports synth latency', async () => {
    const statuses: TtsStatus[] = [];
    const playAudio = vi.fn();
    const model = { generate: vi.fn(async () => fakeAudio()) };
    const loadModel = vi.fn(async (onProgress: (p: number) => void) => {
      onProgress(0.5);
      onProgress(1);
      return model;
    });
    const adapter = createLocalTtsAdapter(
      { loadModel, playAudio, stopAudio: vi.fn() },
      (s) => statuses.push(s),
    );

    await adapter.speak('the bottle has left.');

    expect(loadModel).toHaveBeenCalledTimes(1);
    expect(model.generate).toHaveBeenCalledWith('the bottle has left.');
    expect(playAudio).toHaveBeenCalledTimes(1);
    expect(adapter.getStatus().state).toBe('ready');
    expect(adapter.getStatus().lastSynthMs).not.toBeNull();
    expect(statuses.some((s) => s.state === 'loading')).toBe(true);
  });

  it('does not reload the model on a second call', async () => {
    const loadModel = vi.fn(async () => ({ generate: vi.fn(async () => fakeAudio()) }));
    const adapter = createLocalTtsAdapter({ loadModel, playAudio: vi.fn(), stopAudio: vi.fn() }, () => {});
    await adapter.speak('one');
    await adapter.speak('two');
    expect(loadModel).toHaveBeenCalledTimes(1);
  });

  it('rejects and reports an error status when the model fails to load', async () => {
    const statuses: TtsStatus[] = [];
    const loadModel = vi.fn(async () => {
      throw new Error('onnx runtime blew up');
    });
    const adapter = createLocalTtsAdapter(
      { loadModel, playAudio: vi.fn(), stopAudio: vi.fn() },
      (s) => statuses.push(s),
    );

    await expect(adapter.speak('hello')).rejects.toThrow();
    expect(statuses.some((s) => s.state === 'error')).toBe(true);
  });

  it('reports "unavailable" (not "error") when the environment cannot run it', async () => {
    const statuses: TtsStatus[] = [];
    const loadModel = vi.fn(async () => {
      throw Object.assign(new Error('no audio context'), { yapUnavailable: true });
    });
    const adapter = createLocalTtsAdapter(
      { loadModel, playAudio: vi.fn(), stopAudio: vi.fn() },
      (s) => statuses.push(s),
    );

    await expect(adapter.speak('hello')).rejects.toThrow();
    expect(statuses.some((s) => s.state === 'unavailable')).toBe(true);
  });

  it('stop() delegates to stopAudio, cutting off in-flight synthesis rather than just the next line', () => {
    const stopAudio = vi.fn();
    const adapter = createLocalTtsAdapter(
      { loadModel: vi.fn(), playAudio: vi.fn(), stopAudio },
      () => {},
    );
    adapter.stop();
    expect(stopAudio).toHaveBeenCalledTimes(1);
  });
});
