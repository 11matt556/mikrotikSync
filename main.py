from __future__ import annotations  # for Python 3.7-3.9

import secrets
from Mikrotik import MikrotikDHCPLease
from Mikrotik import MikrotikDNSRecord
from Mikrotik import MikrotikDevice
from PFSense import PFSenseDevice


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


# TODO: Add commandline switches to handle transfer between mikrotik primary and secondary roles
# TODO: Handle diffs between Mikrotik and Pfsense. For now it is simple enough to just remove and recreate.

def main():
    # Get pfsense records
    pfsense_static_dns = PFSenseDevice.get_reserved_dns_records()
    pfsense_static_leases = PFSenseDevice.get_reserved_dhcp_leases()
    pfsense_dynamic_leases = PFSenseDevice.get_dynamic_dhcp_leases()

    # Print pfsense records
    print_list_dict(pfsense_static_dns, "Pfsense Static DNS")
    print_list_dict(pfsense_static_leases, "Pfsense Static Leases")
    print_list_dict(pfsense_dynamic_leases, "Pfsense Dynamic Leases")

    # Connect to and login to RouterOS
    mikro_device = MikrotikDevice()
    mikro_device.connect("COM3", 115200, secrets.routeros_username, secrets.routeros_password)
    print("Connected")

    # Set to standby mode
    standby_mode = set_backup_router_to_standby(mikro_device)
    assert standby_mode is True

    # Clear all add pfsense records added to RouterOS
    remove_pfsense_records_from_backup(mikro_device)

    # Add current Pfsense records
    add_static_pfsense_records_to_backup(pfsense_static_dns, pfsense_static_leases, mikro_device)

    # Get RouterOS records
    mikrotik_static_dns = mikro_device.get_static_dns_records()
    mikrotik_static_leases = mikro_device.get_reserved_dhcp_leases()

    # Print RouterOS records
    print_list_dict(mikrotik_static_dns, "Mikrotik Static DNS")
    print_list_dict(mikrotik_static_leases, "Mikrotik Reserved Leases")

    mikro_device.disconnect()
    print("Disconnected")


if __name__ == "__main__":
    main()
    print("Done")
