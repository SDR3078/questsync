"""Convert Habitica tasks <-> iCalendar VTODO. See docs/design.md section 4-5."""
import re
from datetime import datetime, timezone

from dateutil import parser as dateparser

# Habitica difficulty (priority field) -> VTODO PRIORITY (1 = high .. 9 = low).
_DIFF_TO_PRIO = {0.1: 9, 1: 6, 1.5: 5, 2: 1}
# Reverse: nearest Habitica difficulty for a given VTODO PRIORITY.
_PRIO_BUCKETS = [(2, 2.0), (4, 1.5), (7, 1.0), (9, 0.1)]


def _esc(text):
    return (str(text).replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\r", "").replace("\n", "\\n"))


def _ical_utc(iso):
    return dateparser.isoparse(iso).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _ical_date(iso):
    return dateparser.isoparse(iso).strftime("%Y%m%d")


def _now_utc():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _today_ical():
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def safe_alias(stem):
    """Habitica aliases allow only [A-Za-z0-9_-]; sanitize a client href-stem."""
    alias = re.sub(r"[^A-Za-z0-9_-]", "-", stem)[:60]
    return alias or None


def _vtodo_lines(task, extra):
    """Common VTODO body shared by todos and dailies; `extra` is a list of lines."""
    uid = task.get("alias") or task["_id"]
    completed = bool(task.get("completed"))
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//questsync//v1//EN",
             "BEGIN:VTODO", "UID:" + uid, "DTSTAMP:" + _now_utc(),
             "SUMMARY:" + _esc(task.get("text", ""))]

    desc = task.get("notes", "") or ""
    checklist = task.get("checklist") or []
    if checklist:
        rendered = "\n".join(("[x] " if c.get("completed") else "[ ] ")
                             + c.get("text", "") for c in checklist)
        desc = (desc + "\n\n" + rendered) if desc else rendered
    if desc:
        lines.append("DESCRIPTION:" + _esc(desc))

    lines += extra

    if completed:
        lines += ["STATUS:COMPLETED", "PERCENT-COMPLETE:100",
                  "COMPLETED:" + (_ical_utc(task["dateCompleted"])
                                  if task.get("dateCompleted") else _now_utc())]
    else:
        lines.append("STATUS:NEEDS-ACTION")

    prio = task.get("priority", 1)
    lines.append("PRIORITY:%d" % _DIFF_TO_PRIO.get(prio, 0))
    lines.append("X-HABITICA-PRIORITY:%s" % prio)   # lossless round-trip
    if task.get("createdAt"):
        lines.append("CREATED:" + _ical_utc(task["createdAt"]))
    if task.get("updatedAt"):
        lines.append("LAST-MODIFIED:" + _ical_utc(task["updatedAt"]))
    lines += ["END:VTODO", "END:VCALENDAR"]
    return "\r\n".join(lines) + "\r\n"


def todo_to_ics(task):
    """Habitica todo dict -> a full VCALENDAR/VTODO string."""
    extra = ["X-HABITICA-TYPE:todo"]
    if task.get("date"):
        extra.append("DUE;VALUE=DATE:" + _ical_date(task["date"]))
    return _vtodo_lines(task, extra)


def daily_should_render(task):
    """Materialized model: show a daily only if it's completed or currently due."""
    return bool(task.get("completed")) or bool(task.get("isDue"))


def daily_to_ics(task):
    """Habitica daily -> VTODO for *today's* occurrence (no RRULE)."""
    extra = ["X-HABITICA-TYPE:daily"]
    due = task.get("nextDue") or []
    extra.append("DUE;VALUE=DATE:" + (_ical_date(due[0]) if due else _today_ical()))
    if task.get("streak") is not None:
        extra.append("X-HABITICA-STREAK:%s" % task["streak"])
    return _vtodo_lines(task, extra)


def _prop(vtodo, name):
    child = getattr(vtodo, name, None)
    return child.value if child is not None else None


def _prio_to_diff(vtodo_priority):
    if not vtodo_priority:
        return 1
    for threshold, diff in _PRIO_BUCKETS:
        if vtodo_priority <= threshold:
            return diff
    return 0.1


def ics_to_habitica(vtodo):
    """vobject VTODO component -> (habitica_fields, completed_bool)."""
    fields = {}
    summary = _prop(vtodo, "summary")
    if summary is not None:
        fields["text"] = summary
    notes = _prop(vtodo, "description")
    if notes is not None:
        fields["notes"] = notes

    due = _prop(vtodo, "due")
    if due is not None and hasattr(due, "isoformat"):
        fields["date"] = due.isoformat()

    # Prefer the lossless X-HABITICA-PRIORITY; else map back from PRIORITY.
    xprio = _prop(vtodo, "x_habitica_priority")
    if xprio is not None:
        try:
            fields["priority"] = float(xprio)
        except (TypeError, ValueError):
            pass
    else:
        prio = _prop(vtodo, "priority")
        if prio is not None:
            fields["priority"] = _prio_to_diff(int(prio))

    status = (_prop(vtodo, "status") or "").upper()
    return fields, status == "COMPLETED"
