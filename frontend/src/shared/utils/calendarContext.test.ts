import { describe, it, expect } from 'vitest';
import { calendarContext } from './calendarContext';
describe('calendar URL context', () => {
 it('reads an exact day and zone', () => expect(calendarContext(new URLSearchParams('calendar_date=2032-01-02&calendar_timezone=Pacific%2FHonolulu'),'Asia/Riyadh')).toEqual({date:'2032-01-02',timezone:'Pacific/Honolulu',invalid:false}));
 for(const date of ['2032-02-30','not-a-date','2032-1-2'])it('rejects invalid date '+date,()=>{const value=calendarContext(new URLSearchParams({calendar_date:date}),'Asia/Riyadh');expect(value.invalid).toBe(true);expect(value.date).not.toBe(date);});
 it('rejects an invalid zone without losing a valid date',()=>expect(calendarContext(new URLSearchParams('calendar_date=2032-01-02&calendar_timezone=invalid-zone'),'Asia/Riyadh')).toEqual({date:'2032-01-02',timezone:'Asia/Riyadh',invalid:true}));
});
