"""Unit tests for the Habitica <-> VTODO converter (no network, no container)."""
import vobject

from questsync import convert


def _parse(ics):
    return vobject.readOne(ics).vtodo


def test_todo_roundtrips_and_escapes():
    task = {"_id": "abc", "text": "Milk, eggs; bread", "notes": "l1\nl2",
            "completed": False, "priority": 2, "date": "2026-07-05T00:00:00.000Z"}
    ics = convert.todo_to_ics(task)
    assert "SUMMARY:Milk\\, eggs\\; bread" in ics
    assert "DESCRIPTION:l1\\nl2" in ics
    assert "DUE;VALUE=DATE:20260705" in ics
    assert "PRIORITY:1" in ics and "X-HABITICA-PRIORITY:2" in ics
    assert "STATUS:NEEDS-ACTION" in ics

    fields, completed = convert.ics_to_habitica(_parse(ics))
    assert completed is False
    assert fields["text"] == "Milk, eggs; bread"
    assert fields["notes"] == "l1\nl2"
    assert fields["priority"] == 2.0


def test_completed_todo():
    task = {"_id": "x", "text": "done", "completed": True, "priority": 1,
            "dateCompleted": "2026-06-30T18:00:00.000Z"}
    ics = convert.todo_to_ics(task)
    assert "STATUS:COMPLETED" in ics
    assert "PERCENT-COMPLETE:100" in ics
    _, completed = convert.ics_to_habitica(_parse(ics))
    assert completed is True


def test_priority_mapping_both_ways():
    assert convert._DIFF_TO_PRIO[2] == 1
    assert convert._DIFF_TO_PRIO[0.1] == 9
    assert convert._prio_to_diff(1) == 2.0
    assert convert._prio_to_diff(9) == 0.1
    assert convert._prio_to_diff(0) == 1     # 0 = "undefined" -> Habitica easy


def test_safe_alias():
    assert convert.safe_alias("uuid@tasks.org") == "uuid-tasks-org"
    assert convert.safe_alias("clean-1_2") == "clean-1_2"
    assert convert.safe_alias("!!!") == "---"


def test_daily_materialization():
    due = {"_id": "d", "type": "daily", "text": "Meditate", "isDue": True,
           "completed": False, "nextDue": ["2026-07-01T00:00:00.000Z"],
           "priority": 1, "streak": 3}
    not_due = {"_id": "e", "type": "daily", "text": "x", "isDue": False,
               "completed": False}
    done = {"_id": "f", "type": "daily", "text": "y", "isDue": False,
            "completed": True}

    assert convert.daily_should_render(due) is True
    assert convert.daily_should_render(not_due) is False   # hidden until due
    assert convert.daily_should_render(done) is True

    ics = convert.daily_to_ics(due)
    assert "X-HABITICA-TYPE:daily" in ics
    assert "DUE;VALUE=DATE:20260701" in ics
    assert "X-HABITICA-STREAK:3" in ics
    assert "STATUS:NEEDS-ACTION" in ics
