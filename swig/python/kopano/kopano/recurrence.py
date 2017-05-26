"""
Part of the high-level python bindings for Kopano

Copyright 2005 - 2016 Zarafa and its licensors (see LICENSE file for details)
Copyright 2016 - Kopano and its licensors (see LICENSE file for details)
"""

import datetime
import libfreebusy
import struct
import sys
import time

from MAPI import (
    MAPI_UNICODE, KEEP_OPEN_READWRITE, MODRECIP_ADD, MODRECIP_MODIFY,
)

from MAPI.Tags import (
    PR_MESSAGE_CLASS_W, PR_ATTACH_NUM, PR_ATTACH_FLAGS, PR_ATTACHMENT_FLAGS,
    PR_ATTACHMENT_HIDDEN, PR_ATTACH_METHOD, PR_DISPLAY_NAME_W,
    PR_EXCEPTION_STARTTIME, PR_EXCEPTION_ENDTIME, PR_HASATTACH,
    PR_NORMALIZED_SUBJECT_W, PR_ATTACHMENT_LINKID, PR_ICON_INDEX,
    PR_MESSAGE_RECIPIENTS, IID_IMAPITable, PR_RECIPIENT_FLAGS,
    PR_MESSAGE_FLAGS, PR_RECIPIENT_TRACKSTATUS,
)

from MAPI.Defs import (
    HrGetOneProp, PpropFindProp,
)

from MAPI.Struct import (
    SPropValue,
)

from MAPI.Time import (
    unixtime,
)

from dateutil.rrule import (
    DAILY, WEEKLY, MONTHLY, MO, TU, TH, FR, WE, SA, SU, rrule, rruleset
)
from datetime import timedelta

from .compat import repr as _repr
from .defs import (
    ARO_SUBJECT, ARO_MEETINGTYPE, ARO_REMINDERDELTA, ARO_REMINDERSET,
    ARO_LOCATION, ARO_BUSYSTATUS, ARO_ATTACHMENT, ARO_SUBTYPE,
    ARO_APPTCOLOR
)

if sys.hexversion >= 0x03000000:
    from . import utils as _utils
    from . import meetingrequest as _meetingrequest
else:
    import utils as _utils
    import meetingrequest as _meetingrequest

SHORT, LONG = 2, 4

PidLidSideEffects = "PT_LONG:common:0x8510"
PidLidSmartNoAttach = "PT_BOOLEAN:common:0x8514"
PidLidReminderDelta = 'PT_LONG:common:0x8501'
PidLidReminderSet = "PT_BOOLEAN:common:0x8503"
PidLidReminderSignalTime = "PT_SYSTIME:common:0x8560"
PidLidReminderDelta = "PT_LONG:common:0x8501"
PidLidBusyStatus = "PT_LONG:appointment:0x8205"
PidLidExceptionReplaceTime = "PT_SYSTIME:appointment:0x8228"
PidLidAppointmentSubType = "PT_BOOLEAN:appointment:0x8215"
PidLidResponseStatus = "PT_LONG:appointment:0x8218"

# XXX check with MS-OXOCAL, section 2.2.1.44, and use same naming
# XXX run parse/save with lots of existing data (data should not change)

class Recurrence(object):
    def __init__(self, item):
        # XXX add check if we actually have a recurrence, otherwise we throw a mapi exception which might not be desirable

        self.item = item
        self.tz = item.get_value('appointment:33331')
        self._parse()

    def _parse(self):
        value = self.item.prop('appointment:33302').value # recurrencestate

        self.recurrence_frequency = _utils.unpack_short(value, 2 * SHORT)
        self.patterntype = _utils.unpack_short(value, 3 * SHORT)
        self.calendar_type = _utils.unpack_short(value, 4 * SHORT)
        self.first_datetime = _utils.unpack_long(value, 5 * SHORT)
        self.period = _utils.unpack_long(value, 5 * SHORT + LONG) # 12 for year, coincedence?
        self.regen = _utils.unpack_long(value, 5 * SHORT + 2 * LONG)

        pos = 5 * SHORT + 3 * LONG

        if self.patterntype == 1: # Weekly recurrence
            self.pattern = _utils.unpack_long(value, pos) # WeekDays
            pos += LONG
        if self.patterntype in (2, 4, 10, 12): # Monthly recurrence
            self.pattern = _utils.unpack_long(value, pos) # Day Of Month
            pos += LONG
        elif self.patterntype in (3, 11): # Yearly recurrence
            weekday = _utils.unpack_long(value, pos)
            pos += LONG
            weeknumber = _utils.unpack_long(value, pos)
            pos += LONG

        self.endtype = _utils.unpack_long(value, pos)
        pos += LONG
        self.occurrence_count = _utils.unpack_long(value, pos)
        pos += LONG
        self.first_dow = _utils.unpack_long(value, pos)
        pos += LONG

        # deleted dates
        self.delcount = _utils.unpack_long(value, pos)
        pos += LONG
        self.del_vals = []
        for _ in range(0, self.delcount):
            self.del_vals.append(_utils.unpack_long(value, pos))
            pos += LONG

        # modified dates
        self.modcount = _utils.unpack_long(value, pos)
        pos += LONG

        self.mod_vals = []
        for _ in range(0, self.modcount):
            self.mod_vals.append(_utils.unpack_long(value, pos))
            pos += LONG

        self.start_val = _utils.unpack_long(value, pos)
        pos += LONG
        self.end_val = _utils.unpack_long(value, pos)
        pos += LONG

        self.reader_version = _utils.unpack_long(value, pos)
        pos += LONG
        self.writer_version = _utils.unpack_long(value, pos)
        pos += LONG
        self.starttime_offset = _utils.unpack_long(value, pos)
        pos += LONG
        self.endtime_offset = _utils.unpack_long(value, pos)
        pos += LONG

        # exceptions
        self.exception_count = _utils.unpack_short(value, pos)
        pos += SHORT

        self.exceptions = []
        for i in range(0, self.exception_count):
            exception = {}

            val = _utils.unpack_long(value, pos)
            exception['startdatetime_val'] = val
            pos += LONG
            val = _utils.unpack_long(value, pos)
            exception['enddatetime_val'] = val
            pos += LONG
            val = _utils.unpack_long(value, pos)
            exception['originalstartdate_val'] = val
            pos += LONG
            exception['overrideflags'] = _utils.unpack_short(value, pos)
            pos += SHORT

            # We have modified the subject
            if exception['overrideflags'] & ARO_SUBJECT:
                subject_length1 = _utils.unpack_short(value, pos) # XXX: unused?
                pos += SHORT
                subject_length2 = _utils.unpack_short(value, pos)
                pos += SHORT
                exception['subject'] = value[pos:pos+subject_length2]
                pos += subject_length2

            if exception['overrideflags'] & ARO_MEETINGTYPE:
                exception['meetingtype'] = _utils.unpack_long(value, pos)
                pos += LONG

            if exception['overrideflags'] & ARO_REMINDERDELTA:
                exception['reminderdelta'] = _utils.unpack_long(value, pos) # XXX: datetime?
                pos += LONG

            if exception['overrideflags'] & ARO_REMINDERSET:
                exception['reminderset'] = _utils.unpack_long(value, pos) # XXX: bool?
                pos += LONG

            if exception['overrideflags'] & ARO_LOCATION:
                location_length1 = _utils.unpack_short(value, pos) # XXX: unused?
                pos += SHORT
                location_length2 = _utils.unpack_short(value, pos)
                pos += SHORT
                exception['location'] = value[pos:pos+location_length2]
                pos += location_length2

            if exception['overrideflags'] & ARO_BUSYSTATUS:
                exception['busystatus'] = _utils.unpack_long(value, pos)
                pos += LONG

            if exception['overrideflags'] & ARO_ATTACHMENT:
                exception['attachment'] = _utils.unpack_long(value, pos)
                pos += LONG

            if exception['overrideflags'] & ARO_SUBTYPE:
                exception['subtype'] = _utils.unpack_long(value, pos)
                pos += LONG

            if exception['overrideflags'] & ARO_APPTCOLOR:
                exception['color'] = _utils.unpack_long(value, pos)
                pos += LONG

            self.exceptions.append(exception)

        pos += LONG # XXX read actual blocksize, also elsewhere..

        # extended exceptions
        self.extended_exceptions = []
        for exception in self.exceptions:
            extended_exception = {}

            if self.writer_version >= 0x3009:
                chl_size = _utils.unpack_long(value, pos)
                pos += LONG
                extended_exception['change_highlight'] = _utils.unpack_long(value, pos)
                pos += chl_size

            pos += LONG # XXX actual blocksize

            if exception['overrideflags'] & ARO_SUBJECT or exception['overrideflags'] & ARO_LOCATION:
                extended_exception['startdatetime_val'] = _utils.unpack_long(value, pos)
                pos += LONG
                extended_exception['enddatetime_val'] = _utils.unpack_long(value, pos)
                pos += LONG
                extended_exception['originalstartdate_val'] = _utils.unpack_long(value, pos)
                pos += LONG

            if exception['overrideflags'] & ARO_SUBJECT:
                length = _utils.unpack_short(value, pos)
                pos += SHORT
                extended_exception['subject'] = value[pos:pos+2*length].decode('utf-16-le')
                pos += 2*length

            if exception['overrideflags'] & ARO_LOCATION:
                length = _utils.unpack_short(value, pos)
                pos += SHORT
                extended_exception['location'] = value[pos:pos+2*length].decode('utf-16-le')
                pos += 2*length

            self.extended_exceptions.append(extended_exception)

    def _save(self):
        data = struct.pack('<BBBBHI', 0x04, 0x30, 0x04, 0x30, self.recurrence_frequency, self.patterntype)

        if self.recurrence_frequency == 0x200b:
            # weekly
            data += struct.pack('<IIII', 0, self.period, 0, self.pattern) # XXX firstocc

        data += struct.pack('<I', self.endtype)

        # XXX php sets 0x2021 for an enddate!?
        if self.endtype == 0x2021: # stop after date XXX should compute in this case
            occurrence_count = 0xa
#        elif self.endtype == 0x2022: # stop after N occurrences
#            occurrence_count = self.occurrence_count
        else: # no end date XXX should be 0xa
            occurrence_count = 0
        data += struct.pack('<I', occurrence_count)

        if  self.recurrence_frequency == 0x200b and self.patterntype == 1: # XXX check doc
            data += struct.pack('<I', 1)
        else:
            data += struct.pack('<I', 0)

        data += struct.pack('<I', self.delcount)
        for val in self.del_vals:
            data += struct.pack('<I', val)

        data += struct.pack('<I', self.modcount)
        for val in self.mod_vals:
            data += struct.pack('<I', val)

        data += struct.pack('<II', self.start_val, self.end_val)

        data += struct.pack('<II', 0x3006, 0x3008)
        data += struct.pack('<II', self.starttime_offset, self.endtime_offset)

        # ExceptionInfo
        data += struct.pack('<H', self.modcount)
        for exception in self.exceptions:
            data += struct.pack('<I', exception['startdatetime_val'])
            data += struct.pack('<I', exception['enddatetime_val'])
            data += struct.pack('<I', exception['originalstartdate_val'])
            data += struct.pack('<H', exception['overrideflags'])

            if exception['overrideflags'] & ARO_SUBJECT:
                subject = exception['subject']
                data += struct.pack('<H', len(subject)+1)
                data += struct.pack('<H', len(subject))
                data += subject

            if exception['overrideflags'] & ARO_MEETINGTYPE:
                data += struct.pack('<I', exception['meetingtype'])

            if exception['overrideflags'] & ARO_REMINDERDELTA:
                data += struct.pack('<I', exception['reminderdelta'])

            if exception['overrideflags'] & ARO_REMINDERSET:
                data += struct.pack('<I', exception['reminderset'])

            if exception['overrideflags'] & ARO_LOCATION:
                location = exception['location']
                data += struct.pack('<H', len(location)+1)
                data += struct.pack('<H', len(location))
                data += location

            if exception['overrideflags'] & ARO_BUSYSTATUS:
                data += struct.pack('<I', exception['busystatus'])

            if exception['overrideflags'] & ARO_ATTACHMENT:
                data += struct.pack('<I', exception['attachment'])

            if exception['overrideflags'] & ARO_SUBTYPE:
                data += struct.pack('<I', exception['subtype'])

            if exception['overrideflags'] & ARO_APPTCOLOR:
                data += struct.pack('<I', exception['color'])

        data += struct.pack('<I', 0)

        # ExtendedException
        for exception, extended_exception in zip(self.exceptions, self.extended_exceptions):
            data += struct.pack('<I', 0)

            overrideflags = exception['overrideflags']

            if overrideflags & ARO_SUBJECT or overrideflags & ARO_LOCATION:
                data += struct.pack('<I', extended_exception['startdatetime_val'])
                data += struct.pack('<I', extended_exception['enddatetime_val'])
                data += struct.pack('<I', extended_exception['originalstartdate_val'])

            if overrideflags & ARO_SUBJECT:
                subject = extended_exception['subject']
                data += struct.pack('<H', len(subject))
                data += subject.encode('utf-16-le')

            if overrideflags & ARO_LOCATION:
                location = extended_exception['location']
                data += struct.pack('<H', len(location))
                data += location.encode('utf-16-le')

            if overrideflags & ARO_SUBJECT or overrideflags & ARO_LOCATION:
                data += struct.pack('<I', 0)

        data += struct.pack('<I', 0)

        self.item.prop('appointment:33302').value = data
        return data # XXX remove

    @property
    def _start(self):
        return datetime.datetime.fromtimestamp(_utils.rectime_to_unixtime(self.start_val)) + datetime.timedelta(minutes=self.starttime_offset) # XXX local time..

    @property
    def _end(self):
        return datetime.datetime.fromtimestamp(_utils.rectime_to_unixtime(self.end_val)) + datetime.timedelta(minutes=self.endtime_offset)# XXX local time..

    @property
    def _del_recurrences(self): # XXX local time..
        return [datetime.datetime.fromtimestamp(_utils.rectime_to_unixtime(val)) \
            for val in self.del_vals]

    @property
    def _mod_recurrences(self): # XXX local time..
        return [datetime.datetime.fromtimestamp(_utils.rectime_to_unixtime(val)) \
            for val in self.mod_vals]

    @property
    def recurrences(self):
        # FIXME; doesn't dateutil have a list of this?
        rrule_weekdays = {0: SU, 1: MO, 2: TU, 3: WE, 4: TH, 5: FR, 6: SA} # FIXME: remove above

        # FIXME: merge exception details with normal appointment data to recurrence.occurences() (Class occurence)
        if self.patterntype == 0: # DAILY
            recurrences = rrule(DAILY, dtstart=self._start, until=self._end, interval=self.period/(24*60))
        if self.patterntype == 1: # WEEKLY
            byweekday = () # Set
            for index, week in rrule_weekdays.items():
                if (self.pattern >> index ) & 1:
                    byweekday += (week,)
            # Setup our rule
            rule = rruleset()
            # FIXME: add one day, so that we don't miss the last recurrence, since the end date is for example 11-3-2015 on 1:00
            # But the recurrence is on 8:00 that day and we should include it.
            rule.rrule(rrule(WEEKLY, dtstart=self._start, until=self._end + timedelta(days=1), byweekday=byweekday))

            recurrences = rule
            # self.recurrences = rrule(WEEKLY, dtstart=self.start, until=self.end, byweekday=byweekday)
        elif self.patterntype == 2: # MONTHLY
            # X Day of every Y month(s)
            # The Xnd Y (day) of every Z Month(s)
            recurrences = rrule(MONTHLY, dtstart=self._start, until=self._end, bymonthday=self.pattern, interval=self.period)
            # self.pattern is either day of month or
        elif self.patterntype == 3: # MONTHY, YEARLY
            byweekday = () # Set
            for index, week in rrule_weekdays.items():
                if (weekday >> index ) & 1:
                    byweekday += (week(weeknumber),)
            # Yearly, the last XX of YY
            recurrences = rrule(MONTHLY, dtstart=self._start, until=self._end, interval=self.period, byweekday=byweekday)

        # Remove deleted ocurrences
        for del_date in self._del_recurrences:
            # XXX: Somehow rule.rdate does not work in combination with rule.exdate
            del_date = datetime.datetime(del_date.year, del_date.month, del_date.day, self._start.hour, self._start.minute)
            if del_date not in self._mod_recurrences:
                rule.exdate(del_date)

        # add exceptions
        for exception in self.exceptions:
            rule.rdate(datetime.datetime.fromtimestamp(_utils.rectime_to_unixtime(exception['startdatetime_val'])))

        return recurrences

    def exception_message(self, basedate):
        for message in self.item.items():
            if message.prop('appointment:33320').value.date() == basedate.date():
                return message

    def is_exception(self, basedate):
        return self.exception_message(basedate) is not None

    def _override_prop(self, proptag, cal_item, item):
        item_prop = item.get_prop(proptag) # XXX faster lookup
        return bool(item_prop)

    def _update_exceptions(self, cal_item, item, startdate_val, enddate_val, basedate_val, exception, extended_exception, copytags, create=False): # XXX kill copytags, create args, just pass all properties as in php
        exception['startdatetime_val'] = startdate_val
        exception['enddatetime_val'] = enddate_val
        exception['originalstartdate_val'] = basedate_val
        exception['overrideflags'] = 0

        extended = False
        if self._override_prop(PR_NORMALIZED_SUBJECT_W, cal_item, item):
            subject = item.value(PR_NORMALIZED_SUBJECT_W)
            exception['overrideflags'] |= ARO_SUBJECT
            exception['subject'] = subject.encode('cp1252', 'replace')
            extended = True
            extended_exception['subject'] = subject

        # skip ARO_MEETINGTYPE (like php)

        if self._override_prop(PidLidReminderDelta, cal_item, item):
            exception['overrideflags'] |= ARO_REMINDERDELTA
            exception['reminderdelta'] = item.value(PidLidReminderDelta)

        if self._override_prop(PidLidReminderSet, cal_item, item):
            exception['overrideflags'] |= ARO_REMINDERSET
            exception['reminderset'] = item.value(PidLidReminderSet)

        pidlid_location = 'appointment:33288'
        if self._override_prop(pidlid_location, cal_item, item):
            location = item.value(pidlid_location)
            exception['overrideflags'] |= ARO_LOCATION
            exception['location'] = location.encode('cp1252', 'replace')
            extended = True
            extended_exception['location'] = location

        pidlid_busystatus = 'appointment:33285'
        if self._override_prop(pidlid_busystatus, cal_item, item):
            exception['overrideflags'] |= ARO_BUSYSTATUS
            exception['busystatus'] = item.value(pidlid_busystatus)

        # skip ARO_ATTACHMENT (like php)

        # XXX php doesn't set the following by accident? ("alldayevent" not in copytags..)
        if not copytags or not create:
            pidlid_appointmentsubtype = 'appointment:33301'
            if self._override_prop(pidlid_appointmentsubtype, cal_item, item):
                exception['overrideflags'] |= ARO_SUBTYPE
                exception['subtype'] = item.value(pidlid_appointmentsubtype)

        pidlid_appointmentcolor = 'appointment:33300'
        if self._override_prop(pidlid_appointmentcolor, cal_item, item):
            exception['overrideflags'] |= ARO_APPTCOLOR
            exception['color'] = item.value(pidlid_appointmentcolor)

        if extended:
            extended_exception['startdatetime_val'] = startdate_val
            extended_exception['enddatetime_val'] = enddate_val
            extended_exception['originalstartdate_val'] = basedate_val

    def _update_calitem(self, item):
        tz = item.get_value('appointment:33331')
        cal_item = self.item

        cal_item.prop(PidLidSideEffects, create=True).value = 3441 # XXX check php
        cal_item.prop(PidLidSmartNoAttach, create=True).value = True

        # reminder
        if cal_item.prop(PidLidReminderSet).value:
            occs = list(cal_item.occurrences(datetime.datetime.now(), datetime.datetime(2038,1,1))) # XXX slow for daily?
            occs.sort(key=lambda occ: occ.start) # XXX check if needed
            for occ in occs: # XXX check default/reminder props
                dueby = _utils._to_gmt(occ.start, tz) - datetime.timedelta(minutes=cal_item.prop(PidLidReminderDelta).value)
                if dueby > datetime.datetime.now():
                    cal_item.prop(PidLidReminderSignalTime).value = dueby
                    break

    def _update_embedded(self, basedate, message, item, copytags=None, create=False):
        basetime = basedate + datetime.timedelta(minutes=self.starttime_offset)
        cal_item = self.item

        if copytags:
            props = item.mapiobj.GetProps(copytags, 0)
        else: # XXX remove?
            props = [p.mapiobj for p in item.props() if p.proptag != PR_ICON_INDEX]

        message.mapiobj.SetProps(props)

        message.prop(PR_MESSAGE_CLASS_W).value = u'IPM.OLE.CLASS.{00061055-0000-0000-C000-000000000046}'
        message.prop(PidLidExceptionReplaceTime, create=True).value = basetime

        intended_busystatus = cal_item.prop('appointment:33316').value # XXX tentative? merge with modify_exc?

        message.prop(PidLidBusyStatus, create=True).value = intended_busystatus

        message.prop(PidLidAppointmentSubType, create=True).value = cal_item.prop(PidLidAppointmentSubType).value

        start = message.prop('appointment:33293').value
        start_local = unixtime(time.mktime(_utils._from_gmt(start, self.tz).timetuple())) # XXX why local??

        end = message.prop('appointment:33294').value
        end_local = unixtime(time.mktime(_utils._from_gmt(end, self.tz).timetuple())) # XXX why local??

        props = [
            SPropValue(PR_ATTACHMENT_FLAGS, 2),
            SPropValue(PR_ATTACHMENT_HIDDEN, True),
            SPropValue(PR_ATTACHMENT_LINKID, 0),
            SPropValue(PR_ATTACH_FLAGS, 0),
            SPropValue(PR_ATTACH_METHOD, 5),
            SPropValue(PR_DISPLAY_NAME_W, u'Exception'),
            SPropValue(PR_EXCEPTION_STARTTIME, start_local),
            SPropValue(PR_EXCEPTION_ENDTIME, end_local),
        ]

        message._attobj.SetProps(props)
        if not create: # XXX php bug?
            props = props[:-2]
        message.mapiobj.SetProps(props)

        message.mapiobj.SaveChanges(KEEP_OPEN_READWRITE)
        message._attobj.SaveChanges(KEEP_OPEN_READWRITE)

    def create_exception(self, basedate, item, copytags=None, merge=False):
        tz = item.get_value('appointment:33331')
        cal_item = self.item

        # create embedded item
        message_flags = 1
        if item.prop(PR_MESSAGE_FLAGS).value == 0: # XXX wut/php compat
            message_flags = 9
        message = cal_item.create_item(message_flags)

        self._update_embedded(basedate, message, item, copytags, create=True)

        message.prop(PidLidResponseStatus).value = 5 # XXX php bug for merge case?
        if copytags:
            message.prop(PidLidBusyStatus).value = 0

        # copy over recipients (XXX check php delta stuff..)
        table = item.mapiobj.OpenProperty(PR_MESSAGE_RECIPIENTS, IID_IMAPITable, MAPI_UNICODE, 0)
        table.SetColumns(_meetingrequest.RECIP_PROPS, 0)
        recips = list(table.QueryRows(-1, 0))

        for recip in recips:
            flags = PpropFindProp(recip, PR_RECIPIENT_FLAGS)
            if not flags:
                recip.append(SPropValue(PR_RECIPIENT_FLAGS, 17)) # XXX

        if copytags:
            for recip in recips:
                recip.append(SPropValue(PR_RECIPIENT_FLAGS, 33)) # XXX
                recip.append(SPropValue(PR_RECIPIENT_TRACKSTATUS, 0)) # XXX

        organiser = _meetingrequest._organizer_props(message, item)
        if organiser and not merge: # XXX merge -> initialize?
            recips.insert(0, organiser)

        message.mapiobj.ModifyRecipients(MODRECIP_ADD, recips)

        message.mapiobj.SaveChanges(KEEP_OPEN_READWRITE)
        message._attobj.SaveChanges(KEEP_OPEN_READWRITE)
        cal_item.mapiobj.SaveChanges(KEEP_OPEN_READWRITE)

        # XXX attachments?

        # update blob
        self.delcount += 1
        deldate = _utils._from_gmt(basedate, tz)
        deldate_val = _utils.unixtime_to_rectime(time.mktime(deldate.timetuple()))
        self.del_vals.append(deldate_val)
        self.del_vals.sort()

        self.modcount += 1
        moddate = message.prop('appointment:33293').value
        daystart = moddate - datetime.timedelta(hours=moddate.hour, minutes=moddate.minute) # XXX different approach in php? seconds?
        localdaystart = _utils._from_gmt(daystart, tz)
        moddate_val = _utils.unixtime_to_rectime(time.mktime(localdaystart.timetuple()))
        self.mod_vals.append(moddate_val)
        self.mod_vals.sort()

        startdate = _utils._from_gmt(message.prop('appointment:33293').value, tz)
        startdate_val = _utils.unixtime_to_rectime(time.mktime(startdate.timetuple()))

        enddate = _utils._from_gmt(message.prop('appointment:33294').value, tz)
        enddate_val = _utils.unixtime_to_rectime(time.mktime(enddate.timetuple()))

        exception = {}
        extended_exception = {}
        self._update_exceptions(cal_item, message, startdate_val, enddate_val, deldate_val, exception, extended_exception, copytags, create=True)
        self.exceptions.append(exception) # no evidence of sorting
        self.extended_exceptions.append(extended_exception)

        self._save()

        # update calitem
        self._update_calitem(item)

    def modify_exception(self, basedate, item, copytags=None): # XXX 'item' too MR specific
        tz = item.get_value('appointment:33331')
        cal_item = self.item

        # update embedded item
        for message in cal_item.items(): # XXX no cal_item? to helper
            if message.prop('appointment:33320').value.date() == basedate.date():
                self._update_embedded(basedate, message, item, copytags)

                if not copytags:
                    message.prop(PR_ICON_INDEX).value = item.prop(PR_ICON_INDEX).value

                message._attobj.SaveChanges(KEEP_OPEN_READWRITE)

                break

        if copytags: # XXX bug in php code? (setallrecipients, !empty..)
            message.prop(PidLidBusyStatus).value = 0

            table = message.mapiobj.OpenProperty(PR_MESSAGE_RECIPIENTS, IID_IMAPITable, MAPI_UNICODE, 0)
            table.SetColumns(_meetingrequest.RECIP_PROPS, 0)

            recips = list(table.QueryRows(-1, 0))
            for recip in recips:
                flags = PpropFindProp(recip, PR_RECIPIENT_FLAGS)
                if flags and flags.Value != 3:
                    flags.Value = 33
                    trackstatus = PpropFindProp(recip, PR_RECIPIENT_TRACKSTATUS)
                    recip.append(SPropValue(PR_RECIPIENT_TRACKSTATUS, 0))

            message.mapiobj.ModifyRecipients(MODRECIP_MODIFY, recips)

            message.mapiobj.SaveChanges(KEEP_OPEN_READWRITE)
            message._attobj.SaveChanges(KEEP_OPEN_READWRITE)
            cal_item.mapiobj.SaveChanges(KEEP_OPEN_READWRITE)

        # update blob
        basedate_val = _utils.unixtime_to_rectime(time.mktime(_utils._from_gmt(basedate, tz).timetuple()))

        startdate = _utils._from_gmt(message.prop('appointment:33293').value, tz)
        startdate_val = _utils.unixtime_to_rectime(time.mktime(startdate.timetuple()))

        enddate = _utils._from_gmt(message.prop('appointment:33294').value, tz)
        enddate_val = _utils.unixtime_to_rectime(time.mktime(enddate.timetuple()))

        for i, exception in enumerate(self.exceptions):
            if exception['originalstartdate_val'] == basedate_val:
                current_startdate_val = exception['startdatetime_val'] - self.starttime_offset

                for j, val in enumerate(self.mod_vals):
                    if val == current_startdate_val:
                        self.mod_vals[j] = startdate_val - self.starttime_offset
                        self.mod_vals.sort()
                        break

                extended_exception = self.extended_exceptions[i]
                self._update_exceptions(cal_item, message, startdate_val, enddate_val, basedate_val, exception, extended_exception, copytags, create=False)

        self._save()

        # update calitem
        self._update_calitem(item)

    def __unicode__(self):
        return u'Recurrence(start=%s - end=%s)' % (self.start, self.end)

    def __repr__(self):
        return _repr(self)


class Occurrence(object):
    def __init__(self, item, start, end): # XXX make sure all GMT?
        self.item = item
        self.start = start
        self.end = end

    def __getattr__(self, x):
        return getattr(self.item, x)

    def __unicode__(self):
        return u'Occurrence(%s)' % self.subject

    def __repr__(self):
        return _repr(self)
