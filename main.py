import pfsense as pf
import routeros as ros
import config


def main():
    pfsense = pf.Pfsense(static_lease_path=config.static_lease_path,
                         dynamic_lease_path=config.dynamic_lease_path,
                         host_entries_path=config.host_entries_path)

    backup_router = ros.RouterOS(connection_string=config.serial_tty_path,
                                 baud_rate=config.serial_baud_rate,
                                 skip_import=config.ros_skip_import)

    #if config.pf_print:
    #    pfsense.dhcp_server.print_dhcp_leases()
    #    pfsense.dns_server.print_dns_records()

    #if config.ros_print and not config.ros_skip_import:
    #    backup_router.dhcp_server.print_dhcp_leases()
    #    backup_router.dns_server.print_dns_records()

    if config.ros_setMode == 'switch' or config.ros_setMode == 'router':
        backup_router.set_mode(config.ros_setMode)

    if config.ros_add_records:
        print("=== ADDING RECORDS ===")
        backup_router.dhcp_server.add_dhcp_leases(pfsense.dhcp_server.get_all_dhcp_leases())
        backup_router.dns_server.add_dns_records(pfsense.dns_server.get_all_dns_records())
        print("=== RECORDS ADDED ===")

    if config.ros_remove_records:
        print("=== Removing records added by this script ===")
        backup_router.dhcp_server.remove_all_pfsense_records()
        backup_router.dns_server.remove_all_pfsense_records()
        print("===  RECORDS REMOVED ===")

    if config.pf_print:
        pfsense.dhcp_server.print_dhcp_leases()
        pfsense.dns_server.print_dns_records()

    if config.ros_print and not config.ros_skip_import:
        backup_router.dhcp_server.print_dhcp_leases()
        backup_router.dns_server.print_dns_records()

    print("Done.")


if __name__ == "__main__":
    main()
