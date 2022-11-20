from abc import abstractmethod
from datetime import datetime
from datetime import timedelta

from typing import Dict


class DNSServer:
    class DNSRecord:
        """
        Record is to be keyed on the hostname.
        Hostname must be all lower case.
        """

        def __init__(self, hostname: str, ip: str, record: str, static: bool):
            assert hostname.islower()
            self.hostname = hostname
            self.ip_address = ip
            self.record_type = record
            self.static = static

        def print(self):
            print(f"   Hostname: {self.hostname}")
            print(f" IP Address: {self.ip_address}")
            print(f"Record Type: {self.record_type}")
            print(f"     static: {'Yes' if self.static else 'No'}")

        def __eq__(self, other) -> bool:
            """
            Performs attribute by attribute equality check between two DNS Records
            :type other DNSServer.DNSRecord
            :param other: DNS Record to compare to
            :return: True if equal, False if not
            """
            if self.static != other.static:
                return False
            if self.hostname != other.hostname:
                return False
            if self.ip_address != other.ip_address:
                return False
            if self.record_type != other.record_type:
                return False
            return True

    _dns_records: Dict[str, DNSRecord]

    def print_dns_records(self):
        """
        Pretty print DNS records
        """
        print("==DNS Records==")
        for entry in self._dns_records:
            self._dns_records[entry].print()
            print("")

    def get_all_dns_records(self):
        return self._dns_records

    def get_single_dns_record(self, hostname):
        return self._dns_records[hostname]

    @abstractmethod
    def import_dns_records(self) -> Dict[str, DNSRecord]:
        """
        Import DNS records from file or command line.
        """


class DHCPServer:
    class DHCPLease:
        def __init__(self,
                     mac: str,
                     hostname: str,
                     static: bool,
                     ip: str,
                     lease_start: datetime = None,
                     lease_end: datetime = None,
                     lease_duration: timedelta = None,
                     comment: str = None):

            self.mac_address = mac
            self.ip_address = ip if ip else "0.0.0.0"
            self.hostname = hostname if hostname else ""
            self.static = static
            self.lease_start = lease_start          # Optional
            self.lease_end = lease_end              # Optional
            self.lease_duration = lease_duration    # Optional
            self.comment = comment                  # Optional

            # If lease duration, start, end, etc is none assume lease is 0 (doesn't expire)
            if (self.lease_start is None or self.lease_end is None) and self.lease_duration is None:
                assert self.static is True
                self.lease_duration = timedelta(minutes=0)

        def set_comment(self, message):
            self.comment = message

        def print(self):
            print(f"         ip: {self.ip_address}")
            print(f"        mac_address: {self.mac_address}")
            print(f"   hostname: {self.hostname}")
            print(f"     static: {'Yes' if self.static else 'No'}")
            print(f"lease start: {self.lease_start}")
            print(f"  lease end: {self.lease_end}")
            print(f" lease time: {self.lease_duration}")
            print(f"    comment: {self.comment}")

        def __eq__(self, other) -> bool:
            """
            Performs attribute by attribute equality check between two DNS Records
            :type other DHCPServer.DHCPLease
            :param other: DHCP Record to compare to
            :return: True if equal, False if not
            """
            if self.mac_address != other.mac_address:
                return False
            if self.ip_address != other.ip_address:
                return False
            if self.hostname != other.hostname:
                return False
            if self.static != other.static:
                return False
            if self.lease_duration != other.lease_duration:
                return False
            return True
    _leases: Dict[str, DHCPLease]

    def print_dhcp_leases(self):
        """
        Pretty print DHCP lease information
        """
        print("==DHCP Leases==")
        for entry in self._leases:
            self._leases[entry].print()
            print("")

    @abstractmethod
    def lease_config_export(self):
        """
        Read DHCP leases. Implemented by DHCP server of Pfsense and RouterOS
        :returns: Dictionary of DHCP leases keyed on mac_address address
        :rtype: dict[str, DHCPServer.DHCPLease]
        """

    def get_all_dhcp_leases(self):
        """
        Return all DHCP leases from _leases
        Leases are keyed on MAC address.
        :return: ._leases
        :rtype: dict[str, DHCPServer.DHCPLease]
        """
        return self._leases

    def get_single_dhcp_lease(self, mac_address):
        """
        Return single DHCP lease from _leases using MAC address key.
        :param mac_address: MAC address of desired DHCP lease in XX:XX:XX:XX:XX:XX format
        :type mac_address: str
        :return: Single lease from _leases
        :rtype: DHCPServer.DHCPLease
        """
        return self._leases[mac_address]
