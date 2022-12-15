from __future__ import annotations  # for Python 3.7-3.9

import datetime
import os.path
import sys

import config
import secrets
from Mikrotik import MikrotikDHCPLease
from Mikrotik import MikrotikDNSRecord
from Mikrotik import MikrotikDevice
from PFSense import PFSenseDevice

import platform  # For getting the operating system name
import subprocess  # For executing a shell command


# Credit to https://stackoverflow.com/questions/2953462/pinging-servers-in-python
def ping(host):
    """
    Returns True if host (str) responds to a ping request.
    Remember that a host may not respond to a ping (ICMP) request even if the host name is valid.
    """

    # Option for the number of packets as a function of
    param = '-n' if platform.system().lower() == 'windows' else '-c'

    # Building the command. Ex: "ping -c 1 google.com"
    command = ['ping', param, '1', host]

    return subprocess.call(command) == 0


def set_backup_router_to_standby(backup_router: MikrotikDevice):
    """
    Set the configuration of the backup Mikrotik device back to the 'standby' / 'switch' configuration.
    :return: True if successful, False otherwise
    """
    in_standby_config = False
    backup_router.send_command(":global mode switch")
    res = backup_router.send_command(":put $mode")

    if 'switch' in res.splitlines():
        res = backup_router.send_command("/system/script/run setMode")
        if "Setting configuration to switch mode!" in res and "Done reconfiguring!" in res:
            res = backup_router.send_command(":put [/interface/ethernet/get ether8 mac-address]")
            if "18:FD:74:78:5D:DB" in res:
                in_standby_config = True

    return in_standby_config


def remove_pfsense_records_from_backup(backup_router: MikrotikDevice):
    print("Removing pfsense dns records from mikrotik")
    backup_router.remove_static_dns_with_comment_containing("Added by pfsense")
    print("Removing pfsense dhcp leases from mikrotik")
    backup_router.remove_static_leases_with_comment_containing("Added by pfsense")


def add_static_pfsense_records_to_backup(pfsense_static_dns, pfsense_static_leases, backup_router):
    print("Adding pfsense dns records to mikrotik")
    for pf_dns in pfsense_static_dns:
        mk_dns = MikrotikDNSRecord(ip_address=pf_dns['ip_address'],
                                   hostname=pf_dns['hostname'],
                                   record_type=pf_dns['record_type'],
                                   disabled=True,
                                   comment="mode:router. Added by pfsense.")
        backup_router.write_static_dns_record(mk_dns)

    print("Adding pfsense dhcp leases to mikrotik")
    for pf_lease in pfsense_static_leases:
        mk_lease = MikrotikDHCPLease(mac_address=pf_lease['mac_address'],
                                     ip_address=pf_lease['ip_address'],
                                     hostname=pf_lease['hostname'],
                                     lease_duration=pf_lease['lease_duration'],
                                     disabled=True,
                                     comment="mode:router. Added by pfsense.")
        backup_router.write_reserved_dhcp_lease(mk_lease)


def print_list_dict(data_list: list[dict], title=None):
    """
    Pretty print list of dicts.

    :param list[dict] data_list: List of dictionaries to print
    :param str title: Optional text to print at the start of the dictionary. <br \>
    Center justified with '=' fill characters
    """
    if title:
        print(f"{title:=^32}")
    for data_dict in data_list:
        pretty_print_dict(data_dict)


def pretty_print_dict(data_dict: dict):
    for key in data_dict.keys():
        print(f"{key: >11}: {data_dict[key]}")
    print("")


"""
Usage Notes / Reminders:
/etc/devd.conf must be edited to include something like 
action "/usr/local/bin/python3.8 /pySync/main.py --link_up";
on link up

Since the RouterOS link can briefly go down during reconfiguration back-to-back LINK_UP devd events can
be triggered, resulting in an endless loop.
"""


# TODO: Fix possible endless loop. Probably by logging when the last runtime was and throttling based on that.
# TODO: Add some basic sys logging functionality for monitoring.
# TODO: Handle diffs between Mikrotik and Pfsense. For now it is simple enough to just remove and recreate.

def main(action):
    assert action is not None

    mikro_device = MikrotikDevice()
    # Connect and login to RouterOS
    connected = mikro_device.connect(config.serial_port if config.serial_port else "/dev/ttyU0",
                                     config.baud_rate if config.baud_rate else 115200,
                                     secrets.routeros_username, secrets.routeros_password)
    if not connected:
        print("Serial port or login failure.")
        return

    print("Connected")

    with open('last_login.txt', 'w') as _file:
        _file.write(datetime.datetime.now().strftime("%m/%d/%Y, %H:%M:%S"))

    if action == "sync":
        # Get pfsense records
        pfsense_static_dns = PFSenseDevice.get_reserved_dns_records()
        pfsense_static_leases = PFSenseDevice.get_reserved_dhcp_leases()
        pfsense_dynamic_leases = PFSenseDevice.get_dynamic_dhcp_leases()
        print("Pfsense records loaded")

        # Clear all add pfsense records added to RouterOS
        remove_pfsense_records_from_backup(mikro_device)

        # Add current Pfsense records
        add_static_pfsense_records_to_backup(pfsense_static_dns, pfsense_static_leases, mikro_device)

        # Print pfsense records
        print_list_dict(pfsense_static_dns, "Pfsense Static DNS")
        print_list_dict(pfsense_static_leases, "Pfsense Static Leases")
        print_list_dict(pfsense_dynamic_leases, "Pfsense Dynamic Leases")

        # Get RouterOS records
        mikrotik_static_dns = mikro_device.get_static_dns_records()
        mikrotik_static_leases = mikro_device.get_reserved_dhcp_leases()

        # Print RouterOS records
        print_list_dict(mikrotik_static_dns, "Mikrotik Static DNS")
        print_list_dict(mikrotik_static_leases, "Mikrotik Reserved Leases")

    # Script has been, presumably, called from /etc/devd in response to a LINK_UP event
    elif action == "link_up":
        # Ping a couple of things to make sure we are connected to the expected network
        if ping("10.0.0.2") or ping("10.0.0.3") or ping("10.0.0.20"):
            # Set backup device to back to standby mode (I.E, change it back to 'switch mode')
            standby_mode = set_backup_router_to_standby(mikro_device)
            assert standby_mode is True
            print("Pfsense operational. Mikrotik configured for standby mode")
        else:
            print("Unable to locate any expected LAN devices.")

    else:
        print("Invalid action")

    mikro_device.disconnect()
    print("Disconnected")


if __name__ == "__main__":
    # See how long it has been since the last time the script ran
    try:
        with open('last_login.txt', 'r') as file:
            last_modified = datetime.datetime.strptime(file.read(), "%m/%d/%Y, %H:%M:%S")
            interval_seconds = 30
            if (datetime.datetime.now() - last_modified) < datetime.timedelta(seconds=interval_seconds):
                print(f"Wait at least {interval_seconds} seconds between calls")
    except FileNotFoundError:
        print("last_login.txt not present. File will be created after the first successful login to RouterOS.")

    if "--sync" in sys.argv:
        main("sync")
    elif "--link_up" in sys.argv:
        main("link_up")
    else:
        print("Usage: main.py ACTION")
        print("ACTION")
        print("--sync")
        print("Synchronize pfsense records to the backup routeros device")
        print("--link_up")
        print("Indicates to the application that pfsense is ready to resume control.")
        print("In other words, it sets the standby router to the standby configuration")
        print("Script checks for presence of LAN devices before commanding backup router to return to standby config.")

    os.remove("lock")
