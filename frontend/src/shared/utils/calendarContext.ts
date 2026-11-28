import { dateInTimezone } from './timezone';

export function calendarContext(params: URLSearchParams, defaultZone: string) {
  const requestedZone = params.get('calendar_timezone');
  let timezone = requestedZone || defaultZone;
  let invalid = false;
  try { dateInTimezone(timezone); } catch { timezone = defaultZone; invalid = true; }
  const requestedDate = params.get('calendar_date');
  let date = requestedDate || dateInTimezone(timezone);
  const parsed = new Date(date + 'T00:00:00Z');
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== date) {
    date = dateInTimezone(timezone); invalid = true;
  }
  return { date, timezone, invalid };
}
