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

import email
import logging
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

# TODO: define custom headers.
CUSTOM_HEADERS = []


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
    if len(version) >= 2:
        try:
            # XXX: What should happen if we have a 4.0 kernel version?
            if version[-1] != "0":
                version[-1] = str(int(version[-1]) - 1)
            else:
                log.warn("Kernel version has a 0, don't know how to proceed")
        except ValueError:
            log.error("Got non parsable kernel version: %s", version)
        finally:
            version = ".".join(version)
    else:
        version = version[0]

    return version


def extract_kernel_version(subject):
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

            extracted = {
                "tree": matched.group("tree"),
                "version": version,
                "patches": patches
            }

    return extracted


def parse(message):
    """Parse a single email message and trigger the (possible) report.

    :param message: The email message from the server.
    :type message: str
    :return dict A dictionary with all the necessary data.
    """
    # TODO: check for custom headers.
    # TODO: check presence of In-Reply-To & References headers?
    mail = email.message_from_bytes(message[0][1])
    subject = mail["Subject"]

    log.debug("Received email with subject: %s", subject)
    email_data = extract_kernel_version(subject)
    if email_data:
        log.info("New valid email found: %s", subject)

        to = mail["To"]
        cc = mail["Cc"]

        if to:
            to = [x.strip() for x in to.split(",")]
        if cc:
            cc = [x.strip() for x in cc.split(",")]

        email_data["subject"] = subject
        email_data["message_id"] = mail["Message-Id"]
        email_data["to"] = to
        email_data["cc"] = cc
        email_data["from"] = email.utils.parseaddr(mail["From"])

        log.debug("Extracted data: %s", email_data)

    return email_data
