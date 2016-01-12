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

"""Check emails and trigger build/boot reports."""

import argparse
import email
import imaplib
import logging
import re
import sys
import time

# XXX: use Google APIs?

# Where to read the configuration from by default.
DEFAULT_CONFIG_FILE = "/etc/linaro/kernelci-reports.cfg"

# Default IMAP server to connect to.
DEFAULT_IMAP_SERVER = "imap.gmail.com"
# Default IMAP server port.
DEFAULT_IMAP_PORT = 993

# Check emails every 15 minutes by default.
DEFAULT_SLEEP = 900

# TODO: define custom headers.
CUSTOM_HEADERS = []

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

# pylint: disable=invalid-name
log = logging.getLogger("kernelci-reports")


def extract_kernel_version(subject):
    """Extract the kernel version and patches info from the subject.

    Parse the subject string looking for a pre-defined structure. Then extract
    the necessary values of:

    . patches: The total number of patches that are part of the test.
    . version: The kernel version that will be released, as a list of numbers.
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

            version = matched.group("version")
            version = version.split(".")

            extracted = {
                "tree": matched.group("tree"),
                "version": version,
                "patches": patches
            }

    return extracted


def parse_email(message):
    """Parse a single email message and trigger the (possible) report.

    :param message: The email message from the server.
    :type message: str
    """
    mail = email.message_from_string(message[0][1])
    log.debug("Received email with subject: %s", mail["Subject"])
    # TODO: check for custom headers.
    # TODO: check presence of In-Reply-To & References headers?
    email_data = extract_kernel_version(mail["Subject"])
    if email_data:
        email_data["to"] = mail["To"]
        email_data["cc"] = mail["Cc"]
        email_data["from"] = email.utils.parseaddr(mail["From"])

        log.debug("Extracted data: %s", email_data)


def check_emails(options):
    """Check for new emails via IMAP protocol.

    Will only check the default 'INBOX' mail box.
    """
    log.debug("Checking emails...")

    try:
        log.debug("Connecting to mail server...")
        server = imaplib.IMAP4_SSL(
            host=options["mail_server"], port=options["mail_server_port"])
        server.login(options["user_name"], options["user_password"])

        # Only check in the INBOX.
        server.select()

        log.debug("Retrieving new messages...")
        status, messages = server.search(None, "(UNSEEN)")
        if status == "OK":
            for msg_id in messages[0].split():
                status, message = server.fetch(msg_id, "(RFC822)")

                if status == "OK":
                    parse_email(message)
                else:
                    log.error("Error fetching message with ID '%s'", msg_id)

        server.close()
        server.logout()
    except imaplib.IMAP4.error:
        log.error("Error connecting to IMAP server, aborting.")
        sys.exit(1)


def setup_logging(debug=False):
    """Setup and configure logging infrastructure.

    :param debug: If debug logging should be enabled. Default False.
    :type debug: bool
    """
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter("%(levelname)s - %(message)s"))

    if debug:
        log.setLevel(logging.DEBUG)
        console_handler.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.INFO)
        console_handler.setLevel(logging.INFO)

    log.addHandler(console_handler)


def setup_args():
    """Setup command line arguments parsing.

    :return dict The parsed command line arguments as a dictionary.
    """
    parser = argparse.ArgumentParser(
        description="Wait for emails and send build/boot reports.")

    parser.add_argument(
        "--mail-server",
        dest="mail_server",
        help="The IMAP server to connect to", default=DEFAULT_IMAP_SERVER
    )
    parser.add_argument(
        "--mail-server-port",
        dest="mail_server_port",
        help="The IMAP server port", default=DEFAULT_IMAP_PORT
    )
    parser.add_argument(
        "--user-name",
        dest="user_name", help="The user name to use for the server connection"
    )
    parser.add_argument(
        "--user-password",
        dest="user_password",
        help="Password to authenticate to the mail server"
    )
    parser.add_argument(
        "--check-every",
        type=int,
        default=DEFAULT_SLEEP,
        dest="check_every",
        help="Number of seconds to wait for each check (default: 900)")
    parser.add_argument(
        "--debug",
        dest="debug", action="store_true", help="Enable debug output")

    return vars(parser.parse_args())


def parse_config_file():
    """Parse the configuration file.

    :return dict The options read as a dictionary.
    """
    # TODO
    pass


if __name__ == "__main__":
    args = setup_args()
    setup_logging(debug=args["debug"])

    try:
        while True:
            check_emails(args)
            log.debug("Sleeping for %d seconds...", args["check_every"])
            time.sleep(args["check_every"])
    except KeyboardInterrupt:
        log.info("Interrupted by the user, exiting.")
