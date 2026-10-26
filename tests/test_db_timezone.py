import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import db

class DisplayTimezoneTests(unittest.TestCase):
    def test_utc_datetime_is_converted_to_schedule_timezone(self):
        local = db._display_local(datetime(2026, 10, 11, 1), "Asia/Shanghai")
        self.assertEqual(local.isoformat(), "2026-10-11T09:00:00+08:00")

if __name__ == "__main__":
    unittest.main()
