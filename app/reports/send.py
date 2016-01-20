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

"""Check the queue in the database and the API, send reports."""

import logging
import re

import utils
import utils.backend
import utils.db

# pylint: disable=invalid-name
log = logging.getLogger("kernelci-reports")

# Seconds to wait before the backend should send the email report.
SEND_DELAY = 5
# TODO: need a better check for different git_describe format.
GIT_DESCRIBE_MATCHER = r"^v{0:s}-{1:s}-g(.*)"


def send_report(result, report, options):
    """Trigger the backend to send a report.

    :param result: The result from the backend API.
    :type result: dict
    :param report: The report as parsed from the email.
    :type report: dict
    :param options: The app configuration parameters.
    :type options: dict
    """
    url = options[utils.BACKEND_URL] + "/send"
    # TODO: need a way to customize some of these values.
    data = {
        "delay": SEND_DELAY,
        "build_report": 1,
        "job": result["job"],
        "kernel": result["kernel"],
        "format": ["txt"],
        # TODO: complete these, need to merge the from address.
        "send_to": report["to"],
        "send_cc": report["cc"],
        "in_reply_to": report["message_id"],
        "subject": report["subject"]
    }
    return utils.backend.post(url, data)


def is_valid_result(result, report):
    """Make sure that a result from the API is the correct one.

    To be valid, the git_describe value must match a string made with the
    data retrieved from the email.

    In the email report we have:
    . the kernel version
    . the number of patches

    The string that will be matched is, expressed as a regex::

    ^v{version}-{patches}-.*

    The original git_describe value would be something like:

    v4.1.14-44-gb580d5c9a21f

    :param result: The result from the API.
    :type result: dict
    :param report: The original report as parsed from the email.
    :type report: dict
    """
    is_valid = True

    pattern = GIT_DESCRIBE_MATCHER.format(
        report["version"], report["patches"])

    # TODO: need to use the git_describe_v field here as well.
    if not re.match(pattern, result["git_describe"]):
        log.debug("Git describe version does not match '%s'", pattern)
        is_valid = False

    return is_valid


# pylint: disable=too-many-branches
def handle_result(response, report, database, options):
    """Handle the results as obtained from the backend.

    Check the status code of the response and apply the correct logic.
    It will update the 'retries' field only if the status is 200 and we don't
    have any results.

    :param response: The response from the backend.
    :param report: The original report as parsed from the email.
    :param database: The database connection.
    :param options: The app configuration parameters.
    """
    def _inc_retries():
        """Increment the retries field of the report."""
        database[utils.db.DB_CHECK_QUEUE].find_one_and_update(
            {"_id": report["_id"]}, {"$inc": {"retries": 1}})

    def _delete_report():
        """Delete the report from the database."""
        database[utils.db.DB_CHECK_QUEUE].delete_one({"_id": report["_id"]})

    if response.status_code == 200:
        response = response.json()

        if response["count"] > 0:
            response = response["result"]
            valid_result = None

            for result in response:
                if is_valid_result(result, report):
                    valid_result = result
                    break

            if valid_result:
                response = send_report(valid_result, report, options)
            else:
                # We couldn't find a valid result from the API.
                # Let's check again later.
                _inc_retries()
                log.info(
                    "No valid results found from the backend for %s-%s",
                    report["tree"], report["version"])
        else:
            _inc_retries()
    elif response.status_code == 503:
        log.warn("Backend is in maintenance, will retry later")
    elif response.status_code == 404:
        log.error(
            "Requested resource (%s, %s) not found, report will be discarded",
            report["tree"], report["version"])
        _delete_report()
    elif response.status_code == 400:
        log.error("Something wrong in the request, report will be discarded")
        _delete_report()
    elif response.status_code == 500:
        log.warn("Backend error, will retry later")


def check_and_send(options):
    """

    :param options: The app configuration parameters.
    :type options: dict
    """
    connection = utils.db.get_connection(options)

    try:
        database = connection[utils.db.DB_NAME]

        queued_reports = database[utils.db.DB_CHECK_QUEUE].find()
        utils.backend.req.headers.update(
            {"Authorization": options.get(utils.BACKEND_TOKEN, None)})

        url = options[utils.BACKEND_URL] + "/job"

        for report in queued_reports:
            if report.get("retires", 0) >= options[utils.MAX_RETRIES]:
                log.warn(
                    "Too many retries for '%s - %s', report will be discarded",
                    report["tree"], report["version"])
                database[utils.db.DB_CHECK_QUEUE].delete_one(
                    {"_id": report["_id"]})
            else:
                params = [
                    ("job", "stable-queue"),
                    # ("job", report["tree"]),
                    ("kernel_version", report["version"])
                ]
                response = utils.backend.get(url, params)
                handle_result(response, report, database, options)
    finally:
        connection.close()
