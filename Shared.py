from __future__ import annotations  # for Python 3.7-3.9
from typing_extensions import TypedDict
from datetime import timedelta

import re


class RegexHelper:
    # Matches text contained within quotes
    quoted_text = re.compile('\"([^"]+)\"')

    # Matches text in the format of [something@somethingelse]
    terminal_prompt = re.compile('\[[^]]+@[^]]+]')

    get_key_equal_value_groups = re.compile('([\w-]+)=(".+?"|\S+)(?= [\w-]+=|\s*\Z)')
    """ Returns two groups. Group 1 is the key and Group 2 is the value of the key """

    @staticmethod
    def convert_kv_string_to_dict(message: str) -> dict:
        """
        Finds key value pairs defined in message. Key value pairs must be 'key=value'.
        Values with spaces much be contained in quotes.

        :param message: String containing key value pairs. Multiple kv pairs per string are allowed.
        :return: Dictionary of kv pairs contained in message
        """
        return dict((key, val) for key, val in re.findall(RegexHelper.get_key_equal_value_groups, message))


class DNSRecord(TypedDict):
    """
    | ip_address: str
    | hostname: str
    | record_type: str
    """
    ip_address: str
    hostname: str
    record_type: str


class DHCPLease(TypedDict):
    """
    | mac_address: str
    | ip_address: str
    | hostname: str
    | lease_duration: timedelta
    """
    mac_address: str
    ip_address: str
    hostname: str
    lease_duration: timedelta
