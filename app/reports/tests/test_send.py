# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Email utilities test module."""

import logging
import unittest

import reports.send


class TestEmails(unittest.TestCase):

    def setUp(self):
        logging.disable(logging.CRITICAL)

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def test_send_git_describe_valid(self):
        result = {
            "git_describe": "v4.4.30-70-g3a40a54aa275"
        }
        report = {
            "version": "4.4.30",
            "patches": ["68", "69", "70", "71"]
        }

        self.assertTrue(reports.send.is_valid_result(result, report))

    def test_send_git_describe_not_valid(self):
        result = {
            "git_describe": "v4.3.29-72-g3a40a54aa1234"
        }
        report = {
            "version": "4.3.29",
            "patches": ["70", "71"]
        }

        self.assertFalse(reports.send.is_valid_result(result, report))

    def test_send_git_describe_not_valid_2(self):
        result = {
            "git_describe": "v4.3.29-72-g3a40a54aa1234"
        }
        report = {
            "version": "4.3.29",
            "patches": ["69"]
        }

        self.assertFalse(reports.send.is_valid_result(result, report))
