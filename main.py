import pfsense as pf
import routeros as ros
import argparse


def main():
    parser = argparse.ArgumentParser(description="Some description")
    parser.add_argument('--connection_string',
                        action='store',
                        help="Currently only supports serial connection. Path to tty device path or COM port.",
                        default="/dev/ttyS1",
                        type=str
                        )
    parser.add_argument('--serial_baud_rate',
                        action='store',
                        help="Baud Rate in bps. Suggested baud rates: 9600, 19200, 115200, 460800.",
                        default=460800,
                        type=int
                        )

    parser.add_argument('--static_lease_path',
                        action='store',
                        help="Path to dhcpd.conf",
                        type=str,
                        default="/var/dhcpd/etc/dhcpd.conf"
                        )

    parser.add_argument('--dynamic_lease_path',
                        action='store',
                        help="Path to dhcpd.leases",
                        type=str,
                        default="/var/dhcpd/var/db/dhcpd.leases"
                        )

    parser.add_argument('--host_entries_path',
                        action='store',
                        help="Path to host_entries.conf for DNS",
                        type=str,
                        default="/var/unbound/host_entries.conf"
                        )

    parser.add_argument('--setMode',
                        action='store',
                        help="Set the mode of the RouterOS device.",
                        type=str,
                        default=False,
                        choices=['router', 'switch']
                        )

    parser.add_argument('--remove_managed_records',
                        action='store',
                        help="Remove any records added by this script. "
                             "Will not run part of the script that adds records.",
                        type=bool,
                        default=False
                        )

    parser.add_argument('--print_pf_records',
                        action='store',
                        help="Print DNS and DHCP records of Pfsense. "
                             "Prints before and after records are changed.",
                        type=bool
                        )

    parser.add_argument('--print_ros_records',
                        action='store',
                        help="Print DNS and DHCP records of RouterOS. "
                             "Prints before and after records are changed. "
                             "Ignored when --skip_ros_import is True.",
                        type=bool
                        )

    parser.add_argument('--skip_ros_import',
                        action='store',
                        help="Skip import from RouterOS.",
                        type=bool,
                        default=False
                        )

    args = vars(parser.parse_args())

    pfsense = pf.Pfsense(static_lease_path=args['static_lease_path'],
                         dynamic_lease_path=args['dynamic_lease_path'],
                         host_entries_path=args['host_entries_path'])

    backup_router = ros.RouterOS(connection_string=args['connection_string'],
                                 baud_rate=args['serial_baud_rate'],
                                 do_import=not args['skip_ros_import'])

    if args['print_pf_records']:
        pfsense.dhcp_server.print_dhcp_leases()
        pfsense.dns_server.print_dns_records()

    if args['print_ros_records'] and not args['skip_ros_import']:
        backup_router.dhcp_server.print_dhcp_leases()
        backup_router.dns_server.print_dns_records()

    if args['setMode']:
        backup_router.set_mode(args['setMode'])

    if args['remove_managed_records']:
        print("=== Removing records added by this script ===")
        backup_router.dhcp_server.remove_all_pfsense_records()
        backup_router.dns_server.remove_all_pfsense_records()
        print("===  RECORDS REMOVED ===")
    else:
        print("=== ADDING RECORDS ===")
        backup_router.dhcp_server.add_dhcp_leases(pfsense.dhcp_server.get_all_dhcp_leases())
        backup_router.dns_server.add_dns_records(pfsense.dns_server.get_all_dns_records())
        print("=== RECORDS ADDED ===")

    if args['print_pf_records']:
        pfsense.dhcp_server.print_dhcp_leases()
        pfsense.dns_server.print_dns_records()

    if args['print_ros_records'] and not args['skip_ros_import']:
        backup_router.dhcp_server.print_dhcp_leases()
        backup_router.dns_server.print_dns_records()

    print("Done.")


if __name__ == "__main__":
    main()
