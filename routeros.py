import time

import base_classes
import secrets
import serial
import re
from datetime import timedelta

_BASE_COMMENT = "Added by pfsense. mode:router."


class MikrotikDNS(base_classes.DNSServer):

    def __init__(self, handle, do_import):
        """
        :param handle:
        Handle to a RouterOS object. Used to read and write to the RouterOS console.
        :type handle: RouterOS
        """
        self._ros_handle = handle
        if do_import:
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
        self._ros_handle.write("/ip/dns/static/export")
        res = self._ros_handle.read()
        static_dns_records: dict[str, MikrotikDNS.DNSRecord] = {}

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
    def __init__(self, handle, do_import):
        """
        Handles implementation details of managing DHCP leases of RouterOS
        :param handle:
        Handle to a RouterOS object. Handle is used to read and write to RouterOS console
        :type handle: RouterOS
        :returns: Instance of MikrotikDHCP
        :rtype: MikrotikDHCP
        """
        self._ros_handle = handle
        if do_import:
            self._leases = self.import_dhcp_leases()

        # _leases are keyed on MAC address

    def print_dhcp_leases(self):
        print("====MIKROTIK====")
        super().print_dhcp_leases()

    def import_dhcp_leases(self):
        """
        Load all current DHCP leases from the RouterOS console.
        :returns: Dictionary of MikrotikDHCP.DHCPLease keyed on MAC address
        :rtype: dict[str, MikrotikDHCP.DHCPLease]
        """
        print("Importing RouterOS DHCP Leases")
        self._ros_handle.write("/ip/dhcp-server/lease export")
        res = self._ros_handle.read()
        dhcp_leases: dict[str, MikrotikDHCP.DHCPLease] = {}

        iter_items = iter(re.split(' |\r\n', res))
        debug_items = re.split(' |\r\n', res)
        ip_address = None
        lease_time = None
        mac_address = None
        hostname = None
        static = None
        comment = None

        def submit_info():
            # Commit the values we found to dhcp_leases

            nonlocal ip_address
            nonlocal lease_time
            nonlocal mac_address
            nonlocal hostname
            nonlocal static
            nonlocal comment

            if lease_time is None:
                # If no lease time was found assume it is static
                static = True

            # TODO: Figure out how to determine if actually static
            # Maybe start parsing comment and use that.

            # Wasn't able to determine static in initial parse, but if lease doesn't expire it must be static
            if static is None and (lease_time is None or lease_time == timedelta(minutes=0)):
                # Must be static if lease never expires
                static = True

            dhcp_leases[mac_address] = MikrotikDHCP.DHCPLease(mac_address, hostname, static, ip_address,
                                                              lease_duration=lease_time, comment=comment)
            lease_time = None
            mac_address = None
            hostname = None
            static = None
            ip_address = None
            comment = None

        def skip_until_value_found():
            nonlocal item
            nonlocal iter_items
            item = next(iter_items)
            while item == "":
                item = next(iter_items)
            return item

        # TODO: Make this more robust against malignant comments.
        for item in iter_items:

            if item.startswith("add") and mac_address is not None:
                # We are at the start of a new loop
                submit_info()

            if item.startswith("address=") and ip_address is None:
                ip_address = item[8:]

            if item.startswith("lease-time="):
                lease_time = item[11:]

                if lease_time[:-1].isnumeric():
                    if int(lease_time[:-1]) == 0:
                        static = True

                else:
                    print("Lease time is not a number!")
                    raise Exception

                if lease_time[-1] == "s":
                    lease_time = timedelta(seconds=int(lease_time[:-1]))
                elif lease_time[-1] == "m":
                    lease_time = timedelta(minutes=int(lease_time[:-1]))
                elif lease_time[-1] == "h":
                    lease_time = timedelta(hours=int(lease_time[:-1]))
                elif lease_time[-1] == "d":
                    lease_time = timedelta(days=int(lease_time[:-1]))
                else:
                    print("Couldn't parse lease duration")
                    raise Exception

            if item.startswith("mac-address="):
                assert mac_address is None
                if "=\\" in item:
                    mac_address = str.lower(skip_until_value_found())
                else:
                    mac_address = str.lower(item[12:])

            if item.startswith("client-id="):
                hostname = item[10:].replace("\"", "")

            if item.startswith("comment="):
                # Find start of comment
                if "=\\" in item:
                    comment = skip_until_value_found()
                else:
                    comment = item[8:]

                # Do-While not at end of comment
                while True:
                    item = next(iter_items)
                    comment = f"{comment} {item}"
                    if "static:" in item:
                        val = item.split(":")[-1].replace(".", "").replace("\"", "")
                        static = eval(val)
                    if item[-1] == "\"":
                        break

        # Deal with the case at the end of loop where return to 'add' never happens (I.E, only 1 entry or on last entry)
        if mac_address:
            submit_info()

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

    def add_dhcp_leases(self, leases: dict[str, base_classes.DHCPServer.DHCPLease]):
        """
        Add all DHCP leases contained in the leases dictionary to the routeros device.
        Re-imports DHCP leases after all leases have been added.
        :param leases: Dictionary of DHCPLease to be added
        :return:
        None
        """
        for mac in leases:
            self.add_single_dhcp_lease(leases[mac])

        self._leases = self.import_dhcp_leases()

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
        self._leases = self.import_dhcp_leases()


class RouterOS:
    def __init__(self, connection_string: str, baud_rate: int, do_import: bool = True):
        """
        Note: Only serial connection is implemented at this time
        :param connection_string: Serial Port or IP address associated with RouterOS device
        """
        if "COM" in connection_string or "tty" in connection_string:
            self.serial_port = serial.Serial(connection_string)
            self.serial_port.baudrate = baud_rate
            self.serial_port.parity = "N"
            self.serial_port.stopbits = 1
            self.serial_port.bytesize = 8
            self.serial_port.timeout = 60
            self.serial_port.inter_byte_timeout = 1

            assert self.serial_port.is_open
        else:
            print(f"{connection_string} is Invalid or Not Implemented! ")
            raise NotImplementedError

        self.logged_in = False
        self.logged_in = self.login()
        exit(-1) if self.logged_in is False else 'Do Nothing'

        self.dns_server = MikrotikDNS(handle=self, do_import=do_import)
        self.dhcp_server = MikrotikDHCP(handle=self, do_import=do_import)

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

        # Some sort of regex magic to remove escape characters
        ansi_escape = re.compile(r'(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]')
        serial_ret = self.serial_port.read(100000)

        print(f"=== READ ===")
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
            return ""

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
            self.write(secrets.routeros_password)  # TODO: Make this less blatantly insecure
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
