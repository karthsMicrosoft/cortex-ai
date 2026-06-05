export type DeadlinePriority = 1 | 2 | 3;
export type DeadlineRecurring = 'daily' | 'weekly' | 'monthly';

export interface ExtractOptions {
  now: Date;
  tz: string;
}

export interface ExtractedDeadline {
  due_at?: string;
  priority?: DeadlinePriority;
  recurring?: DeadlineRecurring;
}

interface ZonedParts {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
}

const WEEKDAYS: Record<string, number> = {
  sunday: 0,
  monday: 1,
  tuesday: 2,
  wednesday: 3,
  thursday: 4,
  friday: 5,
  saturday: 6,
};

const formatterCache = new Map<string, Intl.DateTimeFormat>();

function pad(value: number, length = 2): string {
  return String(value).padStart(length, '0');
}

function getFormatter(tz: string): Intl.DateTimeFormat {
  const cached = formatterCache.get(tz);
  if (cached) return cached;

  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone: tz,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    hourCycle: 'h23',
  });
  formatterCache.set(tz, formatter);
  return formatter;
}

function getZonedParts(date: Date, tz: string): ZonedParts {
  const raw = getFormatter(tz).formatToParts(date);
  const parts: Partial<Record<Intl.DateTimeFormatPartTypes, string>> = {};
  for (const part of raw) {
    if (part.type !== 'literal') parts[part.type] = part.value;
  }

  const hour = Number(parts.hour ?? '0');
  return {
    year: Number(parts.year),
    month: Number(parts.month),
    day: Number(parts.day),
    hour: hour === 24 ? 0 : hour,
    minute: Number(parts.minute ?? '0'),
    second: Number(parts.second ?? '0'),
  };
}

function getOffsetMinutes(date: Date, tz: string): number {
  const parts = getZonedParts(date, tz);
  const zonedAsUtc = Date.UTC(
    parts.year,
    parts.month - 1,
    parts.day,
    parts.hour,
    parts.minute,
    parts.second,
  );
  return Math.round((zonedAsUtc - date.getTime()) / 60_000);
}

function makeZonedDate(parts: ZonedParts, tz: string): Date {
  const utcGuess = Date.UTC(
    parts.year,
    parts.month - 1,
    parts.day,
    parts.hour,
    parts.minute,
    parts.second,
  );
  const firstOffset = getOffsetMinutes(new Date(utcGuess), tz);
  let instant = new Date(utcGuess - firstOffset * 60_000);
  const secondOffset = getOffsetMinutes(instant, tz);
  if (secondOffset !== firstOffset) {
    instant = new Date(utcGuess - secondOffset * 60_000);
  }
  return instant;
}

function formatZonedIso(date: Date, tz: string): string {
  const parts = getZonedParts(date, tz);
  const offset = getOffsetMinutes(date, tz);
  const sign = offset >= 0 ? '+' : '-';
  const absOffset = Math.abs(offset);
  const offsetHours = Math.floor(absOffset / 60);
  const offsetMinutes = absOffset % 60;

  return `${pad(parts.year, 4)}-${pad(parts.month)}-${pad(parts.day)}T${pad(parts.hour)}:${pad(
    parts.minute,
  )}:${pad(parts.second)}${sign}${pad(offsetHours)}:${pad(offsetMinutes)}`;
}

function addLocalDays(parts: ZonedParts, days: number): ZonedParts {
  const date = new Date(Date.UTC(parts.year, parts.month - 1, parts.day + days));
  return {
    year: date.getUTCFullYear(),
    month: date.getUTCMonth() + 1,
    day: date.getUTCDate(),
    hour: parts.hour,
    minute: parts.minute,
    second: parts.second,
  };
}

function localDayOfWeek(parts: ZonedParts): number {
  return new Date(Date.UTC(parts.year, parts.month - 1, parts.day)).getUTCDay();
}

function localDateCompare(a: ZonedParts, b: ZonedParts): number {
  const aValue = Date.UTC(a.year, a.month - 1, a.day);
  const bValue = Date.UTC(b.year, b.month - 1, b.day);
  return Math.sign(aValue - bValue);
}

function withTime(parts: ZonedParts, hour: number, minute: number, second = 0): ZonedParts {
  return { ...parts, hour, minute, second };
}

function parseClock(raw: string | undefined): { hour: number; minute: number } | null {
  if (!raw) return null;
  const value = raw.trim().toLowerCase();
  if (value === 'noon') return { hour: 12, minute: 0 };
  if (value === 'midnight') return { hour: 0, minute: 0 };

  const match = value.match(/^(\d{1,2})(?::(\d{2}))?\s*(am|pm)$/i);
  if (!match) return null;

  let hour = Number(match[1]);
  const minute = Number(match[2] ?? '0');
  const meridiem = match[3].toLowerCase();
  if (hour < 1 || hour > 12 || minute > 59) return null;
  if (meridiem === 'am') hour = hour === 12 ? 0 : hour;
  if (meridiem === 'pm') hour = hour === 12 ? 12 : hour + 12;
  return { hour, minute };
}

function normalizeIsoDateTime(match: RegExpMatchArray, tz: string): string {
  const [, date, hour, minute, second = '00', offset] = match;
  if (offset) {
    return `${date}T${hour}:${minute}:${second}${offset.toUpperCase() === 'Z' ? '+00:00' : offset}`;
  }

  const [year, month, day] = date.split('-').map(Number);
  return formatZonedIso(
    makeZonedDate({ year, month, day, hour: Number(hour), minute: Number(minute), second: Number(second) }, tz),
    tz,
  );
}

function extractDueAt(text: string, options: ExtractOptions): string | undefined {
  const nowParts = getZonedParts(options.now, options.tz);

  const isoDateTime = text.match(
    /\b(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?(Z|[+-]\d{2}:\d{2})?\b/i,
  );
  if (isoDateTime) return normalizeIsoDateTime(isoDateTime, options.tz);

  const relative = text.match(/\bin\s+(\d+)\s+(hours?|days?|weeks?)\b/i);
  if (relative) {
    const amount = Number(relative[1]);
    const unit = relative[2].toLowerCase();
    if (unit.startsWith('hour')) {
      return formatZonedIso(new Date(options.now.getTime() + amount * 60 * 60 * 1000), options.tz);
    }
    const days = unit.startsWith('week') ? amount * 7 : amount;
    return formatZonedIso(makeZonedDate(withTime(addLocalDays(nowParts, days), 23, 59), options.tz), options.tz);
  }

  const eod = text.match(/\bby\s+(?:eod|end\s+of\s+day)\b/i);
  if (eod) return formatZonedIso(makeZonedDate(withTime(nowParts, 17, 0), options.tz), options.tz);

  const tonight = text.match(/\bby\s+tonight\b/i);
  if (tonight) return formatZonedIso(makeZonedDate(withTime(nowParts, 21, 0), options.tz), options.tz);

  const todayTomorrow = text.match(
    /\bby\s+(today|tomorrow)(?:\s+(noon|midnight|\d{1,2}(?::\d{2})?\s*(?:am|pm)))?\b/i,
  );
  if (todayTomorrow) {
    const dayOffset = todayTomorrow[1].toLowerCase() === 'tomorrow' ? 1 : 0;
    const targetDay = addLocalDays(nowParts, dayOffset);
    const clock = parseClock(todayTomorrow[2]) ?? { hour: 23, minute: 59 };
    return formatZonedIso(makeZonedDate(withTime(targetDay, clock.hour, clock.minute), options.tz), options.tz);
  }

  const byTime = text.match(/\bby\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))(?:\s+(today|tomorrow))?\b/i);
  if (byTime) {
    const clock = parseClock(byTime[1]);
    if (clock) {
      const explicitDay = byTime[2]?.toLowerCase();
      let targetDay = addLocalDays(nowParts, explicitDay === 'tomorrow' ? 1 : 0);
      let candidate = makeZonedDate(withTime(targetDay, clock.hour, clock.minute), options.tz);
      if (!explicitDay && candidate.getTime() <= options.now.getTime()) {
        targetDay = addLocalDays(nowParts, 1);
        candidate = makeZonedDate(withTime(targetDay, clock.hour, clock.minute), options.tz);
      }
      return formatZonedIso(candidate, options.tz);
    }
  }

  const weekday = text.match(
    /\bby\s+(next\s+)?(sunday|monday|tuesday|wednesday|thursday|friday|saturday)(?:\s+(?:at\s+)?(noon|midnight|\d{1,2}(?::\d{2})?\s*(?:am|pm)))?\b/i,
  );
  if (weekday) {
    const targetDow = WEEKDAYS[weekday[2].toLowerCase()];
    const currentDow = localDayOfWeek(nowParts);
    let delta = (targetDow - currentDow + 7) % 7;
    if (weekday[1] && delta === 0) delta = 7;

    const clock = parseClock(weekday[3]) ?? { hour: 23, minute: 59 };
    let targetDay = addLocalDays(nowParts, delta);
    let candidate = makeZonedDate(withTime(targetDay, clock.hour, clock.minute), options.tz);
    if (!weekday[1] && candidate.getTime() <= options.now.getTime()) {
      targetDay = addLocalDays(nowParts, delta + 7);
      candidate = makeZonedDate(withTime(targetDay, clock.hour, clock.minute), options.tz);
    }
    return formatZonedIso(candidate, options.tz);
  }

  const slashDate = text.match(/\bby\s+(\d{1,2})\/(\d{1,2})(?:\/(\d{2,4}))?\b/i);
  if (slashDate) {
    const month = Number(slashDate[1]);
    const day = Number(slashDate[2]);
    let year = slashDate[3] ? Number(slashDate[3]) : nowParts.year;
    if (year < 100) year += 2000;
    let target = withTime({ year, month, day, hour: 0, minute: 0, second: 0 }, 23, 59);
    if (!slashDate[3] && localDateCompare(target, nowParts) < 0) {
      target = { ...target, year: year + 1 };
    }
    return formatZonedIso(makeZonedDate(target, options.tz), options.tz);
  }

  const isoDate = text.match(/\b(\d{4})-(\d{2})-(\d{2})\b/i);
  if (isoDate) {
    const target = {
      year: Number(isoDate[1]),
      month: Number(isoDate[2]),
      day: Number(isoDate[3]),
      hour: 23,
      minute: 59,
      second: 0,
    };
    return formatZonedIso(makeZonedDate(target, options.tz), options.tz);
  }

  return undefined;
}

export function extract(text: string, options: ExtractOptions): ExtractedDeadline | null {
  if (!text.trim()) return null;

  const result: ExtractedDeadline = {};
  const dueAt = extractDueAt(text, options);
  if (dueAt) result.due_at = dueAt;

  if (/\#(?:p1|high)\b/i.test(text)) result.priority = 1;
  else if (/\#(?:p2|medium)\b/i.test(text)) result.priority = 2;
  else if (/\#(?:p3|low)\b/i.test(text)) result.priority = 3;

  const recurring = text.match(/\#(daily|weekly|monthly)\b/i);
  if (recurring) result.recurring = recurring[1].toLowerCase() as DeadlineRecurring;

  return Object.keys(result).length > 0 ? result : null;
}
