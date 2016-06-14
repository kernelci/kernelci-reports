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

import datetime
import logging
import unittest

import utils.emails


class TestEmails(unittest.TestCase):

    def setUp(self):
        logging.disable(logging.CRITICAL)

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def test_fix_kernel_version_correct(self):
        returned_value = utils.emails.fix_kernel_version("4.1.14")
        self.assertEqual("4.1.13", returned_value)

    def test_fix_kernel_version_with_zero(self):
        returned_value = utils.emails.fix_kernel_version("4.0")
        self.assertEqual("4.0", returned_value)

    def test_fix_kernel_version_wrong_non_numeric(self):
        returned_value = utils.emails.fix_kernel_version("foo")
        self.assertEqual("foo", returned_value)

    def test_fix_kernel_version_wrong_non_numeric_and_numeric(self):
        returned_value = utils.emails.fix_kernel_version("4.1.3-foo")
        self.assertEqual("4.1.3-foo", returned_value)

    def test_fix_kernel_version_with_minor_one_len_three(self):
        returned_value = utils.emails.fix_kernel_version("4.1.1")
        self.assertEqual("4.1", returned_value)

    def test_fix_kernel_version_with_minor_one_len_two(self):
        returned_value = utils.emails.fix_kernel_version("4.1")
        self.assertEqual("4.0", returned_value)

    def test_extract_kernel_version_correct(self):
        expected = {
            "tree": "stable-queue",
            "patches": "45",
            "version": "4.1.14"
        }

        subject = "[PATCH 4.1 00/45] 4.1.15-stable review"
        returned_value = utils.emails.extract_kernel_from_subject(subject)

        self.assertDictEqual(expected, returned_value)

    def test_extract_kernel_version_reply(self):
        subject = "Re: [PATCH 4.1 00/45] 4.1.15-stable review"
        returned_value = utils.emails.extract_kernel_from_subject(subject)

        self.assertIsNone(returned_value)

    def test_extract_kernel_version_random(self):
        subject = "foo review 4.1.5 bar kernel"
        returned_value = utils.emails.extract_kernel_from_subject(subject)

        self.assertIsNone(returned_value)

    def test_extract_deadline_format_0(self):
        deadline = "2016-06-13T11:30:00.000001+00:00"
        returned_val = utils.emails.parse_deadline_string(deadline)

        self.assertIsInstance(returned_val, datetime.datetime)

    def test_extract_deadline_format_1(self):
        deadline = "2016-06-13T11:30:00+00:00"
        returned_val = utils.emails.parse_deadline_string(deadline)

        self.assertIsInstance(returned_val, datetime.datetime)

    def test_extract_deadline_format_2(self):
        deadline = "2016-06-13T11:30-02:00"
        returned_val = utils.emails.parse_deadline_string(deadline)

        self.assertIsInstance(returned_val, datetime.datetime)

    def test_extract_deadline_format_not_valid(self):
        deadline = "2016-06-13T11:30:00"
        returned_val = utils.emails.parse_deadline_string(deadline)

        self.assertIsNone(returned_val)
