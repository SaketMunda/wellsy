import { describe, expect, it } from 'vitest';
import { parseIntent } from './parseIntent';

describe('parseIntent', () => {
  it('parses wake', () => {
    expect(parseIntent('wake up')).toEqual({ type: 'wake' });
    expect(parseIntent('Hey YAP')).toEqual({ type: 'wake' });
  });

  it('parses sleep, including its synonyms', () => {
    expect(parseIntent('go to sleep')).toEqual({ type: 'sleep' });
    expect(parseIntent('be quiet')).toEqual({ type: 'sleep' });
    expect(parseIntent('shut up')).toEqual({ type: 'sleep' });
  });

  it('parses stop, and stop wins even inside a longer sentence', () => {
    expect(parseIntent('stop')).toEqual({ type: 'stop' });
    expect(parseIntent('please stop now')).toEqual({ type: 'stop' });
  });

  it('parses describe_scene', () => {
    expect(parseIntent('what do you see')).toEqual({ type: 'describe_scene' });
    expect(parseIntent("what's in front of you?")).toEqual({ type: 'describe_scene' });
    expect(parseIntent('describe the scene')).toEqual({ type: 'describe_scene' });
  });

  it('parses query_object and extracts the object, stripping determiners', () => {
    expect(parseIntent('do you see a laptop')).toEqual({ type: 'query_object', object: 'laptop' });
    expect(parseIntent('is there a person?')).toEqual({ type: 'query_object', object: 'person' });
    expect(parseIntent('can you see the bottle')).toEqual({ type: 'query_object', object: 'bottle' });
  });

  it('parses help', () => {
    expect(parseIntent('what can you do')).toEqual({ type: 'help' });
    expect(parseIntent('help')).toEqual({ type: 'help' });
  });

  it('falls through to unknown for off-script phrasing, and never improvises', () => {
    expect(parseIntent('could you tell me what is around')).toEqual({
      type: 'unknown',
      transcript: 'could you tell me what is around',
    });
    expect(parseIntent('')).toEqual({ type: 'unknown', transcript: '' });
    expect(parseIntent('tell me a joke')).toEqual({ type: 'unknown', transcript: 'tell me a joke' });
  });

  it('is case- and punctuation-insensitive', () => {
    expect(parseIntent('STOP!')).toEqual({ type: 'stop' });
    expect(parseIntent('  Wake Up.  ')).toEqual({ type: 'wake' });
  });
});
