"""Convert Habitica tasks <-> iCalendar VTODO. See docs/design.md sections 4-5.

Rendering is a PURE FUNCTION of Habitica state — no wall-clock. DTSTAMP and
LAST-MODIFIED derive from the task's updatedAt, COMPLETED from dateCompleted.
This keeps Radicale's ETag -> ctag -> sync-token stable across polls (so change
detection and If-Match work) and makes replicas byte-identical.
"""
import re
from datetime import timezone

from dateutil import parser as dateparser

# Habitica difficulty (priority field) -> VTODO PRIORITY (1 = high .. 9 = low).
_DIFF_TO_PRIO = {0.1: 9, 1: 6, 1.5: 5, 2: 1}
_PRIO_BUCKETS = [(2, 2.0), (4, 1.5), (7, 1.0), (9, 0.1)]

HTTP_DT_FMT = "%a, %d %b %Y %H:%M:%S GMT"
EPOCH_ISO = "1970-01-01T00:00:00.000Z"


def _esc(text):
    return (str(text).replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\r", "").replace("\n", "\\n"))


def _ical_utc(iso):
    return dateparser.isoparse(iso).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _ical_date(iso):
    return dateparser.isoparse(iso).strftime("%Y%m%d")


def http_date(iso):
    return dateparser.isoparse(iso).astimezone(timezone.utc).strftime(HTTP_DT_FMT)


def task_lastmod(task):
    """Deterministic HTTP Last-Modified for a task (from its updatedAt)."""
    return http_date(task.get("updatedAt") or EPOCH_ISO)


def safe_alias(stem):
    """Habitica aliases allow only [A-Za-z0-9_-]; sanitize a client href-stem."""
    alias = re.sub(r"[^A-Za-z0-9_-]", "-", stem)[:60]
    return alias or None


# Client-created tasks are aliased with this prefix so the alias is never a bare
# UUID — Habitica rejects UUID-shaped aliases (they collide with task ids at
# /tasks/:idOrAlias). The prefix is stripped on read so the client keeps its href.
ALIAS_PREFIX = "qs-"


def client_alias(stem):
    """Namespaced, Habitica-safe alias for a client-created task."""
    base = re.sub(r"[^A-Za-z0-9_-]", "-", stem)[:57]
    return (ALIAS_PREFIX + base) if base else None


def href_stem(task):
    """Resource stem to render a task at: the client's original stem for a
    QuestSync-created task (strip the prefix), else the task's alias or _id."""
    alias = task.get("alias")
    if alias and alias.startswith(ALIAS_PREFIX):
        return alias[len(ALIAS_PREFIX):]
    return alias or task["_id"]


def _vtodo_lines(task, extra):
    uid = href_stem(task)                          # matches the resource href (prefix stripped)
    completed = bool(task.get("completed"))
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//questsync//v1//EN",
             "BEGIN:VTODO", "UID:" + uid,
             "DTSTAMP:" + _ical_utc(task.get("updatedAt") or EPOCH_ISO),
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
        lines += ["STATUS:COMPLETED", "PERCENT-COMPLETE:100"]
        if task.get("dateCompleted"):                # deterministic; omit if absent
            lines.append("COMPLETED:" + _ical_utc(task["dateCompleted"]))
    else:
        lines.append("STATUS:NEEDS-ACTION")

    prio = task.get("priority", 1)
    lines.append("PRIORITY:%d" % _DIFF_TO_PRIO.get(prio, 0))
    lines.append("X-HABITICA-PRIORITY:%s" % prio)    # lossless round-trip
    if task.get("createdAt"):
        lines.append("CREATED:" + _ical_utc(task["createdAt"]))
    if task.get("updatedAt"):
        lines.append("LAST-MODIFIED:" + _ical_utc(task["updatedAt"]))
    lines += ["END:VTODO", "END:VCALENDAR"]
    return "\r\n".join(lines) + "\r\n"


def todo_to_ics(task):
    extra = ["X-HABITICA-TYPE:todo"]
    if task.get("date"):
        extra.append("DUE;VALUE=DATE:" + _ical_date(task["date"]))
    return _vtodo_lines(task, extra)


def daily_should_render(task):
    """Materialized model: show a daily only if it's completed or currently due."""
    return bool(task.get("completed")) or bool(task.get("isDue"))


def daily_to_ics(task):
    extra = ["X-HABITICA-TYPE:daily"]
    due = task.get("nextDue") or []
    if due:                                          # deterministic; from Habitica
        extra.append("DUE;VALUE=DATE:" + _ical_date(due[0]))
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
