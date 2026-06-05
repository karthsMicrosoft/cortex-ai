import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { extract, type ExtractedDeadline } from '../services/dateExtractor';

type ExpectedDeadline = ExtractedDeadline | null;

interface FixtureCase {
  name: string;
  input: string;
  expected: ExpectedDeadline;
}

interface Fixture {
  now: string;
  tz: string;
  cases: FixtureCase[];
}

const testDir = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(
  readFileSync(resolve(testDir, '../../../backend/tests/fixtures/deadline_extractor_cases.json'), 'utf-8'),
) as Fixture;

function normalize(value: ExpectedDeadline): ExpectedDeadline {
  if (!value) return null;
  return {
    ...value,
    ...(value.due_at ? { due_at: new Date(value.due_at).toISOString() } : {}),
  };
}

describe('dateExtractor', () => {
  it.each(fixture.cases)('$name', (testCase) => {
    const result = extract(testCase.input, {
      now: new Date(fixture.now),
      tz: fixture.tz,
    });

    if (testCase.expected === null) {
      expect(result).toBeNull();
      return;
    }

    expect(normalize(result)).toEqual(normalize(testCase.expected));
  });

  it('returns null for an empty string', () => {
    expect(extract('', { now: new Date(fixture.now), tz: fixture.tz })).toBeNull();
  });

  it('returns null for whitespace', () => {
    expect(extract('   \n\t  ', { now: new Date(fixture.now), tz: fixture.tz })).toBeNull();
  });

  it('extracts priority without a date', () => {
    expect(extract('Follow up with the vendor #medium', { now: new Date(fixture.now), tz: fixture.tz })).toEqual({
      priority: 2,
    });
  });
});
