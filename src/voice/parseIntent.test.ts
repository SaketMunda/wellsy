import { describe, expect, it } from 'vitest';
import { parseIntent } from './parseIntent';
import intentCases from '../../spec/intent-cases.json';

// Day 10 (decisions.md D37): cases live in spec/intent-cases.json, shared
// with engine/test_intent.py — one spec, two implementations. Add a case
// there, not here.
describe('parseIntent (shared spec/intent-cases.json)', () => {
  for (const { name, transcript, intent } of intentCases.cases) {
    it(name, () => {
      expect(parseIntent(transcript)).toEqual(intent);
    });
  }
});
