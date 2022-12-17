from __future__ import annotations  # for Python 3.7-3.9
from datetime import datetime
from datetime import timedelta

import config_defaults

from Shared import DHCPLease
from Shared import DNSRecord
from Shared import RegexHelper


class PFSenseDevice:
    """
    Collection of methods for parsing Pfsense configuration
    """

    # TODO: Make the ignored things configurable
    @staticmethod
    def get_reserved_dns_records() -> list[DNSRecord]:
        """
        Get reserved/preconfigured DNS records, excluding the record for pfsense itself and mk_sw3.lan
        """
        static_dns_records = []
        if config_defaults.host_entries_file:
            file_dir = config_defaults.host_entries_file
        else:
            file_dir = "/var/unbound/host_entries.conf"

        with open(file_dir, 'r') as reader:
            file = reader.read()
            lines = iter(file.split("\n"))
            for line in iter(lines):
                static_dns_record: DNSRecord
                line = line.replace("\"", "")
                # TODO: Make this less horrible and more configurable
                if line.startswith("local-data:"):  # Found alias
                    if 'localhost' not in line \
                            and 'pfsense.lan' not in line \
                            and '10.0.0.1' not in line \
                            and 'mk_sw3.lan' not in line:
                        data = line.split(" ")
                        static_dns_record = {'hostname': data[1][:-1].lower(),
                                             'ip_address': data[3],
                                             'record_type': data[2],
                                             }
                        static_dns_records.append(static_dns_record)

        return static_dns_records

    @staticmethod
    def get_dynamic_dhcp_leases() -> list[DHCPLease]:
        """
        Get the DHCP leases assigned from the DHCP pool. This does not include preconfigured / reserved leases.
        :return: List of PfsenseDHCPLease dict
        """
        if config_defaults.dhcp_leases_file:
            file_path = config_defaults.dhcp_leases_file
        else:
            file_path = "/var/dhcpd/var/db/dhcpd.leases"

        leases: list[DHCPLease] = []
        domain_name = PFSenseDevice.get_domain_name()

        with open(file_path, 'r') as reader:
            file = reader.read()
            lines = iter(file.split("\n"))
            for line in iter(lines):
                if line.startswith("lease"):  # Found host
                    ip_address = line.split(" ")[1]
                    lease_start = datetime.now()
                    lease_end = datetime.now()
                    mac_address = ""
                    hostname = ""

                    while "}" not in line:
                        # Check for MAC, IP, hostname, and lease time until the end of the host block.
                        line = next(lines)

                        # TODO: Add fallback / default values
                        if "starts" in line:
                            datetime_list = line.replace(';', '').split(" ")[4:]
                            lease_start = datetime.strptime(f"{datetime_list[0]} {datetime_list[1]}",
                                                            "%Y/%m/%d %H:%M:%S")
                        if "ends" in line and "ends never" not in line:
                            datetime_list = line.replace(';', '').split(" ")[4:]
                            lease_end = datetime.strptime(f"{datetime_list[0]} {datetime_list[1]}",
                                                          "%Y/%m/%d %H:%M:%S")
                        if "hardware ethernet" in line:
                            mac_address = line.replace(";", "").split(" ")[-1].upper()

                        if "client-hostname" in line:
                            hostname = line.replace(";", "").split(" ")[-1].replace("\"", "") + domain_name

                    leases.append(DHCPLease(
                        mac_address=mac_address,
                        ip_address=ip_address,
                        hostname=hostname,
                        lease_duration=lease_end - lease_start
                    ))
            return leases

    @staticmethod
    def get_reserved_dhcp_leases() -> list[DHCPLease]:
        """
        Get reserved DHCP records. This includes records that have a reserved DHCP assigned hostname, even if no IP
        is reserved by the reserved DHCP record. Reserved lease config does not have a start or end date.
        :return:
        """
        # /var/dhcpd/etc/dhcpd.conf
        if config_defaults.dhcpd_conf_file:
            file_path = config_defaults.dhcpd_conf_file
        else:
            file_path = "/var/dhcpd/etc/dhcpd.conf"
        leases: list[DHCPLease] = []
        with open(file_path, 'r') as reader:
            file = reader.read()
            lines = iter(file.split("\n"))
            subclass_prefix = ''
            domain_name = ''
            default_lease_seconds = 7200

            for line in lines:
                if line.startswith("option domain-name") and domain_name == '':
                    domain_name = f".{RegexHelper.quoted_text.search(line).group(1)}"
                if line.startswith("class"):
                    subclass_prefix = RegexHelper.quoted_text.search(line).group(1)
                if line.startswith("default-lease-time"):
                    default_lease_seconds = int(line.replace(";", "").split(" ")[-1])
                if subclass_prefix != '':
                    if line.startswith(f'host {subclass_prefix}_'):
                        mac_address, ip_address, hostname = "", "", ""
                        # Host record found
                        while line != '}':
                            line = next(lines)
                            if "hardware ethernet" in line:
                                mac_address = line.replace(";", "").split(" ")[-1].upper()
                                continue
                            if "fixed-address" in line:
                                ip_address = line.replace(";", "").split(" ")[-1]
                                continue
                            if "option host-name" in line:
                                assert domain_name != ''
                                hostname = line.replace(";", "").split(" ")[-1].replace("\"", "") + domain_name
                                continue

                        leases.append(DHCPLease(
                            mac_address=mac_address,
                            ip_address=ip_address,
                            hostname=hostname,
                            lease_duration=timedelta(seconds=default_lease_seconds)
                        ))
        return leases

    @staticmethod
    def get_domain_name():
        if config_defaults.dhcpd_conf_file:
            file_path = config_defaults.dhcpd_conf_file
        else:
            file_path = "/var/dhcpd/etc/dhcpd.conf"

        with open(file_path, 'r') as reader:
            file = reader.read()
            lines = iter(file.split("\n"))
            for line in lines:
                if line.startswith("option domain-name"):
                    return "." + RegexHelper.quoted_text.search(line).group(1)
