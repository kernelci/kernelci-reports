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

"""Module to interact with the backend API."""

import logging
import requests

# pylint: disable=invalid-name
log = logging.getLogger("kernelci-reports")

# The requests session object.
req = requests.Session()
http_adapter = requests.adapters.HTTPAdapter(
    pool_connections=50, pool_maxsize=150)
req.mount("http://", http_adapter)
req.mount("https://", http_adapter)


def get(url, params):
    """Perform a GET request.

    :param url: The URL where to perform the request.
    :type url: str
    :param params: The list of parameters for the request.
    :type params: list
    :return A Response object.
    """
    log.debug("GET request to '%s' for %s", url, params)
    return req.get(url, params=params, timeout=(3.0, 7.0))


def post(url, data):
    """Perform a POST request.

    :param url: The URL where to perform the request.
    :type url: str
    :param data: The JSON data to send.
    :type data: dict
    :return A Response object.
    """
    log.debug("POST request with data: %s", data)
    return req.post(url, json=data)
