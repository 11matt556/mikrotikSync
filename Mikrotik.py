from __future__ import annotations  # for Python 3.7-3.9
from serial import Serial
from serial import SerialException
from datetime import timedelta

import time
import sys
import re

from Shared import DNSRecord
from Shared import DHCPLease
from Shared import RegexHelper


def on_terminal_prompt(data):
    if data == '':
        return False
    elif re.search(RegexHelper.terminal_prompt, data.splitlines()[-1]) is not None:
        return True
    else:
        return False


def on_login_or_terminal_prompt(data):
    if "Login:" in data or "Password:" in data:
        return True
    elif on_terminal_prompt(data):
        return True
    else:
        return False


class MikrotikDHCPLease(DHCPLease):
    """
    | -----------------
    | DHCPLease
    | -----------------
    | mac_address: str
    | ip_address: str
    | hostname: str
    | lease_duration: timedelta
    | -----------------------------
    | MikrotikDHCPLease
    | -----------------------------
    | disabled: bool
    | comment: str
    """

    disabled: bool
    comment: str


class MikrotikDNSRecord(DNSRecord):
    """
    | -----------------
    | DNSRecord
    | -----------------
    | ip_address: str
    | hostname: str
    | record_type: str
    | -----------------------------
    | MikrotikDNSRecord
    | -----------------------------
    | disabled: bool
    | comment: str
    """
    disabled: bool
    comment: str


class MikrotikDevice:
    _serial_port: Serial = None
    _logged_in: bool = False

    def get_static_dns_records(self) -> list[MikrotikDNSRecord]:
        print("RouterOS: Importing Reserved DNS Records")
        reserved_dns_records: list[MikrotikDNSRecord] = []
        start_index = 0

        items = re.split('/ip dns static add', self.send_command("/ip/dns/static export terse").replace("\r\n", ""))
        # Remove whitespace and find starting index
        for index, item in enumerate(items):
            # Strip out any leading or trailing whitespace
            items[index] = item.strip()
            if 'software id' in item:
                start_index = index + 1

        # Cut off the trailing garbage on the last line
        items[-1] = items[-1][:items[-1].find("\r")]
        items = items[start_index:]

        for item in items:
            parsed_item = RegexHelper.convert_kv_string_to_dict(item)

            # TODO: Add if/else vs try/except performance tweak from DHCP?
            try:
                ip_address = parsed_item['address']
            except KeyError:
                ip_address = "0.0.0.0"

            try:
                hostname = parsed_item['name']
            except KeyError:
                hostname = ""

            try:
                record_type = parsed_item['type']
            except KeyError:
                record_type = "A"

            try:
                disabled = True if parsed_item['disabled'] == 'yes' else False
            except KeyError:
                disabled = False

            try:
                comment = parsed_item['comment']
            except KeyError:
                comment = ""

            reserved_dns_records.append(MikrotikDNSRecord(ip_address=ip_address,
                                                          hostname=hostname,
                                                          record_type=record_type,
                                                          disabled=disabled,
                                                          comment=comment))
        return reserved_dns_records

    def write_static_dns_record(self, record: MikrotikDNSRecord):
        command = "/ip/dns/static/add"

        if record['ip_address']:
            command += f" address=\"{record['ip_address']}\""
        if record['hostname']:
            command += f" name=\"{record['hostname']}\""
        if record['record_type'] != "" and record['record_type'] != "A":
            command += f" type=\"{record['record_type']}\""
        if record['disabled']:
            command += f" disabled=yes"
        if record['comment']:
            command += f" comment=\"{record['comment']}\""
        command += "]"

        self.send_command(command)
        return True

    def remove_static_dns_record(self, record: MikrotikDNSRecord):
        command = f"/ip/dns/static/remove [find"

        if record['ip_address']:
            command += f" address=\"{record['ip_address']}\""
        if record['hostname']:
            command += f" name=\"{record['hostname']}\""
        if record['record_type'] != "" and record['record_type'] != "A":
            command += f" type=\"{record['record_type']}\""
        if record['disabled']:
            command += f" disabled=yes"
        if record['comment']:
            command += f" comment=\"{record['comment']}\""
        command += "]"
        # Sanity check
        assert command != "/ip/dns/static/remove [find]"

        self.send_command(command)
        return True

    def remove_static_dns_with_comment_containing(self, message: str):
        command = f"/ip/dns/static/remove [find comment~\"{message}\"]"
        self.send_command(command)

    def get_reserved_dhcp_leases(self) -> list[MikrotikDHCPLease]:
        """
        Get all 'manually' added DHCP leases. I.E, Get leases not predefined or preconfigured.
        :returns: Dictionary of MikrotikDHCP.DHCPLease keyed on MAC address
        :rtype: dict[str, MikrotikDHCP.DHCPLease]
        """
        print("Importing RouterOS DHCP Leases")

        reserved_dhcp_leases: list[MikrotikDHCPLease] = []
        start_index = 0
        items = re.split('/ip dhcp-server lease add',
                         self.send_command("/ip/dhcp-server/lease export terse").replace("\r\n", ""))

        # Remove whitespace and find starting index
        for index, item in enumerate(items):
            # Strip out any leading or trailing whitespace
            items[index] = item.strip()
            if 'software id' in item:
                start_index = index + 1

        # Cut off the trailing garbage on the last line
        items[-1] = items[-1][:items[-1].find("\r")]
        items = items[start_index:]

        for item in items:
            parsed_item = RegexHelper.convert_kv_string_to_dict(item)
            keys = parsed_item.keys()

            # If statements are sometimes more performant than try/except when
            # value is likely to be present. Try/except is good when KeyError is unlikely (Like on the mac address key)

            if 'mac-address' not in keys and 'client-id' not in keys:
                raise KeyError("mac or hostname must be present")

            try:
                mac_address = parsed_item['mac-address']
            except KeyError:
                mac_address = ""

            try:
                ip_address = parsed_item['address']
            except KeyError:
                # Value not used. Assume system default is used.
                # RouterOS default is to use a dynamic IP assignment for MAC if no IP is provided in the config
                # RouterOS uses an IP of 0.0.0.0 to indicate dynamic assignment
                ip_address = "0.0.0.0"

            try:
                hostname = parsed_item['client-id']
            except KeyError:
                hostname = ""

            if 'disabled' in keys:
                disabled = True if parsed_item['disabled'] == 'yes' else False
            else:
                disabled = False

            comment = parsed_item['comment'] if 'comment' in keys else ""

            if 'lease-time' in keys:
                lease_duration = parsed_item['lease-time']
                if lease_duration[-1] == "s":
                    lease_duration = timedelta(seconds=int(lease_duration[:-1]))
                elif lease_duration[-1] == "m":
                    lease_duration = timedelta(minutes=int(lease_duration[:-1]))
                elif lease_duration[-1] == "h":
                    lease_duration = timedelta(hours=int(lease_duration[:-1]))
                elif lease_duration[-1] == "d":
                    lease_duration = timedelta(days=int(lease_duration[:-1]))
                else:
                    print("WARNING: Couldn't parse lease duration time unit. Assuming it is in hours.")
                    lease_duration = timedelta(hours=int(lease_duration[:-1]))
            else:
                # If not set, the default is being used. 0 duration indicates default. (10 minutes for ipv4 OOB)
                lease_duration = timedelta(seconds=0)

            reserved_dhcp_leases.append(MikrotikDHCPLease(mac_address=mac_address,
                                                          hostname=hostname,
                                                          ip_address=ip_address,
                                                          lease_duration=lease_duration,
                                                          disabled=disabled,
                                                          comment=comment))
        return reserved_dhcp_leases

    # TODO: Create exception cases for potential failures
    def write_reserved_dhcp_lease(self, lease: MikrotikDHCPLease):
        command = "/ip/dhcp-server/lease/add"

        command += f" mac-address=\"{lease['mac_address']}\""
        command += f" address=\"{lease['ip_address']}\""
        command += f" client-id=\"{lease['hostname']}\""
        command += f" disabled={'yes' if lease['disabled'] else 'no'}"
        command += f" lease-time={int(lease['lease_duration'].total_seconds())}"
        command += f" comment=\"{lease['comment']}\""

        self.send_command(command)
        return True

    # TODO: Create exception cases for potential failures
    def remove_reserved_dhcp_lease(self, lease: MikrotikDHCPLease):
        command = f"/ip/dhcp-server/lease/remove [find"

        if lease['mac_address']:
            command += f" mac-address=\"{lease['mac_address']}\""
        if lease['ip_address']:
            command += f" address=\"{lease['ip_address']}\""
        if lease['hostname']:
            command += f" client-id=\"{lease['hostname']}\""
        if lease['lease_duration'].total_seconds() != 0:
            command += f" lease-time={int(lease['lease_duration'].total_seconds())}"
        if lease['disabled']:
            command += f" disabled=yes"
        if lease['comment']:
            command += f" comment=\"{lease['comment']}\""
        command += "]"
        # Sanity check
        assert command != "/ip/dhcp-server/lease/remove [find]"

        self.send_command(command)
        return True

    def remove_static_leases_with_comment_containing(self, message: str):
        command = f"/ip/dhcp-server/lease/remove [find comment~\"{message}\"]"
        self.send_command(command)

    def send_command(self, command: str, look_for='terminal'):
        self._write(command)

        ret = self._read(read_type=look_for)
        return ret

    # TODO: ADD TIMEOUT
    def _read(self, read_type='terminal') -> str | bool:
        print(f"=== BEGIN READ ===")

        if read_type == 'terminal':
            expected_prompt = on_terminal_prompt
        elif read_type == 'login':
            expected_prompt = on_login_or_terminal_prompt
        else:
            raise ValueError(f"{read_type} is not valid for expected_prompt parameter. "
                             f"Valid parameter values are 'terminal' or 'login'")

        # Reminder: System latency timer changed to 1ms
        read_attempt = 0
        ansi_escape = re.compile(r'(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]')
        polished_read_result = ''
        while not expected_prompt(polished_read_result):
            time.sleep(0.5)
            raw_read_result = self._serial_port.read(self._serial_port.in_waiting)
            read_attempt += 1
            if raw_read_result:
                polished_read_result += ansi_escape.sub('', raw_read_result.decode())

            sys.stdout.write("\r\rRead Attempts: {0}".format(str(read_attempt)))
            sys.stdout.flush()

        print("")
        print(polished_read_result)
        self._serial_port.flushInput()
        print(f"=== END READ ===")
        return polished_read_result

    def _write(self, command):
        print("=== BEGIN WRITE ===")
        print(command)
        ret = self._serial_port.write(f"{command}\r\n".encode())
        self._serial_port.flush()
        print("=== END WRITE ===")
        return ret

    def connect(self, tty_path: str, baudrate: int, username: str, password: str):
        try:
            self._serial_port = Serial(tty_path,
                                       baudrate=baudrate,
                                       parity="E",
                                       stopbits=1,
                                       bytesize=8,
                                       timeout=18,
                                       exclusive=True)
        except SerialException or ValueError as e:
            print(e)
            return False

        self._login(username, password)
        return self._logged_in

    def disconnect(self):
        if self._logged_in:
            self._logout()

        if self._serial_port:
            if self._serial_port.is_open:
                self._serial_port.close()

    def _login(self, username: str, password: str) -> bool | str:
        """

        :param username:
        :param password:
        :return: True if successful, console output/error if failed
        """

        read_res = self.send_command("", look_for='login')

        if "Password:" in read_res:
            # Partial login attempt... Get back to the start of the login prompt
            read_res = self.send_command("", look_for='login')

        if "Login:" in read_res:
            read_res = self.send_command(username, look_for='login')

            if "Password:" in read_res:
                read_res = self.send_command(password)

        if on_terminal_prompt(read_res):
            # Already logged in or successfully logged in
            self._logged_in = True
            return True
        else:
            self._logged_in = False
            return read_res

    def _logout(self):
        self.send_command("/quit", look_for='login')
        self._logged_in = False

    def __del__(self):
        self.disconnect()
