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

"""Email parsing logic."""

import datetime
import email
import email.utils
import io
import logging
import os
import re

# pylint: disable=invalid-name
log = logging.getLogger("kernelci-reports")

# Need to match something like:
# [PATCH 4.1 00/45] 4.1.15-stable review
#
# Matches the patches count, the kernel version and the tree name into separate
# named matching groups.
SUBJECT_PATCH_RGX = re.compile(
    r"\[PATCH\s+(?:\d+\.{1}\d+(?:\.{1}\d+)?)\s+(?P<patches>\d{1,}/\d{1,})\]"
    r"\s+(?P<version>\d+\.{1}\d+(?:\.{1}\d+)?)-(?P<tree>\w*)"
)
# Is the message a reply?
SUBJECT_RE_RGX = re.compile(r"^Re:?")

DEADLINE_FORMATS = [
    r"%Y%m%dT%H%M%z",
    r"%Y%m%dT%H%M%S%z",
    r"%Y%m%dT%H%M%S.%f%z"
]


def fix_kernel_version(version):
    """Make sure the kernel version is correct.

    When we get an email, usually we get the kernel version for an unreleased
    kernel. We need to subtract 1 to the last version format number.

    :param version: The kernel version as obtained from the email.
    :type version: str
    :return str The updated kernel version.
    """
    version = version.split(".")

    # Do the "conversion" only if we have some valid values: meaning that we
    # have something when we split the provided version string.
    v_len = len(version)
    if v_len >= 2:
        try:
            # XXX: What should happen if we have a 4.0 kernel version?
            if version[-1] != "0":
                minor = int(version[-1]) - 1
                # If we receive the string 4.1.1, it will become just 4.1.
                if all([minor == 0, v_len > 2]):
                    version = version[:-1]
                else:
                    version[-1] = str(minor)
            else:
                log.warning(
                    "Kernel version has a 0, don't know how to proceed")
        except ValueError:
            log.error("Got non parsable kernel version: %s", version)
        finally:
            version = ".".join(version)
    else:
        version = version[0]

    return version


def extract_kernel_from_subject(subject):
    """Extract the kernel version and patches info from the subject.

    Parse the subject string looking for a pre-defined structure. Then extract
    the necessary values of:

    . patches: The total number of patches that are part of the test.
    . version: The kernel version that will be released.
    . tree: The name of the kernel tree.

    :param subject: The email subject to parse.
    :type subject: str
    :return dict A dictionary with keys 'tree', 'patches' and 'version'.
    """
    extracted = None
    if not SUBJECT_RE_RGX.match(subject):
        matched = SUBJECT_PATCH_RGX.match(subject)
        if matched:
            patches = matched.group("patches")
            patches = patches.split("/")[1]

            version = fix_kernel_version(matched.group("version"))

            tree = matched.group("tree")
            # TODO: extract this and read translation from a file maybe?
            if tree == "stable":
                tree = "stable-queue"

            extracted = {
                "tree": tree,
                "version": version,
                "patches": patches
            }

    return extracted


def parse_deadline_string(deadline):
    """Parse the X-KernelTest-Deadline mail header and convert it to datetime.

    :param deadline: The custom header value.
    :type deadline: str
    :return A datetime.datetime object with UTC timezone.
    :rtype datetime.datetime
    """
    # Just replace two hypens because we need the one on the timezone.
    deadline = deadline.replace("-", "", 2).replace(":", "")

    parsed_deadline = None
    for fmt in DEADLINE_FORMATS:
        try:
            parsed_deadline = datetime.datetime.strptime(deadline, fmt)
        except ValueError:
            log.error("Error parsing deadline '%s' with '%s'", deadline, fmt)
        else:
            parsed_deadline = parsed_deadline.astimezone(datetime.timezone.utc)
            break

    return parsed_deadline


def extract_mail_values(mail):
    """Extract the necessary values from the mail.

    :param mail: The email message.
    :return dict The email data as a dictionary.
    """
    data = None

    if not all([mail["In-Reply-To"], mail["References"]]):
        subject = mail["Subject"]

        log.debug("Received email with subject: %s", subject)
        data = extract_kernel_from_subject(subject)

        # TODO: check custom headers for tree/version/patches (if defined).
        if data:
            log.info("New valid email found: %s", subject)

            to = mail["To"]
            cc = mail["Cc"]

            if to:
                to = [x.strip() for x in to.split(",")]
            if cc:
                cc = [x.strip() for x in cc.split(",")]

            data["subject"] = subject
            data["message_id"] = mail["Message-Id"]
            data["to"] = to
            data["cc"] = cc
            data["from"] = email.utils.parseaddr(mail["From"])

            email_date = \
                email.utils.parsedate_to_datetime(mail["Date"])
            email_date = email_date.astimezone(datetime.timezone.utc)

            log.debug("Email date: %s", email_date)

            data["created_on"] = email_date

            # When is the last moment for sending the report?
            deadline = mail["X-KernelTest-Deadline"]
            if deadline:
                deadline = parse_deadline_string(deadline)

            if not deadline:
                log.warning("No deadline available, default to +2 days")
                deadline = (email_date + datetime.timedelta(days=2))

            data["deadline"] = deadline

            log.debug("Extracted data: %s", data)

    return data


def parse_from_file(path):
    """Parse a single message from a file.

    :param path: The full path the the email file.
    :type path: str
    :return dict A dictionary with all the necessary data.
    """
    data = None

    # Although we don't write anything into the file, we need to make
    # sure we can remove it.
    if os.access(path, os.R_OK | os.W_OK):
        with io.open(path, mode="rb") as read_file:
            mail = email.message_from_binary_file(read_file)

        data = extract_mail_values(mail)

        try:
            os.unlink(path)
        except PermissionError:
            log.error("Error removing file at '%s'", path)
    else:
        log.warning("Cannot access in 'rw' mode the file at '%s'", path)

    return data


def parse(message):
    """Parse a single email message.

    :param message: The email message from the IMAP server.
    :type message: str
    :return dict A dictionary with all the necessary data.
    """
    return extract_mail_values(email.message_from_bytes(message[0][1]))
