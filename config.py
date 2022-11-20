static_lease_path = "dhcpd.conf"  # /var/dhcpd/etc/dhcpd.conf
dynamic_lease_path = "dhcpd.leases"  # /var/dhcpd/var/db/dhcpd.leases
host_entries_path = "host_entries.conf"  # /var/unbound/host_entries.conf

serial_tty_path = "COM3"
serial_baud_rate = 115200

pf_print = False
ros_print = True
ros_skip_import = False
ros_setMode = ""  # Valid options are switch or router. Anything else will have no effect.
ros_add_records = True  # Add records. If both adding and removing records, adding happens first
ros_remove_records = False  # Remove records added by this script
