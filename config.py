"""
| Configuration file
| dhcpd_conf_file -> static leases
| dhcp_leases_file -> dynamic leases
| host_entries_file -> static dns
"""

dhcpd_conf_file: str = 'dhcpd.conf'
"""
| Path to dhcpd.conf (Static Leases)
| Default: /var/dhcpd/etc/dhcpd.conf
"""

dhcp_leases_file: str = 'dhcpd.leases'
"""
| Path to dhcpd.leases (Dynamic Leases)
| Default: /var/dhcpd/var/db/dhcpd.leases
"""

host_entries_file: str = 'host_entries.conf'
"""
| Path to host_entries.con (Static DNS / DNS Alias)
| Default: /var/unbound/host_entries.conf
"""

serial_port: str = "COM3"
"""
Default: /dev/ttyU0
"""

baud_rate: int = 115200
"""
Default: 115200
"""
