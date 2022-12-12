from __future__ import annotations  # for Python 3.7-3.9

from Mikrotik import MikrotikDevice
from Mikrotik import MikrotikDHCPLease
from Mikrotik import MikrotikDNSRecord
from PFSense import PFSenseDevice

import secrets


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


def main():
    pfsense_static_dns = PFSenseDevice.get_reserved_dns_records()
    print_list_dict(pfsense_static_dns, "Static DNS")

    pfsense_static_leases = PFSenseDevice.get_reserved_dhcp_leases()
    print_list_dict(pfsense_static_leases, "Static Leases")

    pfsense_dynamic_leases = PFSenseDevice.get_dynamic_dhcp_leases()
    print_list_dict(pfsense_dynamic_leases, "Dynamic Leases")

    mikrotik_device_handler = MikrotikDevice()
    mikrotik_device_handler.connect("COM3", 115200, secrets.routeros_username, secrets.routeros_password)
    print("Connected")

    print("Removing pfsense dns records from mikrotik")
    mikrotik_device_handler.remove_static_dns_records_with_comment_containing("Added by pfsense")
    print("Removing pfsense dhcp leases from mikrotik")
    mikrotik_device_handler.remove_reserved_dhcp_leases_with_comment_containing("Added by pfsense")

    print("Adding pfsense dns records to mikrotik")
    for pf_dns in pfsense_static_dns:
        mk_dns = MikrotikDNSRecord(ip_address=pf_dns['ip_address'],
                                   hostname=pf_dns['hostname'],
                                   record_type=pf_dns['record_type'],
                                   disabled=True,
                                   comment="mode:router. Added by pfsense.")
        mikrotik_device_handler.write_static_dns_record(mk_dns)

    print("Adding pfsense dhcp leases to mikrotik")
    for pf_lease in pfsense_static_leases:
        mk_lease = MikrotikDHCPLease(mac_address=pf_lease['mac_address'],
                                     ip_address=pf_lease['ip_address'],
                                     hostname=pf_lease['hostname'],
                                     lease_duration=pf_lease['lease_duration'],
                                     disabled=True,
                                     comment="mode:router. Added by pfsense.")
        mikrotik_device_handler.write_reserved_dhcp_lease(mk_lease)

    mikrotik_reserved_dns = mikrotik_device_handler.get_static_dns_records()
    mikrotik_reserved_leases = mikrotik_device_handler.get_reserved_dhcp_leases()

    print_list_dict(mikrotik_reserved_dns, "Mikrotik Static DNS")
    print_list_dict(mikrotik_reserved_leases, "Mikrotik Reserved Leases")

    mikrotik_device_handler.disconnect()
    print("Disconnected")


if __name__ == "__main__":
    main()
    print("Done")
