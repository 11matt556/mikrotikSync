from typing import Dict

import base_classes
from datetime import datetime
from datetime import timedelta


class PfsenseDNS(base_classes.DNSServer):
    def __init__(self, host_entries_path):
        self._host_entries_path = host_entries_path
        self._dns_records = self.import_dns_records()

    def print_dns_records(self):
        print("====PFSENSE====")
        super().print_dns_records()

    def import_dns_records(self) -> Dict[str, base_classes.DNSServer.DNSRecord]:
        """
        Import DNS records from Pfsense. Currently only implements host_entries.conf parsing (static DNS)
        """

        # /var/unbound/host_entries.conf
        file_dir = self._host_entries_path
        static_dns_records = {}
        with open(file_dir, 'r') as reader:
            file = reader.read()
            lines = iter(file.split("\n"))
            for line in iter(lines):
                line = line.replace("\"", "")
                if line.startswith("local-data:"):  # Found alias
                    if 'localhost' not in line and 'pfsense.lan' not in line and '10.0.0.1' not in line and 'mk_sw3.lan' not in line:
                        data = line.split(" ")
                        hostname, record_type, ip_addr = data[1][:-1].lower(), data[2], data[3]
                        static_dns_records[hostname] = self.DNSRecord(hostname, ip_addr, record_type, True)

        return static_dns_records


class PfsenseDHCP(base_classes.DHCPServer):
    def __init__(self, static_lease_path, dynamic_lease_path):
        self._static_lease_path = static_lease_path
        self._dynamic_lease_path = dynamic_lease_path
        self._leases = self.lease_config_export()

    def print_dhcp_leases(self):
        print("====PFSENSE====")
        super().print_dhcp_leases()

    def lease_config_export(self):
        leases = {}
        domain_name = ''

        # Parse dhcpd.conf first. These are the static leases
        # /var/dhcpd/etc/dhcpd.conf
        file_path = self._static_lease_path
        with open(file_path, 'r') as reader:
            file = reader.read()
            lines = iter(file.split("\n"))
            for line in lines:
                if line.startswith("option domain-name") and leases == {} and domain_name == '':
                    domain_name = "." + line.split(" ")[-1].replace(";", "").replace("\"", "")

                if line.startswith("host s_lan_"):
                    mac = ""
                    ip = ""
                    hostname = ""
                    while '}' not in line:
                        # Check for MAC, IP, and hostname until the end of the host block.
                        line = next(lines)

                        if "hardware ethernet" in line:
                            mac = line.replace(";", "").split(" ")[-1]
                            continue
                        if "fixed-address" in line:
                            ip = line.replace(";", "").split(" ")[-1]
                            continue
                        if "option host-name" in line:
                            hostname = line.replace(";", "").split(" ")[-1].replace("\"", "") + domain_name
                            continue

                    leases[mac] = self.DHCPLease(mac, hostname, True, ip)

        # Now parse dhcp.leases for the dynamic leases
        # /var/dhcpd/var/db/dhcpd.leases
        file_path = self._dynamic_lease_path
        with open(file_path, 'r') as reader:
            file = reader.read()
            lines = iter(file.split("\n"))
            for line in iter(lines):
                if line.startswith("lease"):  # Found host
                    ip_address = line.split(" ")[1]
                    lease_start = datetime
                    lease_end = datetime
                    mac_address = ""
                    hostname = ""

                    while "}" not in line:
                        # Check for MAC, IP, hostname, and lease time until the end of the host block.
                        line = next(lines)

                        if "starts" in line:
                            datetime_list = line.replace(';', '').split(" ")[4:]
                            lease_start = datetime.strptime(f"{datetime_list[0]} {datetime_list[1]}",
                                                            "%Y/%m/%d %H:%M:%S")
                        if "ends" in line and "ends never" not in line:
                            datetime_list = line.replace(';', '').split(" ")[4:]
                            lease_end = datetime.strptime(f"{datetime_list[0]} {datetime_list[1]}",
                                                          "%Y/%m/%d %H:%M:%S")
                        if "hardware ethernet" in line:
                            mac_address = line.replace(";", "").split(" ")[-1]

                        if "client-hostname" in line:
                            hostname = line.replace(";", "").split(" ")[-1].replace("\"", "") + domain_name

                    leases[mac_address] = self.DHCPLease(mac_address, hostname, False, ip_address, lease_start,
                                                         lease_end, lease_end - lease_start)

            return leases


class Pfsense:
    def __init__(self, static_lease_path, dynamic_lease_path, host_entries_path):
        self.dns_server = PfsenseDNS(host_entries_path)
        self.dhcp_server = PfsenseDHCP(static_lease_path, dynamic_lease_path)
