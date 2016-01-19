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

"""Database connection."""

import logging
import pymongo
import sys

DB_NAME = "kernelci-reports"
DB_CHECK_QUEUE = "check_queue"

# pylint: disable=invalid-name
log = logging.getLogger("kernelci-reports")


def get_connection(options):
    """Get connection to the database.

    :param options: The database connection parameters.
    :type options: dict
    :return A database connection instance.
    """
    options_get = options.get

    db_host = options_get("database_host", "localhost")
    db_port = options_get("database_port", 27017)
    db_pool = options_get("database_pool", 100)

    db_user = options_get("database_user", "")
    db_pwd = options_get("database_password", "")

    try:
        log.debug("Retrieving database connection...")
        db_connection = pymongo.MongoClient(
            host=db_host, port=db_port, maxPoolSize=db_pool, w="majority")

        if all([db_user, db_pwd]):
            log.debug("Authenticating to the database...")
            db_connection.authenticate(db_user, password=db_pwd)
    except pymongo.errors.ConnectionFailure:
        log.error("Cannot connect to the database, aborting")
        sys.exit(1)

    return db_connection
