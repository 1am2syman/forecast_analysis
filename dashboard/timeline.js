/* Planner timeline calculations shared by the dashboard and validation scripts. */
((root, factory) => {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.ForecastTimeline = api;
})(typeof globalThis === "undefined" ? window : globalThis, () => {
  const ISO_MONTH = /^\d{4}-\d{2}-01$/;

  function monthNumber(value) {
    if (!ISO_MONTH.test(String(value))) return null;
    const [year, month] = String(value).split("-").map(Number);
    if (month < 1 || month > 12) return null;
    return year * 12 + month - 1;
  }

  function monthFromNumber(value) {
    const year = Math.floor(value / 12);
    const month = (value % 12) + 1;
    return `${year}-${String(month).padStart(2, "0")}-01`;
  }

  function normalizeMonths(values) {
    return [
      ...new Set((values || []).filter((value) => monthNumber(value) !== null)),
    ].sort((left, right) => monthNumber(left) - monthNumber(right));
  }

  function clampRange(months, start, end) {
    const available = normalizeMonths(months);
    if (!available.length) return { start: null, end: null };
    const startNumber = monthNumber(start);
    const endNumber = monthNumber(end);
    let startIndex =
      startNumber === null
        ? 0
        : available.findIndex((value) => monthNumber(value) >= startNumber);
    if (startIndex < 0) startIndex = available.length - 1;
    let endIndex =
      endNumber === null
        ? available.length - 1
        : available.findLastIndex((value) => monthNumber(value) <= endNumber);
    if (endIndex < 0) endIndex = 0;
    if (startIndex > endIndex) startIndex = endIndex;
    return { start: available[startIndex], end: available[endIndex] };
  }

  function latestCompleteQuarterEnd(months, referenceEnd) {
    const available = normalizeMonths(months);
    if (!available.length) return null;
    const referenceNumber =
      monthNumber(referenceEnd) ?? monthNumber(available.at(-1));
    const completeEnds = available.filter((value) => {
      const number = monthNumber(value);
      return number <= referenceNumber && (number + 1) % 3 === 0;
    });
    return (
      completeEnds.at(-1) ||
      available.findLast((value) => monthNumber(value) <= referenceNumber) ||
      available[0]
    );
  }

  function rangeForPreset(
    months,
    durationMonths,
    grain = "month",
    referenceEnd = null,
  ) {
    const available = normalizeMonths(months);
    const duration = Number(durationMonths);
    if (!available.length || !Number.isInteger(duration) || duration < 1)
      return { start: null, end: null };
    const requestedEnd =
      grain === "quarter"
        ? latestCompleteQuarterEnd(available, referenceEnd)
        : clampRange(available, null, referenceEnd).end;
    const endIndex = available.indexOf(requestedEnd);
    const targetStart = monthFromNumber(
      monthNumber(requestedEnd) - duration + 1,
    );
    const firstAtOrAfter = available.findIndex(
      (value) => monthNumber(value) >= monthNumber(targetStart),
    );
    const startIndex = Math.max(0, Math.min(endIndex, firstAtOrAfter));
    return { start: available[startIndex], end: available[endIndex] };
  }

  function inclusiveMonthCount(start, end) {
    const startNumber = monthNumber(start);
    const endNumber = monthNumber(end);
    if (startNumber === null || endNumber === null || startNumber > endNumber)
      return 0;
    return endNumber - startNumber + 1;
  }

  function matchingPreset(
    months,
    start,
    end,
    grain,
    durations = [3, 6, 12, 24],
  ) {
    return (
      durations.find((duration) => {
        const range = rangeForPreset(months, duration, grain, end);
        return (
          inclusiveMonthCount(range.start, range.end) === Number(duration) &&
          range.start === start &&
          range.end === end
        );
      }) ?? null
    );
  }

  function rangeFromIndices(months, startIndex, endIndex) {
    const available = normalizeMonths(months);
    if (!available.length) return { start: null, end: null };
    const left = Math.max(
      0,
      Math.min(available.length - 1, Number(startIndex)),
    );
    const right = Math.max(
      left,
      Math.min(available.length - 1, Number(endIndex)),
    );
    return { start: available[left], end: available[right] };
  }

  function indexRange(months, start, end) {
    const available = normalizeMonths(months);
    const range = clampRange(available, start, end);
    return {
      start: Math.max(0, available.indexOf(range.start)),
      end: Math.max(0, available.indexOf(range.end)),
    };
  }

  function moveWindow(months, startIndex, endIndex, delta) {
    const available = normalizeMonths(months);
    const width = Math.max(0, Number(endIndex) - Number(startIndex));
    const nextStart = Math.max(
      0,
      Math.min(
        available.length - width - 1,
        Number(startIndex) + Number(delta),
      ),
    );
    return { start: nextStart, end: nextStart + width };
  }

  function quarterLabel(value) {
    const number = monthNumber(value);
    if (number === null) return "—";
    const year = Math.floor(number / 12);
    const quarter = Math.floor((number % 12) / 3) + 1;
    return `Q${quarter} ${year}`;
  }

  return {
    clampRange,
    inclusiveMonthCount,
    latestCompleteQuarterEnd,
    matchingPreset,
    monthFromNumber,
    monthNumber,
    indexRange,
    moveWindow,
    rangeFromIndices,
    normalizeMonths,
    quarterLabel,
    rangeForPreset,
  };
});
