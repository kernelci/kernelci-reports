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

import datetime
import logging
import re

import utils
import utils.backend
import utils.db

# pylint: disable=invalid-name
log = logging.getLogger("kernelci-reports")

# Seconds to wait before the backend should send the email report.
SEND_DELAY = 12600
# TODO: need a better check for different git_describe format.
GIT_DESCRIBE_MATCHER = r"^v{0:s}-{1:s}-g(.*)"
# Format string to re-build to from email address.
FROM_ADR_FMT = "{0:s} <{1:s}>"
# Format string for the reply message.
REPLY_FMT = "Re: {0:s}"


def _add_api_endpoint(url, endpoint):
    """Check if the URL contains the trailing / and add the endpoit."""
    if url[-1] != "/":
        url += "/"
    return url + endpoint


def check_boots(result, options):
    """Verify there are boot reports in the backend.

    :param result: The result of the job from the backend.
    :type result: dict
    :param options: The app configuration parameters.
    :type options: dict
    :return A Response object.
    """
    log.debug("Checking boot results")
    r_get = result.get
    url = _add_api_endpoint(options[utils.BACKEND_URL], "count/boot")

    param = [("job", r_get("job")), ("kernel", r_get("kernel"))]

    return utils.backend.get(url, param)


def send_report(result, report, options):
    """Trigger the backend to send a report.

    :param result: The result from the backend API.
    :type result: dict
    :param report: The report as parsed from the email.
    :type report: dict
    :param options: The app configuration parameters.
    :type options: dict
    :return A Response object.
    """
    url = _add_api_endpoint(options[utils.BACKEND_URL], "send")
    report_get = report.get

    send_to = []
    from_addr = None

    if report_get("from")[0]:
        from_addr = FROM_ADR_FMT.format(
            report_get("from")[0], report_get("from")[1])
    else:
        from_addr = report_get("from")[1]

    send_to.append(from_addr)
    if report_get("to", None):
        send_to.extend(report_get("to"))

    # TODO: need a way to customize some of these values.
    data = {
        "delay": SEND_DELAY,
        "boot_report": 1,
        "job": result["job"],
        "kernel": result["kernel"],
        "git_branch": result["git_branch"],
        "format": ["txt"],
        "send_to": send_to
    }

    if report_get("message_id", None):
        data["in_reply_to"] = report_get("message_id")

    if report_get("subject", None):
        data["subject"] = REPLY_FMT.format(report_get("subject"))

    if report_get("cc", None):
        data["send_cc"] = report_get("cc")

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

    patterns = [
        GIT_DESCRIBE_MATCHER.format(report["version"], patches)
        for patches in report["patches"]
    ]

    def is_kernel_match(to_match):
        """Check if a kernel version matches the provided one."""
        matches = False

        for pattern in patterns:
            if re.match(pattern, git_describe):
                matches = True
                break

        return matches

    git_describe = \
        result.get("git_describe_v", None) or result.get("git_describe", None)

    if not git_describe or not is_kernel_match(git_describe):
        log.debug(
            "Git describe version does not match '%s', or no git "
            "describe value", patterns)
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
                log.info(
                    "Found valid job from backend: %s - %s - %s",
                    valid_result["job"],
                    valid_result["git_branch"],
                    valid_result["kernel"])

                status = valid_result["status"]
                if status == "PASS":
                    response = check_boots(valid_result, options)

                    if response.status_code == 200:
                        result = response.json()["result"][0]

                        # Check if we have the first boot reports in the
                        # backend. If so, schedule the email reports for
                        # later.
                        if int(result["count"]) > 0:
                            response = send_report(
                                valid_result, report, options)
                            if (response.status_code == 202 or
                                    response.status_code == 200):
                                _delete_report()
                        else:
                            log.info("No boot reports yet, retrying later")
                    else:
                        log.error("Error checking boot results from backend")
                elif status == "BUILD":
                    log.info("Job still building, retrying later")
                elif status == "FAIL":
                    _delete_report()
                    log.info("Job failed, will not send report")
            else:
                log.info(
                    "No valid results found from the backend, retrying later")
        else:
            log.warn("No results found yet, retrying later")
    elif response.status_code == 503:
        log.warn("Backend is in maintenance, retrying later")
    elif response.status_code == 400:
        log.error("Something wrong in the request, report will be discarded")
        _delete_report()
    elif response.status_code == 500:
        log.warn("Backend error, retrying later")


def check_and_send(options):
    """Check the queue and in case send the build/boot report.

    :param options: The app configuration parameters.
    :type options: dict
    """
    connection = utils.db.get_connection(options)

    try:
        database = connection[utils.db.DB_NAME]

        queued_reports = \
            database[utils.db.DB_CHECK_QUEUE].find(sort=[("created_on", 1)])

        utils.backend.req.headers.update(
            {"Authorization": options.get(utils.BACKEND_TOKEN, None)})

        url = _add_api_endpoint(options[utils.BACKEND_URL], "job")

        for report in queued_reports:
            r_get = report.get
            tree = r_get("tree")
            version = r_get("version")
            deadline = r_get("deadline")
            branch = r_get("branch")

            now = datetime.datetime.utcnow()
            # Time when the scheduled report should be sent by the backend.
            # If this value is bigger than deadline, no point in sending the
            # report.
            scheduled = now + datetime.timedelta(seconds=SEND_DELAY)

            log.info(
                "Working on: %s - %s / %s", tree, version, r_get("patches"))
            if now >= deadline or scheduled >= deadline:
                log.info(
                    "Removing mail request, past the deadline: %s - %s",
                    deadline, scheduled)
                database[utils.db.DB_CHECK_QUEUE].delete_one(
                    {"_id": r_get("_id")})
            else:
                params = [
                    ("job", tree),
                    ("kernel_version", version)
                ]
                if branch:
                    params.append(("git_branch", branch))
                response = utils.backend.get(url, params)
                handle_result(response, report, database, options)
    finally:
        connection.close()


def process(options, event):
    """Execute the operations inside the event protected zone.

    :param options: The app configuration parameters.
    :type options: dict
    :param event: The even object used to synchronize.
    :type event: threading.Event
    """
    if event.is_set():
        try:
            event.clear()
            check_and_send(options)
        finally:
            event.set()
    else:
        log.warn("Cannot send reports, other thread is blocking")
