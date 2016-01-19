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

"""Get the emails, parse them and store what needs to be sent."""

import imaplib
import logging
import sys
import pymongo

import utils
import utils.db
import utils.emails

# pylint: disable=invalid-name
log = logging.getLogger("kernelci-reports")


def ensure_indexes(options):
    """Make sure database indexes are setup.

    :param options: The database connection parameters.
    :type options: dict
    """
    log.debug("Creating/Updating database indexes...")
    try:
        connection = utils.db.get_connection(options)
        database = connection[utils.db.DB_NAME]

        if database:
            database[utils.db.DB_CHECK_QUEUE].create_index(
                [
                    ("message_id", pymongo.ASCENDING),
                    ("subject", pymongo.ASCENDING)
                ],
                background=True
            )
        else:
            log.error("No database connection found, cannot continue")
            sys.exit(1)
    finally:
        connection.close()


def save(options, data):
    """Save the parsed email into the database.

    :param options: The options read from the command line and the config.
    :type options: dict
    :param data: List of dictionaries to save.
    :type data: list
    """
    if data:
        try:
            log.debug("Saving parsed emails...")
            connection = utils.db.get_connection(options)
            database = connection[utils.db.DB_NAME]

            if database:
                for message in data:
                    prev_doc = database[utils.db.DB_CHECK_QUEUE].find_one(
                        {
                            "message_id": message["message_id"],
                            "subject": message["subject"]
                        },
                        projection={
                            "_id": False, "message_id": True, "subject": True}
                    )

                    if not prev_doc:
                        log.debug("No similar document found, saving...")
                        database[utils.db.DB_CHECK_QUEUE].insert_many(
                            data, ordered=False)
                    else:
                        log.warn(
                            "Similar message found with Message-Id '%s'",
                            message["message_id"])
            else:
                log.error(
                    "No database connection found, parsed data will be lost")
                sys.exit(1)
        finally:
            connection.close()


def check(options):
    """Check for new emails via IMAP protocol.

    Will only check the default 'INBOX' mail box.

    :param options: The configuration options.
    :type options: dict
    :return list A list with the parsed emails data.
    """
    log.debug("Checking emails...")

    try:
        log.debug("Connecting to mail server...")

        parsed_emails = []
        server = imaplib.IMAP4_SSL(
            host=options[utils.MAIL_SERVER],
            port=options[utils.MAIL_SERVER_PORT])
        server.login(
            options[utils.MAIL_USERNAME], options[utils.MAIL_PASSWORD])

        # Only check in the INBOX.
        server.select()

        log.debug("Retrieving new messages...")
        status, messages = server.search(None, "(UNSEEN)")
        if status == "OK":
            for msg_id in messages[0].split():
                status, message = server.fetch(msg_id, "(RFC822)")

                if status == "OK":
                    email_data = utils.emails.parse(message)
                    if email_data:
                        parsed_emails.append(email_data)
                else:
                    log.error("Error fetching message with ID '%s'", msg_id)

        server.close()
        server.logout()

        return parsed_emails
    except imaplib.IMAP4.error:
        log.error("Error connecting to IMAP server, aborting.")
        sys.exit(1)