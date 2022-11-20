import sys
import time
from typing import Dict

import base_classes
import secrets
import serial
import re
from datetime import timedelta

_BASE_COMMENT = "Added by pfsense. mode:router."


class MikrotikDNS(base_classes.DNSServer):

    def __init__(self, handle, skip_import):
        """
        :param handle:
        Handle to a RouterOS object. Used to read and write to the RouterOS console.
        :type handle: RouterOS
        """
        self._ros_handle = handle
        if not skip_import:
            self._dns_records = self.import_dns_records()

    def print_dns_records(self):
        print("====MIKROTIK====")
        super().print_dns_records()

    def import_dns_records(self):
        """
        Import (static) DNS records from RouterOS.
        :returns: Dictionary of DNS records keyed on hostname
        :rtype: dict[str, MikrotikDNS.DNSRecord]

        EXAMPLE CONSOLE OUTPUT
        [admin@mk_sw3] > /ip/dns/static/export
        # oct/30/2022 22:27:32 by RouterOS 7.5
        # software id = 1IFA-YT6T
        #
        # model = RB5009UPr+S+
        # serial number = HCZ080WFJ4F
        /ip dns static
        add address=10.0.0.1 comment=mode:router disabled=yes name=mk_sw3.lan
        add address=10.0.0.2 comment="Added by pfsense. mode:router" disabled=yes name=mk_sw1.lan
        """
        print("Importing RouterOS DNS Records")
        # Magic regex to find ipv4
        # ^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$
        res = "NULL"
        attempt = 0
        while res == "NULL":
            self._ros_handle.write("/ip/dns/static/export")
            res = self._ros_handle.read()
            attempt += 1
        static_dns_records: Dict[str, MikrotikDNS.DNSRecord] = {}

        items = re.split(' |\r\n', res)

        ip = None
        name = None
        for item in items:
            # Only match if we have not found an IP. This is to prevent matching 'address=' in a comment.
            if item.startswith("address=") and ip is None:
                # assert name is None and ip is None
                ip = item[8:]

            # Doesn't matter if we accidentally match to name= in comment
            # because name= field follows comment and will overwrite
            if item.startswith("name="):
                # assert name is None and ip is not None
                name = item[5:]

            # If ip and name are found then we have a new record
            if name is not None and ip is not None:
                dns_record = self.DNSRecord(name, ip, "A", True)

                # Deal with cleaning up any potentially invalid records
                if name not in static_dns_records.keys():
                    # Only add to dns record if this is a new hostname
                    static_dns_records[name] = dns_record
                else:
                    # Multiple entries for the same hostname are not allowed.
                    # Delete all records for this hostname and let the sync figure things out later.
                    self.remove_all_records_for_hostname(name)
                    del static_dns_records[name]
                    print(f"Removed {name} because multiple entries exist for hostname.")

                # Reset
                name = None
                ip = None

        return static_dns_records

    def add_single_dns_record(self, dns_record):
        """
        Add a single DNS record to RouterOS.
        Does NOT add record if an exact record already exists.
        Conflicting records are removed if they exist.
        :param dns_record: DNS Record object to add
        :type dns_record MikrotikDNS.DNSRecord
        :return: Nothing
        """

        if dns_record.hostname in self._dns_records.keys():
            if dns_record == self._dns_records[dns_record.hostname]:
                print(f"Skipped adding DNS for {dns_record.hostname} because exact record already exists")
                return
            else:
                # Record for host exists but isn't an exact match
                self.remove_all_records_for_hostname(dns_record.hostname)
                del self._dns_records[dns_record.hostname]

        command = f"/ip/dns/static/add " \
                  f"name={dns_record.hostname} " \
                  f"type={dns_record.record_type} " \
                  f"address={dns_record.ip_address} " \
                  f"disabled=yes " \
                  f"comment=\"{_BASE_COMMENT} static:{dns_record.static}.\""
        self._ros_handle.write(command)
        self._dns_records[dns_record.hostname] = dns_record
        self._ros_handle.read()

    def add_dns_records(self, dns_records):
        """
        Add all DNS records in dns_records parameter to RouterOS
        Does NOT add record if an exact record already exists.
        Conflicting records are removed if they exist.
        :param dns_records: Dict of DNS Records to add
        :type dns_records dict[str, MikrotikDNS.DNSRecord]
        :return: Nothing
        """
        print("Adding DNS Records")
        for record in dns_records:
            self.add_single_dns_record(dns_records[record])

    def remove_dns_records_exactly_matching(self, dns_record: base_classes.DNSServer.DNSRecord):
        """
        Remove DNS records that are an exact match for dns_record
        :param dns_record:
        :return:
        """
        command = f"/ip/dns/static/remove [find name={dns_record.hostname} address={dns_record.ip_address}]"
        self._ros_handle.write(command)
        self._ros_handle.read()

    def remove_all_records_for_hostname(self, hostname: str):
        """
        Remove all DNS records for hostname
        :param hostname:
        :return:
        """
        command = f"/ip/dns/static/remove [find name={hostname}]"
        self._ros_handle.write(command)
        self._ros_handle.read()

    def remove_all_pfsense_records(self):
        """
        Remove all DNS records created by this script.
        Resync _dns_records
        :return:
        """
        command = f"/ip/dns/static/remove [find comment~\"Added by pfsense\"]"
        self._ros_handle.write(command)
        self._ros_handle.read()
        self._dns_records = self.import_dns_records()


class MikrotikDHCP(base_classes.DHCPServer):
    def __init__(self, handle, skip_import):
        """
        Handles implementation details of managing DHCP leases of RouterOS
        :param handle:
        Handle to a RouterOS object. Handle is used to read and write to RouterOS console
        :type handle: RouterOS
        :returns: Instance of MikrotikDHCP
        :rtype: MikrotikDHCP
        """
        self._ros_handle = handle
        if not skip_import:
            self._leases = self.lease_config_export()

        # _leases are keyed on MAC address

    def print_dhcp_leases(self):
        print("====MIKROTIK====")
        super().print_dhcp_leases()

    def lease_config_export(self):
        """
        Load all current DHCP leases from the RouterOS console.
        :returns: Dictionary of MikrotikDHCP.DHCPLease keyed on MAC address
        :rtype: dict[str, MikrotikDHCP.DHCPLease]
        """

        # TODO: Change how read and write is handled so re-attempts can be moved there
        def retry_command(command):
            attempt = 0
            _result = "NULL"

            while _result == "NULL":
                self._ros_handle.write(command)
                self._ros_handle.write("")
                _result = self._ros_handle.read()
                attempt += 1
            return _result

        print("Importing RouterOS DHCP Leases")

        result = retry_command("/ip/dhcp-server/lease export terse")
        items = re.split('/ip dhcp-server lease add', result.replace("\r\n", ""))
        start_index = 0
        # Massage the list a little bit
        for index, item in enumerate(items):
            # Strip out any leading or trailing whitespace
            items[index] = item.strip()

            # Find the start of the 'real' data (after the terminal prompt)
            # \[[^\]]+@[^\]]+\] looks for terminal prompt in format of [user@something]
            if "/ip/dhcp-server/lease export terse" in item and re.search('\[[^]]+@[^]]+]', item) is not None:
                start_index = index + 1

            # Cut off the trailing garbage on the last line
            if index == len(items)-1:
                end_of_item = item.find("\r") - 1
                items[index] = items[index][:end_of_item]

        items = items[start_index:]
        dhcp_leases: Dict[str, MikrotikDHCP.DHCPLease] = {}

        for item in items:
            # ([\w-]+)=(".+?"|[\S]+)(?= [\w-]+=|\s*\Z) does two group matches on key=value string
            matches = re.findall('([\w-]+)=(".+?"|\S+)(?= [\w-]+=|\s*\Z)', item)
            matches_dict = dict((key, val) for key, val in matches)
            mac_address = matches_dict['mac-address']

            try:
                ip_address = matches_dict['address']
            except KeyError:
                # Value not used. Assume system default is used.
                # 0.0.0.0 means RouterOS will assign an IP dynamically
                static = False
                ip_address = "0.0.0.0"

            try:
                hostname = matches_dict['client-id']
            except KeyError:
                hostname = None

            try:
                comment = matches_dict['comment'][1:-1]  # Stripping quotes from terminal return
            except KeyError:
                comment = None

            try:
                static = False
                lease_time = matches_dict['lease-time']
                if lease_time[-1] == "s":
                    lease_time = timedelta(seconds=int(lease_time[:-1]))
                elif lease_time[-1] == "m":
                    lease_time = timedelta(minutes=int(lease_time[:-1]))
                elif lease_time[-1] == "h":
                    lease_time = timedelta(hours=int(lease_time[:-1]))
                elif lease_time[-1] == "d":
                    lease_time = timedelta(days=int(lease_time[:-1]))
                else:
                    print("WARNING: Couldn't parse lease duration. Assuming it is in hours.")
                    lease_time = timedelta(hours=int(lease_time[:-1]))
            except KeyError:
                # If not set, use the default routeros lease time of 0 (never expires)
                lease_time = timedelta(seconds=0)
                static = True

            dhcp_leases[mac_address] = MikrotikDHCP.DHCPLease(mac_address,
                                                              hostname,
                                                              static,
                                                              ip_address,
                                                              lease_duration=lease_time,
                                                              comment=comment)
        return dhcp_leases

    def add_single_dhcp_lease(self, lease: base_classes.DHCPServer.DHCPLease):

        if lease.mac_address in self._leases.keys():
            if lease == self._leases[lease.mac_address]:
                print(f"Skipped adding lease for {lease.mac_address} because exact record already exists")
                return
            else:
                # Record for host exists but isn't an exact match
                print(f"Lease exists for {lease.mac_address} ({lease.ip_address}) but isn't an exact match. Replacing.")
                self.remove_dhcp_lease_matching_mac(lease)

        command = "/ip/dhcp-server/lease/add"
        if lease.ip_address:
            command = f"{command} address={lease.ip_address}"
        if lease.hostname:
            command = f"{command} client-id={lease.hostname}"
        if lease.lease_duration:
            command = f"{command} lease-time={int(lease.lease_duration.total_seconds())}s"
        if lease.mac_address:
            command = f"{command} mac-address={lease.mac_address}"

        command = f"{command} disabled=yes"
        command = f"{command} comment=\"{_BASE_COMMENT} static:{lease.static}.\""
        self._ros_handle.write(command)
        return self._ros_handle.read()

    def add_dhcp_leases(self, leases: Dict[str, base_classes.DHCPServer.DHCPLease]):
        """
        Add all DHCP leases contained in the leases dictionary to the routeros device.
        Re-imports DHCP leases after all leases have been added.
        :param leases: Dictionary of DHCPLease to be added
        :return:
        None
        """
        for mac in leases:
            self.add_single_dhcp_lease(leases[mac])

        self._leases = self.lease_config_export()

    def remove_dhcp_lease_matching_mac(self, lease: base_classes.DHCPServer.DHCPLease):
        key = lease.mac_address
        if key in self._leases.keys():
            command = f"/ip/dhcp-server/lease/remove [find mac-address={key}]"
            self._ros_handle.write(command)
            self._ros_handle.read()
            del self._leases[key]

    def remove_all_pfsense_records(self):
        """
        Remove all DHCP records created by this script.
        Resync _leases
        :return:
        """
        command = f"/ip/dhcp-server/lease/remove [find comment~\"Added by pfsense\"]"
        self._ros_handle.write(command)
        self._ros_handle.read()
        self._leases = self.lease_config_export()


class RouterOS:
    def __init__(self, connection_string: str, baud_rate: int, skip_import: bool = True):
        """
        Note: Only serial connection is implemented at this time
        :param connection_string: Serial Port or IP address associated with RouterOS device
        """
        if "COM" in connection_string or "tty" in connection_string:
            self.serial_port = serial.Serial(connection_string)
            self.serial_port.baudrate = baud_rate
            self.serial_port.parity = "E"
            self.serial_port.stopbits = 1
            self.serial_port.bytesize = 8
            self.serial_port.timeout = 1
            assert self.serial_port.is_open
        else:
            print(f"{connection_string} is Invalid or Not Implemented! ")
            raise NotImplementedError

        self.logged_in = False
        self.logged_in = self.login()
        exit(-1) if self.logged_in is False else 'Do Nothing'

        self.dns_server = MikrotikDNS(handle=self, skip_import=skip_import)
        self.dhcp_server = MikrotikDHCP(handle=self, skip_import=skip_import)

    def write(self, command: str, print_command: bool = True) -> int:
        """
        Writes command to RouterOS terminal.

        :param command: Command to write to RouterOS terminal
        :param print_command: (Optional)
        :returns: Number of characters written to terminal
        :rtype: int
        """
        encoded_data = f"{command}\r\n".encode()
        ret = self.serial_port.write(encoded_data)
        if print_command:
            print("=== WRITE ===")
            print(command)
            self.serial_port.flush()
            print("=== END WRITE ===")
        return ret

    def read(self) -> str:
        """
        Reads terminal and prints terminal output with ansi escape characters included.
        :returns: Decoded terminal output with ansi escape characters removed.
        :rtype: str
        """
        print(f"=== READ ===")
        # Some sort of regex magic to remove escape characters
        ansi_escape = re.compile(r'(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]')
        time.sleep(0.5)
        serial_ret = b''
        """
        while self.serial_port.in_waiting > 0:
            self.serial_port.timeout = ((self.serial_port.in_waiting * 8) / self.serial_port.baudrate) + extra_delay + 1
            time.sleep(extra_delay)
            serial_ret += self.serial_port.read(self.serial_port.in_waiting)
            sys.stdout.write("\r\rRemaining: {0}".format(str(self.serial_port.in_waiting)))
            sys.stdout.flush()
        """
        # Changing the latency timer to 1ms seems to have allowed this to work, but the while loop above still
        # doesn't work.
        while True:
            sys.stdout.write("\r\rRemaining: {0}".format(str(self.serial_port.in_waiting)))
            sys.stdout.flush()
            ret = self.serial_port.read(1)
            if ret:
                serial_ret += ret
            else:
                break

        print("")
        serial_ret = serial_ret.decode()
        serial_ret = ansi_escape.sub('', serial_ret)
        lines = serial_ret.split("\r")

        # TODO: [admin@mk_sw3] shouldn't be hard coded
        if "[admin@mk_sw3]" in lines[-1] or "Login:" in serial_ret or "Password:" in serial_ret:
            print(serial_ret)
            print(f"=== END READ ===")
            return serial_ret
        else:
            print("Did not reach end of read")
            return "NULL"

    def login(self) -> bool:
        """
        Login to terminal.
        Login steps are skipped automatically if serial session is already logged in.
        :returns: True if successful or already logged in, False otherwise
        :rtype: bool
        """
        self.write("")
        read_res = self.read()
        if "Login" in read_res:
            self.write(secrets.routeros_username)
            read_res = self.read()
        else:
            print("No login field.")

        if "Password:" in read_res:
            self.write(secrets.routeros_password)
        else:
            print("No password field")

        self.write("")
        read_res = self.read()
        if "[admin@" in read_res and ">" in read_res or "Press F1 for help" in read_res:
            print("Login Success or already logged in")
            return True
        else:
            print("Login Failure")
            return False

    def logout(self) -> str:
        """
        Logout and return terminal output
        :return: Terminal output with escape characters removed.
        :rtype: str
        """
        self.write('quit')
        print("Logged out.")
        return self.read()

    def set_mode(self, mode: str):
        assert mode == "router" or mode == "switch"
        self.write(f":global mode {mode}")
        self.read()
        self.write("/system/script/run setMode")
        self.read()

    def __del__(self):
        """
        Closes serial port if it is open
        """
        if self.serial_port.is_open:
            self.serial_port.close()
