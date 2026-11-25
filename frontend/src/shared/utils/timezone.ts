export function localDateTimeToUtcISOString(value: string, timeZone: string): string {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) throw new Error("حدد تاريخاً ووقتاً صالحين.");
  const [year, month, day, hour, minute] = value.split(/[-T:]/).map(Number);
  const wall = Date.UTC(year, month - 1, day, hour, minute);
  if (new Date(wall).toISOString().slice(0, 16) !== value) throw new Error("التاريخ أو الوقت غير صالح.");
  // Sample both sides of timezone transitions. Keep every matching instant so
  // a repeated clock hour is rejected rather than silently choosing one fold.
  const offsets = new Set<number>();
  for (let h = -36; h <= 36; h += 6) {
    const instant = wall + h * 3600000;
    const local = utcISOStringToLocalDateTime(new Date(instant).toISOString(), timeZone);
    offsets.add(Date.parse(local + ":00Z") - instant);
  }
  const matches = [...offsets].map(offset => new Date(wall - offset).toISOString())
    .filter(instant => utcISOStringToLocalDateTime(instant, timeZone) === value);
  if (matches.length === 0) throw new Error("هذا الوقت غير موجود في المنطقة الزمنية المختارة. اختر وقتاً آخر.");
  if (matches.length > 1) throw new Error("هذا الوقت يتكرر بسبب تغيير الساعة. اختر وقتاً غير ملتبس.");
  return matches[0];
}

export function dateInTimezone(timeZone: string, at: Date = new Date()): string {
  return utcISOStringToLocalDateTime(at.toISOString(), timeZone).slice(0, 10);
}


export function utcISOStringToLocalDateTime(value: string, timeZone: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) throw new Error("Invalid UTC datetime.");
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
  const parts = Object.fromEntries(formatter.formatToParts(date).map((part) => [part.type, part.value]));
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}


export function scheduleTimePreview(start: string, zone: string, interval: number, count: number): string[] {
  if (!Number.isInteger(interval) || interval < 1 || interval > 10080) throw new Error("الفاصل عدد صحيح من1إلى10080دقيقة.");
  const first = Date.parse(localDateTimeToUtcISOString(start, zone));
  return Array.from({length: count}, (_, index) => new Date(first + index * interval * 60000).toISOString());
}
