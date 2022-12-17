"""
| Contains Default Configuration Options.
| Do not change this file. See config.py
| dhcpd_conf_file -> static leases
| dhcp_leases_file -> dynamic leases
| host_entries_file -> static dns
"""

dhcpd_conf_file: str = '/var/dhcpd/etc/dhcpd.conf'
"""
| Path to dhcpd.conf (Static Leases)
| Default: /var/dhcpd/etc/dhcpd.conf
"""

dhcp_leases_file: str = '/var/dhcpd/var/db/dhcpd.leases'
"""
| Path to dhcpd.leases (Dynamic Leases)
| Default: /var/dhcpd/var/db/dhcpd.leases
"""

host_entries_file: str = '/var/unbound/host_entries.conf'
"""
| Path to host_entries.con (Static DNS / DNS Alias)
| Default: /var/unbound/host_entries.conf
"""

serial_port: str = "/dev/ttyU0"
"""
Default: /dev/ttyU0
"""

baud_rate: int = 115200
"""
Default: 115200
"""

login_interval_seconds: int = 5
"""
| How long it has been since the script last logged in to the backup router.
| The script cannot be ran again if it has not been at least login_interval_seconds since the last login.
|
| This is to prevent possible endless loops of the backup router beinging up/down a port while reconfiguring, which then
| triggers the devd to run this script again, etc
"""