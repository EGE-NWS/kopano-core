#!/usr/bin/env python
import collections
from datetime import datetime, timedelta
import sys
import kopano

from MAPI.Tags import PR_DISPLAY_TYPE_EX, PR_EMS_AB_ROOM_CAPACITY

RECURRENCE_AVAILABILITY_RANGE = 180 # days
DT_EQUIPMENT = 8

# XXX ZCP-9901 still relevant without outlook?

def capacity(user): # XXX pyko?
    """ equipment resources can be overbooked up to N times """

    disptype = user.get_prop(PR_DISPLAY_TYPE_EX)
    capacity = user.get_prop(PR_EMS_AB_ROOM_CAPACITY)

    if disptype == DT_EQUIPMENT and capacity and capacity > 0:
        return capacity
    else:
        return 1

class Marker(object): # XXX kill?
    def __init__(self, occurrence):
        self.occurrence = occurrence

def conflict_occurrences(user, item):
    """ item occurrences which overlap (too much) with calendar """

    start = item.start
    end = start + timedelta(RECURRENCE_AVAILABILITY_RANGE)

    item_occs = list(item.occurrences(start, end))
    cal_occs = list(user.calendar.occurrences(start, end))

    # create start/end markers for each occurrence
    dt_markers = collections.defaultdict(list)
    for o in item_occs + cal_occs:
        marker = Marker(o)
        if o.start <= o.end:
            dt_markers[o.start].append(marker)
            dt_markers[o.end].append(marker)

    # loop over sorted markers, maintaining running set
    max_overlap = capacity(user)
    conflict_markers = set()
    running = set()
    for day in sorted(dt_markers):
        for marker in dt_markers[day]:
            if marker in running:
                running.remove(marker)
            else:
                running.add(marker)

        # if too much overlap, check if item is involved
        if len(running) > max_overlap:
            for marker in running:
                if marker.occurrence.item is item:
                    conflict_markers.add(marker)

    return [m.occurrence for m in conflict_markers]

def conflict_message(occurrences):
    lines  = ['The requested time slots are unavailable on the following dates:', '']
    for occ in occurrences:
        lines.append('%s - %s' % (occ.start, occ.end))
    return '\n'.join(lines)

def main():
    username, config, entryid = [arg.decode('utf8') for arg in sys.argv[1:]]

    server = kopano.Server()
    user = server.user(username)
    autoaccept = user.autoaccept
    item = user.item(entryid)
    mr = item.meetingrequest

    if mr.is_request:
        decline_message = None

        if not autoaccept.recurring and item.recurring:
            decline_message = "Recurring meetings are not allowed"

        elif not autoaccept.conflicts:
            conflicts = conflict_occurrences(user, item)
            if conflicts:
                decline_message = conflict_message(conflicts)

        if decline_message:
            mr.decline(message=decline_message)
        else:
            mr.accept(add_bcc=True)

    elif mr.is_cancellation:
        mr.process_cancellation(delete=True)

    now = datetime.now()
    user.freebusy.publish(now - timedelta(7), now + timedelta(180))

if __name__ == '__main__':
    main()
