"""
| Configuration file
| dhcpd_conf_file -> static_ip leases
| dhcp_leases_file -> dynamic leases
| host_entries_file -> static_ip dns
"""

dhcpd_conf_file = 'dhcpd.conf'  # /var/dhcpd/etc/dhcpd.conf
"""
| Path to dhcpd.conf (Static Leases)
| pfsense path: /var/dhcpd/etc/dhcpd.conf
"""

dhcp_leases_file = 'dhcpd.leases'  # /var/dhcpd/var/db/dhcpd.leases
"""
| Path to dhcpd.leases (Dynamic Leases)
| pfsense path: /var/dhcpd/var/db/dhcpd.leases
"""

host_entries_file = 'host_entries.conf'  # /var/unbound/host_entries.conf
"""
| Path to host_entries.con (Static DNS / DNS Alias)
| pfsense path: /var/unbound/host_entries.conf
"""

serial_port = "COM3"
baud_rate = 115200
